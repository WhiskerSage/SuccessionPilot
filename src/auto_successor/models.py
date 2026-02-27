from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class NoteRecord:
    run_id: str
    keyword: str
    note_id: str
    title: str
    author: str
    publish_time: datetime
    publish_time_text: str
    like_count: int
    comment_count: int
    share_count: int
    url: str
    raw_json: str
    xsec_token: str = ""
    publish_time_quality: str = "parsed"
    detail_text: str = ""
    comments_preview: str = ""
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SummaryRecord:
    run_id: str
    note_id: str
    keyword: str
    publish_time: datetime
    title: str
    author: str
    summary: str
    confidence: float
    risk_flags: str
    url: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SendLogRecord:
    run_id: str
    note_id: str
    channel: str
    send_status: str
    send_response: str
    sent_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SendResult:
    status: str
    response: str


@dataclass
class JobRecord:
    run_id: str
    post_id: str
    company: str
    position: str
    location: str
    requirements: str
    link: str
    publish_time: datetime
    source_title: str
    comment_count: int
    comments_preview: str
    original_text: str = ""
    arrival_time: str = ""
    application_method: str = ""
    author: str = ""
    risk_line: str = "low"
    match_score: float = 0.0
    match_reason: str = ""
    parse_source: str = "rule"
    mode: str = "auto"
    opportunity_point: bool = False
    outreach_message: str = ""
