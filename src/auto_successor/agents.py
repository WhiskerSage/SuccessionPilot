from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .job_processor import normalize_job_record, to_job_record
from .llm_enricher import LLMEnricher
from .models import NoteRecord, SendLogRecord, SummaryRecord
from .notification_router import NotificationRouter
from .succession import build_summary


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

    def build_jobs(self, notes: list[NoteRecord], max_job_items: int) -> list:
        jobs = []
        for idx, note in enumerate(notes):
            job = to_job_record(note)
            if idx < max(0, int(max_job_items)):
                job = self.llm_enricher.enrich_job(note, job)
            jobs.append(normalize_job_record(job))
        jobs.sort(key=lambda item: item.publish_time, reverse=True)
        return jobs

    def build_summaries(self, notes: list[NoteRecord], max_summary_items: int, mode: str) -> list[SummaryRecord]:
        summaries: list[SummaryRecord] = []
        for idx, note in enumerate(notes):
            summary = build_summary(note)
            if idx < max(0, int(max_summary_items)):
                summary = self.llm_enricher.enrich_summary(note, summary, mode=mode)
            summaries.append(summary)
        return summaries

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


class CommunicationAgent:
    def __init__(self, router: NotificationRouter, settings: Settings, logger) -> None:
        self.router = router
        self.settings = settings
        self.logger = logger

    def dispatch_realtime(self, run_id: str, summaries: list[SummaryRecord], channel_names: list[str]) -> list[SendLogRecord]:
        logs: list[SendLogRecord] = []
        for summary in summaries:
            logs.extend(self.router.dispatch_summary(run_id=run_id, summary=summary, channel_names=channel_names))
        return logs

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
        subject = self._build_digest_subject(run_id=run_id, mode=mode, new_count=len(new_notes), target_count=len(target_notes))
        body = self._build_digest_body(
            run_id=run_id,
            mode=mode,
            new_notes=new_notes,
            target_notes=target_notes,
            summaries=summaries,
            attachments=attachments,
        )
        logs = self.router.dispatch_digest(
            run_id=run_id,
            subject=subject,
            text=body,
            attachments=attachments,
            channel_names=channel_names,
        )
        return DigestDispatchResult(sent=bool(logs), logs=logs, subject=subject, body=body)

    def _build_digest_subject(self, run_id: str, mode: str, new_count: int, target_count: int) -> str:
        return f"SuccessionPilot digest | run={run_id} | new={new_count} | target={target_count} | mode={mode}"

    def _build_digest_body(
        self,
        run_id: str,
        mode: str,
        new_notes: list[NoteRecord],
        target_notes: list[NoteRecord],
        summaries: list[SummaryRecord],
        attachments: list[str],
    ) -> str:
        top_n = max(1, int(self.settings.notification.digest_top_summaries))
        included = summaries[:top_n]
        attachment_items = [Path(item).name for item in attachments if str(item).strip()]

        lines = [
            "SuccessionPilot 定时摘要",
            "====================",
            "",
            "【统计】",
            f"- 新增线索：{len(new_notes)}",
            f"- 命中目标：{len(target_notes)}",
            f"- 收录摘要：{len(included)} / {len(summaries)}",
            "",
            "【附件】",
        ]
        if attachment_items:
            lines.extend([f"- {name}" for name in attachment_items])
        else:
            lines.append("- 无")

        lines.extend(["", "【岗位详情】"])
        if not included:
            lines.append("暂无可发送岗位摘要（本轮可能无新命中或全部被过滤）。")
            return "\n".join(lines).strip()

        for idx, summary in enumerate(included, start=1):
            publish = summary.publish_time.strftime("%Y-%m-%d %H:%M")
            lines.append(f"-------------------- {idx} --------------------")
            lines.append(f"标题：{summary.title or '（无标题）'}")
            lines.append(f"作者：{summary.author or '未知'}")
            lines.append(f"发布时间：{publish}")
            lines.append(f"链接：{summary.url}")
            if summary.risk_flags:
                lines.append(f"风险标签：{summary.risk_flags}")
            lines.append("")
            lines.append("摘要内容：")
            lines.append(self._format_multiline_block(summary.summary))
            lines.append("")

        return "\n".join(lines).strip()

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
