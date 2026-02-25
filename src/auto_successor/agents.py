from __future__ import annotations

from dataclasses import dataclass
from math import floor
from pathlib import Path

from .config import Settings
from .job_processor import normalize_job_record, to_job_record
from .llm_enricher import LLMEnricher
from .models import JobRecord, NoteRecord, SendLogRecord, SummaryRecord
from .notification_router import NotificationRouter

URGENT_TOKENS = ["急招", "尽快到岗", "马上到岗", "asap", "urgent", "立即入职"]


@dataclass
class AgentPlan:
    mode: str
    detail_fetch_limit: int
    max_filter_items: int
    max_job_items: int
    max_summary_items: int
    top_n: int
    include_jd_full: bool


@dataclass
class FilterOutcome:
    targets: list[NoteRecord]
    filtered_out: list[dict]
    scores: dict[str, float]


@dataclass
class BatchDispatchResult:
    sent: bool
    logs: list[SendLogRecord]
    subject: str
    body: str
    opportunity_post_ids: list[str]


@dataclass
class DigestDispatchResult:
    sent: bool
    logs: list[SendLogRecord]
    subject: str
    body: str


class PlannerAgent:
    def __init__(self, settings: Settings, logger) -> None:
        self.settings = settings
        self.logger = logger

    def build_plan(self, mode: str, fetched_count: int, new_count: int) -> AgentPlan:
        mode = (mode or "auto").strip().lower()
        if mode == "smart":
            mode = "agent"
        if mode not in {"auto", "agent"}:
            mode = "auto"

        if mode == "agent":
            full_detail = self._agent_bool("agent_full_detail_fetch", "smart_full_detail_fetch", True)
            detail_fetch_limit = fetched_count if full_detail else min(self.settings.xhs.max_detail_fetch, fetched_count)
            max_filter_items = new_count
            max_job_items = new_count
            max_summary_items = new_count
            top_n = max(1, self._agent_int("agent_send_top_n", "smart_send_top_n", 5))
            include_jd_full = self._agent_bool("agent_include_jd_full", "smart_include_jd_full", True)
        else:
            detail_fetch_limit = min(self.settings.xhs.max_detail_fetch, fetched_count)
            max_filter_items = max(0, int(self.settings.llm.max_filter_items))
            max_job_items = max(0, int(self.settings.llm.max_job_items))
            max_summary_items = max(0, int(self.settings.llm.max_summary_items))
            top_n = max(1, self._agent_int("agent_send_top_n", "smart_send_top_n", 3))
            include_jd_full = self._agent_bool("agent_include_jd_full", "smart_include_jd_full", True)

        plan = AgentPlan(
            mode=mode,
            detail_fetch_limit=max(0, detail_fetch_limit),
            max_filter_items=max(0, max_filter_items),
            max_job_items=max(0, max_job_items),
            max_summary_items=max(0, max_summary_items),
            top_n=top_n,
            include_jd_full=include_jd_full,
        )
        self.logger.info(
            "planner plan mode=%s detail_fetch=%s filter=%s jobs=%s summaries=%s top_n=%s",
            plan.mode,
            plan.detail_fetch_limit,
            plan.max_filter_items,
            plan.max_job_items,
            plan.max_summary_items,
            plan.top_n,
        )
        return plan

    def _agent_bool(self, key: str, legacy_key: str, default: bool) -> bool:
        if hasattr(self.settings.agent, key):
            return bool(getattr(self.settings.agent, key))
        if hasattr(self.settings.agent, legacy_key):
            return bool(getattr(self.settings.agent, legacy_key))
        return default

    def _agent_int(self, key: str, legacy_key: str, default: int) -> int:
        if hasattr(self.settings.agent, key):
            return int(getattr(self.settings.agent, key))
        if hasattr(self.settings.agent, legacy_key):
            return int(getattr(self.settings.agent, legacy_key))
        return default


class IntelligenceAgent:
    def __init__(self, llm_enricher: LLMEnricher, logger) -> None:
        self.llm_enricher = llm_enricher
        self.logger = logger

    def filter_target_notes(self, notes: list[NoteRecord], max_filter_items: int) -> FilterOutcome:
        targets: list[NoteRecord] = []
        filtered_out: list[dict] = []
        scores: dict[str, float] = {}

        for idx, note in enumerate(notes):
            allow_llm = idx < max(0, int(max_filter_items))
            decision = self.llm_enricher.classify_target(note, allow_llm=allow_llm)
            scores[note.note_id] = float(decision.score)
            if decision.is_target:
                targets.append(note)
                continue
            filtered_out.append(
                {
                    "note_id": note.note_id,
                    "title": note.title[:100],
                    "score": round(decision.score, 4),
                    "reason": decision.reason,
                    "source": decision.source,
                }
            )
            self.logger.info(
                "filter out note=%s score=%.2f source=%s reason=%s",
                note.note_id,
                decision.score,
                decision.source,
                decision.reason,
            )

        return FilterOutcome(targets=targets, filtered_out=filtered_out, scores=scores)

    def build_jobs(self, notes: list[NoteRecord], max_job_items: int, resume_text: str, mode: str) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        for idx, note in enumerate(notes):
            job = to_job_record(note)
            job.mode = mode
            if idx < max(0, int(max_job_items)):
                job = self.llm_enricher.enrich_job(note, job, resume_text=resume_text, mode=mode)
            jobs.append(normalize_job_record(job))
        jobs.sort(key=lambda item: item.publish_time, reverse=True)
        return jobs

    def mark_opportunities(self, jobs: list[JobRecord]) -> list[JobRecord]:
        if not jobs:
            return jobs

        max_score = max(float(item.match_score or 0.0) for item in jobs)
        if max_score <= 0.0:
            for job in jobs:
                job.opportunity_point = False
            return jobs

        limit = max(1, min(len(jobs), floor(len(jobs) * 0.3)))

        for job in jobs:
            job.opportunity_point = False

        ranked = sorted(
            jobs,
            key=lambda item: (
                self._is_urgent(item),
                float(item.match_score),
            ),
            reverse=True,
        )

        selected = ranked[:limit]
        if selected:
            selected[0].opportunity_point = True
        for item in selected:
            item.opportunity_point = True
        return jobs

    def attach_outreach_messages(self, jobs: list[JobRecord], resume_text: str) -> list[JobRecord]:
        for job in jobs:
            if not job.opportunity_point:
                job.outreach_message = ""
                continue
            job.outreach_message = self.llm_enricher.build_outreach_message(job, resume_text=resume_text)
        return jobs

    @staticmethod
    def rank_targets(targets: list[NoteRecord], scores: dict[str, float], top_n: int) -> list[NoteRecord]:
        if not targets:
            return []
        ranked = sorted(
            targets,
            key=lambda n: (
                float(scores.get(n.note_id, 0.0)),
                int(n.comment_count),
                int(n.like_count),
                n.publish_time,
            ),
            reverse=True,
        )
        return ranked[: max(1, int(top_n))]

    @staticmethod
    def _is_urgent(job: JobRecord) -> int:
        text = "\n".join([job.source_title or "", job.requirements or "", job.arrival_time or ""]).lower()
        return int(any(token in text for token in URGENT_TOKENS))


class CommunicationAgent:
    def __init__(
        self,
        router: NotificationRouter,
        settings: Settings,
        llm_enricher: LLMEnricher | None = None,
        logger=None,
    ) -> None:
        self.router = router
        self.settings = settings
        self.llm_enricher = llm_enricher
        self.logger = logger

    def dispatch_batch(
        self,
        run_id: str,
        mode: str,
        jobs: list[JobRecord],
        resume_text: str,
        channel_names: list[str],
        attachments: list[str],
    ) -> BatchDispatchResult:
        if self.llm_enricher is None:
            raise RuntimeError("llm_enricher is required for dispatch_batch")
        summary = self.llm_enricher.summarize_push_batch(run_id=run_id, mode=mode, jobs=jobs, resume_text=resume_text)
        subject = self._build_subject(run_id=run_id, mode=mode, jobs=jobs, headline=summary.get("headline") or "")
        body = self._build_body(
            run_id=run_id,
            mode=mode,
            jobs=jobs,
            headline=summary.get("headline") or "",
            overview=summary.get("overview") or "",
            attachments=attachments,
        )
        logs = self.router.dispatch_digest(
            run_id=run_id,
            subject=subject,
            text=body,
            attachments=attachments,
            channel_names=channel_names,
        )
        opportunity_post_ids = [job.post_id for job in jobs if job.opportunity_point]
        return BatchDispatchResult(
            sent=bool(logs),
            logs=logs,
            subject=subject,
            body=body,
            opportunity_post_ids=opportunity_post_ids,
        )

    # backward compatibility
    def dispatch_realtime(self, run_id: str, summaries: list[SummaryRecord], channel_names: list[str]) -> list[SendLogRecord]:
        logs: list[SendLogRecord] = []
        for summary in summaries:
            logs.extend(self.router.dispatch_summary(run_id=run_id, summary=summary, channel_names=channel_names))
        return logs

    # backward compatibility
    def dispatch_digest(
        self,
        run_id: str,
        mode: str,
        new_notes: list[NoteRecord],
        target_notes: list[NoteRecord],
        summaries: list[SummaryRecord],
        attachments: list[str],
        channel_names: list[str],
    ) -> DigestDispatchResult:
        # Legacy dispatch_digest chain has been deprecated and disabled.
        # Batch notifications should be sent via dispatch_batch.
        return DigestDispatchResult(
            sent=False,
            logs=[],
            subject="",
            body="legacy dispatch_digest disabled",
        )

    @staticmethod
    def _format_multiline_block(text: str) -> str:
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return "（空）"

        lines = [line.rstrip() for line in raw.split("\n")]
        compact_lines: list[str] = []
        blank = False
        for line in lines:
            if not line.strip():
                if not blank:
                    compact_lines.append("")
                blank = True
                continue
            compact_lines.append(line)
            blank = False
        return "\n".join(compact_lines).strip()

    def _build_subject(self, run_id: str, mode: str, jobs: list[JobRecord], headline: str) -> str:
        opp = sum(1 for item in jobs if item.opportunity_point)
        prefix = f"SuccessionPilot batch | run={run_id} | jobs={len(jobs)} | opp={opp} | mode={mode}"
        if headline:
            return f"{prefix} | {headline[:48]}"
        return prefix

    def _build_body(
        self,
        run_id: str,
        mode: str,
        jobs: list[JobRecord],
        headline: str,
        overview: str,
        attachments: list[str],
    ) -> str:
        att = [Path(item).name for item in attachments if str(item).strip()]
        opp_jobs = [item for item in jobs if item.opportunity_point]

        lines = [
            "SuccessionPilot 批次推送",
            "====================",
            f"运行ID：{run_id}",
            f"运行模式：{mode}",
            f"岗位数量：{len(jobs)}",
            f"机会点数量：{len(opp_jobs)}",
            "",
            f"批次标题：{headline or '-'}",
            f"批次概览：{overview or '-'}",
            "",
            "附件：",
        ]
        if att:
            lines.extend([f"- {name}" for name in att])
        else:
            lines.append("- 无")

        lines.extend(["", "岗位详情："])
        for idx, job in enumerate(jobs, start=1):
            original_text = (job.original_text or "").strip() or (job.requirements or "")
            lines.append(f"----- {idx} -----")
            lines.append(f"公司：{job.company}")
            lines.append(f"岗位：{job.position}")
            lines.append(f"发布时间：{job.publish_time.strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"地点：{job.location}")
            lines.append(f"岗位要求：{job.requirements}")
            lines.append(f"到岗时间：{job.arrival_time}")
            lines.append(f"投递方式：{job.application_method}")
            lines.append(f"发布者：{job.author}")
            lines.append(f"简历匹配度：{job.match_score:.2f}")
            lines.append(f"原文：{original_text}")
            lines.append(f"链接：{job.link}")
            lines.append(f"机会点：{job.opportunity_point}")
            if job.outreach_message:
                lines.append(f"套磁文案：{job.outreach_message}")
            lines.append("")

        return "\n".join(lines).strip()
