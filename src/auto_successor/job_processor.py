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
    record.company = _normalize_cell(record.company, fallback="未知", max_len=60)
    record.position = _normalize_cell(record.position, fallback="未知", max_len=80)
    record.location = _normalize_cell(record.location, fallback="未知", max_len=40)
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
