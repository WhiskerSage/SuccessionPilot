from __future__ import annotations

import csv
import re
from pathlib import Path

from .models import JobRecord, NoteRecord

CITIES = [
    "上海",
    "北京",
    "深圳",
    "广州",
    "杭州",
    "南京",
    "成都",
    "苏州",
    "武汉",
    "西安",
    "天津",
]

LOCATION_MOJIBAKE_MAP = {
    "鍖椾含": "北京",
    "涓婃捣": "上海",
    "骞垮窞": "广州",
    "娣卞湷": "深圳",
    "鏉宸": "杭州",
    "鍗椾含": "南京",
    "鎴愰兘": "成都",
    "姝︽眽": "武汉",
    "瑗垮畨": "西安",
    "鑻忓窞": "苏州",
    "澶╂触": "天津",
}

COMPANY_NOISE_VALUES = {
    "未知",
    "公司待补充",
    "岗位待补充",
    "实习招",
    "招继任",
    "找继任",
    "急招",
    "招聘",
    "在招",
    "内推",
}
COMPANY_PREFIX_PATTERNS = [
    r"^(?:急招|急聘|诚招|招聘|招募|内推|扩招|急缺)\s*",
    r"^(?:找|求)(?:继任|接任)\s*",
    r"^(?:招|找|求)(?:继任|接任|实习|实习生|岗位)\s*(?:[:：|｜/、，,\-\s]+)",
]
COMPANY_SUFFIX_PATTERNS = [
    r"(?:急招|招聘中?|在招|招募中?)$",
    r"(?:找|求)(?:继任|接任)$",
    r"(?:招|找|求)(?:继任|接任|实习|实习生|岗位)$",
]

POSITION_HINTS = [
    "实习生",
    "产品",
    "运营",
    "算法",
    "开发",
    "前端",
    "后端",
    "数据",
    "研究",
    "商业化",
    "HR",
]

REQUIREMENT_HINTS = [
    "届",
    "毕业",
    "每周",
    "到岗",
    "实习",
    "天",
    "月",
    "base",
    "长期",
    "短期",
]


def to_job_record(note: NoteRecord) -> JobRecord:
    text = f"{note.title}\n{note.detail_text}".strip()
    company = _extract_company(text)
    position = _extract_position(text)
    location = _extract_location(text)
    requirements = _extract_requirements(text)
    record = JobRecord(
        run_id=note.run_id,
        post_id=note.note_id,
        company=company,
        position=position,
        location=location,
        requirements=requirements,
        parse_source="rule",
        original_text=note.detail_text,
        arrival_time="",
        application_method="",
        author=note.author,
        risk_line="",
        match_score=0.0,
        match_reason="",
        link=note.url,
        mode="auto",
        publish_time=note.publish_time,
        source_title=note.title,
        comment_count=note.comment_count,
        comments_preview=note.comments_preview,
    )
    return normalize_job_record(record)


def to_job_records(notes: list[NoteRecord]) -> list[JobRecord]:
    records = [to_job_record(note) for note in notes]
    records.sort(key=lambda item: item.publish_time, reverse=True)
    return records


def write_jobs_csv(path: str, records: list[JobRecord]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Company", "Position", "Location", "Requirements", "Link", "PostID"])
        for row in records:
            writer.writerow([row.company, row.position, row.location, row.requirements, row.link, row.post_id])


def normalize_job_record(record: JobRecord) -> JobRecord:
    record.post_id = _normalize_cell(record.post_id, fallback="unknown_post", max_len=120)
    record.company = _normalize_company(record.company)
    record.position = _normalize_cell(record.position, fallback="未知", max_len=80)
    record.location = _normalize_location(record.location)
    record.requirements = _normalize_cell(record.requirements, fallback="未提取到明确要求", max_len=180)
    record.arrival_time = _normalize_cell(record.arrival_time, fallback="未明确", max_len=120)
    record.application_method = _normalize_cell(record.application_method, fallback="未明确", max_len=180)
    record.author = _normalize_cell(record.author, fallback="未知", max_len=80)
    record.risk_line = _normalize_cell(record.risk_line, fallback="low", max_len=80)
    record.match_reason = _normalize_cell(record.match_reason, fallback="", max_len=220)
    try:
        record.match_score = max(0.0, min(100.0, float(record.match_score)))
    except Exception:
        record.match_score = 0.0
    record.source_title = _normalize_cell(record.source_title, fallback="", max_len=200)
    record.comments_preview = _normalize_cell(record.comments_preview, fallback="", max_len=500)
    record.original_text = _normalize_cell(record.original_text, fallback="", max_len=4000)
    record.mode = _normalize_cell(record.mode, fallback="auto", max_len=20)
    record.outreach_message = _normalize_cell(record.outreach_message, fallback="", max_len=240)
    parse_source = _normalize_cell(record.parse_source, fallback="rule", max_len=20).lower()
    if parse_source not in {"rule", "llm"}:
        parse_source = "rule"
    record.parse_source = parse_source

    link = _normalize_cell(record.link, fallback="", max_len=600)
    if not link.startswith(("http://", "https://")):
        link = f"https://www.xiaohongshu.com/explore/{record.post_id}"
    record.link = link
    return record


def _extract_company(text: str) -> str:
    title = text.splitlines()[0] if text else ""
    m = re.search(r"([A-Za-z0-9\u4e00-\u9fa5（）()·\-\s]{2,30})(?:招|招聘|继任|接任|实习)", title)
    if m:
        return _clean(m.group(1))
    m = re.search(r"(?:在|于)([A-Za-z0-9\u4e00-\u9fa5（）()·\-\s]{2,20})(?:实习|工作|团队)", text)
    if m:
        return _clean(m.group(1))
    return "未知"


def _extract_position(text: str) -> str:
    for hint in POSITION_HINTS:
        if hint in text:
            if hint == "实习生":
                return "实习生"
            # Capture nearby phrase.
            m = re.search(rf"([A-Za-z0-9\u4e00-\u9fa5]{{0,8}}{re.escape(hint)}[A-Za-z0-9\u4e00-\u9fa5]{{0,8}})", text)
            if m:
                return _clean(m.group(1))
            return hint
    return "未知"


def _extract_location(text: str) -> str:
    for city in CITIES:
        if city in text:
            return city
    m = re.search(r"(?:base|地点|坐标|城市)[:：\s]*([A-Za-z\u4e00-\u9fa5]{2,12})", text, flags=re.IGNORECASE)
    if m:
        return _clean(m.group(1))
    return "未知"


def _normalize_company(value: str) -> str:
    text = _normalize_cell(value, fallback="未知", max_len=120)
    for pattern in COMPANY_PREFIX_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    for pattern in COMPANY_SUFFIX_PATTERNS:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    text = _clean(text)
    if not text:
        return "未知"
    if text in COMPANY_NOISE_VALUES:
        return "未知"
    if re.fullmatch(r"[找求招聘继任接任实习岗位内推急]+", text):
        return "未知"
    return text[:60]


def _normalize_location(value: str) -> str:
    text = _normalize_cell(value, fallback="未知", max_len=120)
    if text in {"-", "—", "--", "未知"}:
        return "未知"
    text = _decode_location_mojibake(text)
    text = _replace_known_location_mojibake(text)
    text = re.sub(r"(?i)(?:base|地点|城市|坐标)[:：\s]*", "", text).strip()
    for city in CITIES:
        if city in text:
            return city
    text = _clean(text)
    if not text or text in {"-", "—", "--"}:
        return "未知"
    return text[:40]


def _decode_location_mojibake(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    best = value
    best_score = _location_text_score(value)
    for encoding in ("gbk", "gb18030"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except Exception:
            continue
        score = _location_text_score(candidate)
        if score > best_score + 0.6:
            best = candidate
            best_score = score
    return best


def _replace_known_location_mojibake(text: str) -> str:
    value = str(text or "")
    for bad, good in LOCATION_MOJIBAKE_MAP.items():
        if bad in value:
            value = value.replace(bad, good)
    return value


def _location_text_score(text: str) -> float:
    value = str(text or "")
    if not value:
        return -999.0
    city_hit = sum(1 for city in CITIES if city in value)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", value))
    odd = len(re.findall(r"[^\u4e00-\u9fffA-Za-z0-9·・/,\-:：\s]", value))
    return (city_hit * 5.0) + (cjk * 0.2) - (odd * 2.0)


def _extract_requirements(text: str) -> str:
    lines = re.split(r"[。；;\n]", text)
    picked = []
    for line in lines:
        line = _clean(line)
        if not line:
            continue
        if any(h in line for h in REQUIREMENT_HINTS):
            picked.append(line)
        if len(picked) >= 2:
            break
    if not picked:
        return "未提取到明确要求"
    return "；".join(picked)[:140]


def _clean(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip(" ,，。:：-")
    return text


def _normalize_cell(value: str, fallback: str, max_len: int) -> str:
    text = _clean(str(value or ""))
    if not text:
        text = fallback
    return text[:max_len]
