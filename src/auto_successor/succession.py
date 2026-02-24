from __future__ import annotations

import re

from .models import NoteRecord, SummaryRecord

RISK_TOKENS = ["诈骗", "警惕", "已招到", "避雷", "坑"]
JD_TOKENS = ["岗位职责", "工作内容", "岗位要求", "任职要求", "职位描述", "岗位JD", "jd"]


def build_summary(note: NoteRecord) -> SummaryRecord:
    title = note.title or "(无标题)"
    combined_text = f"{title}\n{note.detail_text or ''}\n{note.comments_preview or ''}"
    risk_hit = [token for token in RISK_TOKENS if token in combined_text]
    confidence = 1.0
    risk_flags = ",".join(risk_hit)

    poster_comment_update = extract_poster_comment_update(
        comments_preview=note.comments_preview or "",
        comment_count=note.comment_count,
    )

    detail_line = clean_line((note.detail_text or "").replace("\n", " "))
    if detail_line:
        detail_line = detail_line[:380]
    else:
        detail_line = (
            f"帖子可见信息主要来自标题：{title}。当前未抓取到稳定正文，建议人工打开原帖确认岗位要求、地点和投递方式。"
        )[:380]

    jd_full = extract_jd_full(note.detail_text)
    arrival_info = extract_arrival_info(note.detail_text)
    apply_info = extract_apply_info(note.detail_text)

    summary = (
        f"【继任追踪】{title}\n"
        f"作者：{note.author or '未知'}\n"
        f"发布时间：{note.publish_time_text or note.publish_time.strftime('%Y-%m-%d')}\n"
        f"互动：赞{note.like_count} 评{note.comment_count} 转{note.share_count}\n"
        f"正文信息（详细）：{detail_line}\n"
        f"贴主补充评论：{poster_comment_update}\n"
        f"到岗信息：{arrival_info or '未明确'}\n"
        f"投递方式：{apply_info or '未明确'}\n"
        f"JD全文：{jd_full or '未提取到完整JD（可查看原帖图片/附件）'}\n"
        f"风险标记：{risk_flags or '无'}\n"
        f"链接：{note.url}"
    )

    return SummaryRecord(
        run_id=note.run_id,
        note_id=note.note_id,
        keyword=note.keyword,
        publish_time=note.publish_time,
        title=title,
        author=note.author,
        summary=summary,
        confidence=confidence,
        risk_flags=risk_flags,
        url=note.url,
    )


def clean_line(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_poster_comment_update(comments_preview: str, comment_count: int) -> str:
    text = clean_line((comments_preview or "").replace("\n", " / "))
    if not text:
        if int(comment_count or 0) > 0:
            return "评论区有互动，未识别到贴主额外补充。"
        return "未见贴主补充评论。"

    if re.search(r"(贴主|楼主|作者|博主).{0,8}(回复|补充|更新)", text):
        return "检测到贴主有补充评论，建议查看原帖评论区。"
    if re.search(r"(回复贴主|仅作者可见|作者置顶)", text):
        return "疑似贴主有补充评论，建议查看原帖评论区。"
    return "未识别到贴主补充评论。"


def extract_jd_full(detail_text: str) -> str:
    text = clean_line(detail_text)
    if not text:
        return ""
    lower = text.lower()
    pos = -1
    for token in JD_TOKENS:
        idx = lower.find(token.lower())
        if idx >= 0 and (pos < 0 or idx < pos):
            pos = idx
    if pos >= 0:
        return text[pos : pos + 1100].strip()
    if any(k in text for k in ["岗位", "职责", "要求", "到岗", "实习", "base"]):
        return text[:900]
    return ""


def extract_arrival_info(detail_text: str) -> str:
    text = clean_line(detail_text)
    if not text:
        return ""
    patterns = [
        r"(\d{1,2}[./月-]\d{1,2}\s*前?到岗[^，。；]{0,30})",
        r"(下周[^，。；]{0,20}到岗[^，。；]{0,30})",
        r"(尽快到岗[^，。；]{0,30})",
        r"(到岗时间[^：:]{0,6}[：:]\s*[^，。；]{1,60})",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return clean_line(m.group(1))[:140]
    return ""


def extract_apply_info(detail_text: str) -> str:
    text = clean_line(detail_text)
    if not text:
        return ""
    email = re.search(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)
    if email:
        return f"邮箱投递：{email.group(1)}"
    patterns = [
        r"(投递[^，。；]{0,80})",
        r"(简历[^，。；]{0,80})",
        r"(发送到[^，。；]{0,80})",
        r"(私信[^，。；]{0,80})",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return clean_line(m.group(1))[:180]
    return ""
