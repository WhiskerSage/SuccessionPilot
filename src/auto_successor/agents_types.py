from __future__ import annotations

from dataclasses import dataclass, field

from .models import JobRecord, NoteRecord, SendLogRecord


class AgentPlan:
    mode: str
    detail_fetch_limit: int
    max_filter_items: int
    max_job_items: int
    max_summary_items: int
    top_n: int
    include_jd_full: bool

class FilterOutcome:
    targets: list[NoteRecord]
    filtered_out: list[dict]
    scores: dict[str, float]

class ExtractOutcome:
    targets: list[NoteRecord]
    jobs: list[JobRecord]
    filtered_out: list[dict]
    scores: dict[str, float]
    note_agent_stats: dict[str, int] = field(default_factory=dict)
    note_agent_details: list[dict[str, object]] = field(default_factory=list)

class NoteAgentTask:
    index: int
    note: NoteRecord
    allow_llm: bool

class NoteAgentResult:
    index: int
    note: NoteRecord
    decision: object
    job: JobRecord
    allow_llm: bool
    worker_fallback: bool = False
    error: str = ""

class BatchDispatchResult:
    sent: bool
    logs: list[SendLogRecord]
    subject: str
    body: str
    opportunity_post_ids: list[str]

class DigestDispatchResult:
    sent: bool
    logs: list[SendLogRecord]
    subject: str
    body: str

__all__ = [
    "AgentPlan",
    "FilterOutcome",
    "ExtractOutcome",
    "NoteAgentTask",
    "NoteAgentResult",
    "BatchDispatchResult",
    "DigestDispatchResult",
]
