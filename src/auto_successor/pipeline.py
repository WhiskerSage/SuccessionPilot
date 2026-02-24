from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .agents import CommunicationAgent, IntelligenceAgent, PlannerAgent
from .config import Settings
from .email_sender import EmailSender
from .excel_store import ExcelStore, SUMMARY_HEADERS
from .llm_client import LLMClient
from .llm_enricher import LLMEnricher
from .models import SummaryRecord
from .notification_router import NotificationChannel, NotificationRouter
from .run_journal import RunJournal
from .run_lock import RunLock
from .runtime_orchestrator import RuntimeOrchestrator
from .state_store import StateStore
from .wechat_service_sender import WeChatServiceSender
from .xhs_collector import XHSMcpCliCollector


class AutoSuccessorPipeline:
    """
    SuccessionPilot runtime:
    - collector layer
    - agent layer (planner/intelligence/communication)
    - storage + snapshot
    """

    def __init__(self, settings: Settings, logger) -> None:
        self.settings = settings
        self.logger = logger
        self.collector = XHSMcpCliCollector(settings.xhs, settings.app.timezone, logger)
        self.store = ExcelStore(settings.storage.excel_path)
        self.state = StateStore(settings.storage.state_path)
        self.journal = RunJournal()
        self.lock = RunLock()
        self.llm_client = LLMClient(settings=settings, logger=logger)
        self.llm_enricher = LLMEnricher(llm_client=self.llm_client, settings=settings, logger=logger)

        channels = [
            NotificationChannel(name="wechat_service", sender=WeChatServiceSender(settings, logger)),
            NotificationChannel(name="email", sender=EmailSender(settings, logger)),
        ]
        self.router = NotificationRouter(channels=channels, logger=logger)
        self.planner = PlannerAgent(settings=settings, logger=logger)
        self.intelligence = IntelligenceAgent(llm_enricher=self.llm_enricher, logger=logger)
        self.communication = CommunicationAgent(router=self.router, settings=settings, logger=logger)

    def run_once(self, run_id: str, mode: str = "auto") -> dict:
        keyword = self.settings.xhs.keyword
        mode = self._normalize_mode(mode or self.settings.agent.mode or "auto")
        notification_mode = self._normalize_notification_mode(self.settings.notification.mode)
        orchestrator = RuntimeOrchestrator(runtime_name=self.settings.agent.runtime_name, logger=self.logger)

        if not self.lock.acquire():
            self.logger.warning("skip run %s because previous run lock exists", run_id)
            return {"skipped": True, "reason": "run_locked"}

        try:
            self.logger.info("run %s started, keyword=%s mode=%s notify=%s", run_id, keyword, mode, notification_mode)
            self.llm_enricher.reset_stats()

            orchestrator.run_stage(
                "collector.ensure_logged_in",
                lambda: self.collector.ensure_logged_in(),
                meta={"browser_path": self.settings.xhs.browser_path},
            )
            notes = orchestrator.run_stage(
                "collector.search_notes",
                lambda: self.collector.search_notes(
                    run_id=run_id,
                    keyword=keyword,
                    max_results=self.settings.xhs.max_results,
                ),
                meta={"keyword": keyword, "max_results": self.settings.xhs.max_results},
            )
            notes = sorted(notes, key=lambda n: n.publish_time, reverse=True)

            pre_new_notes = orchestrator.run_stage(
                "state.prefilter_new_notes",
                lambda: [note for note in notes if not self.state.has(note.note_id)],
                meta={"existing_state_size": len(self.state.processed_note_ids)},
            )

            initial_plan = self.planner.build_plan(mode=mode, fetched_count=len(notes), new_count=len(pre_new_notes))
            orchestrator.run_stage(
                "collector.enrich_note_details",
                lambda: self.collector.enrich_note_details(pre_new_notes, max_notes=initial_plan.detail_fetch_limit),
                meta={"max_detail_fetch": initial_plan.detail_fetch_limit},
            )

            new_notes = orchestrator.run_stage(
                "state.filter_new_notes",
                lambda: [note for note in pre_new_notes if not self.state.has(note.note_id)],
                meta={"prefiltered_count": len(pre_new_notes)},
            )
            new_notes = sorted(new_notes, key=lambda n: n.publish_time, reverse=True)

            plan = orchestrator.run_stage(
                "agent.planner.build_plan",
                lambda: self.planner.build_plan(mode=mode, fetched_count=len(notes), new_count=len(new_notes)),
                meta={"mode": mode},
            )

            filter_outcome = orchestrator.run_stage(
                "agent.intelligence.filter_target_notes",
                lambda: self.intelligence.filter_target_notes(new_notes, max_filter_items=plan.max_filter_items),
                meta={"max_filter_items": plan.max_filter_items},
            )
            target_notes = filter_outcome.targets
            filtered_out = filter_outcome.filtered_out
            target_scores = filter_outcome.scores

            jobs = orchestrator.run_stage(
                "agent.intelligence.build_jobs",
                lambda: self.intelligence.build_jobs(target_notes, max_job_items=plan.max_job_items),
                meta={"max_job_items": plan.max_job_items},
            )

            summary_mode = mode if plan.include_jd_full else "auto"
            summaries = orchestrator.run_stage(
                "agent.intelligence.build_summaries",
                lambda: self.intelligence.build_summaries(
                    target_notes,
                    max_summary_items=plan.max_summary_items,
                    mode=summary_mode,
                ),
                meta={"max_summary_items": plan.max_summary_items, "mode": summary_mode},
            )
            summary_by_note_id = {item.note_id: item for item in summaries}
            ranked_targets = self.intelligence.rank_targets(target_notes, scores=target_scores, top_n=plan.top_n)
            ranked_summaries = [summary_by_note_id[note.note_id] for note in ranked_targets if note.note_id in summary_by_note_id]

            orchestrator.run_stage(
                "storage.write_excel",
                lambda: self.store.write(new_notes, summaries, [], jobs=jobs),
                meta={"excel_path": self.settings.storage.excel_path},
            )
            orchestrator.run_stage(
                "storage.export_jobs_csv",
                lambda: self.store.export_jobs_csv(self.settings.storage.jobs_csv_path),
                meta={"jobs_csv_path": self.settings.storage.jobs_csv_path},
            )

            send_logs = []
            notify_note_ids: list[str] = []
            digest_due = False
            digest_sent = False
            digest_subject = ""
            digest_channels: list[str] = []
            digest_attachments: list[str] = []

            if notification_mode == "realtime":
                realtime_candidates = summaries if mode == "auto" else ranked_summaries
                send_logs = orchestrator.run_stage(
                    "agent.communication.realtime_dispatch",
                    lambda: self.communication.dispatch_realtime(
                        run_id=run_id,
                        summaries=realtime_candidates,
                        channel_names=list(self.settings.notification.realtime_channels),
                    ),
                    meta={
                        "mode": mode,
                        "channels": list(self.settings.notification.realtime_channels),
                        "summary_count": len(realtime_candidates),
                    },
                )
                notify_note_ids = sorted({log.note_id for log in send_logs})
            elif notification_mode == "digest":
                now = datetime.now(timezone.utc)
                digest_due = self._is_digest_due(now)
                enough_new = len(new_notes) >= max(0, int(self.settings.notification.digest_min_new_notes))
                allow_no_new = bool(self.settings.notification.digest_send_when_no_new)
                if digest_due and (enough_new or allow_no_new):
                    digest_attachments = self._collect_digest_attachments()
                    digest_channels = list(self.settings.notification.digest_channels)
                    digest_result = orchestrator.run_stage(
                        "agent.communication.digest_dispatch",
                        lambda: self.communication.dispatch_digest(
                            run_id=run_id,
                            mode=mode,
                            new_notes=new_notes,
                            target_notes=target_notes,
                            summaries=ranked_summaries or summaries,
                            attachments=digest_attachments,
                            channel_names=digest_channels,
                        ),
                        meta={
                            "channels": digest_channels,
                            "attachment_count": len(digest_attachments),
                            "new_notes": len(new_notes),
                            "target_notes": len(target_notes),
                        },
                    )
                    send_logs = digest_result.logs
                    notify_note_ids = sorted({log.note_id for log in send_logs})
                    digest_subject = digest_result.subject
                    digest_sent = any(
                        str(getattr(log, "send_status", "")).strip().lower() == "success"
                        for log in send_logs
                    )
                    if digest_sent:
                        self._mark_digest_sent(now, run_id)

            if send_logs:
                orchestrator.run_stage(
                    "storage.append_send_logs",
                    lambda: self.store.write(raw=[], summaries=[], send_logs=send_logs, jobs=[]),
                    meta={"send_logs": len(send_logs)},
                )

            def _persist_state():
                for note in new_notes:
                    self.state.mark(note.note_id)
                self.state.save()

            orchestrator.run_stage("state.persist", _persist_state, meta={"marked_count": len(new_notes)})

            stats = {
                "runtime_name": self.settings.agent.runtime_name,
                "mode": mode,
                "notification_mode": notification_mode,
                "fetched": len(notes),
                "new_notes": len(new_notes),
                "target_notes": len(target_notes),
                "filtered_out": len(filtered_out),
                "notify_note_count": len(notify_note_ids),
                "jobs": len(jobs),
                "summaries": len(summaries),
                "send_logs": len(send_logs),
                "stages": len(orchestrator.stage_records()),
                "llm_enabled": self.llm_client.is_enabled(),
                "llm_available": self.llm_client.is_available(),
                "llm_calls": self.llm_enricher.calls,
                "llm_success": self.llm_enricher.success,
                "llm_fail": self.llm_enricher.fail,
                "digest_due": digest_due,
                "digest_sent": digest_sent,
            }
            self.journal.write(
                run_id,
                {
                    "stats": stats,
                    "keyword": keyword,
                    "mode": mode,
                    "notification_mode": notification_mode,
                    "new_note_ids": [note.note_id for note in new_notes],
                    "target_note_ids": [note.note_id for note in target_notes],
                    "notify_note_ids": notify_note_ids,
                    "filtered_out_samples": filtered_out[:50],
                    "agent_plan": {
                        "detail_fetch_limit": plan.detail_fetch_limit,
                        "max_filter_items": plan.max_filter_items,
                        "max_job_items": plan.max_job_items,
                        "max_summary_items": plan.max_summary_items,
                        "top_n": plan.top_n,
                    },
                    "digest": {
                        "subject": digest_subject,
                        "channels": digest_channels,
                        "attachments": digest_attachments,
                    },
                    "stage_records": orchestrator.stage_records(),
                },
            )
            self.logger.info("run %s finished: %s", run_id, stats)
            return stats
        finally:
            self.lock.release()

    def send_latest_stored(self, run_id: str, limit: int = 5) -> dict:
        mode = self._normalize_mode(self.settings.agent.mode or "auto")

        if not self.lock.acquire():
            self.logger.warning("skip manual send %s because previous run lock exists", run_id)
            return {"skipped": True, "reason": "run_locked"}

        try:
            top_n = max(1, int(limit))
            summaries = self._load_latest_summaries_from_store(limit=top_n)
            digest_attachments = self._collect_digest_attachments()
            digest_channels = list(self.settings.notification.digest_channels)

            if not summaries:
                stats = {
                    "runtime_name": self.settings.agent.runtime_name,
                    "action": "send_latest_stored",
                    "requested_limit": top_n,
                    "loaded_summaries": 0,
                    "send_logs": 0,
                    "digest_sent": False,
                }
                self.journal.write(
                    run_id,
                    {
                        "stats": stats,
                        "mode": mode,
                        "notification_mode": "digest",
                        "target_note_ids": [],
                        "notify_note_ids": [],
                        "digest": {
                            "subject": "",
                            "channels": digest_channels,
                            "attachments": digest_attachments,
                        },
                    },
                )
                self.logger.info("manual send %s finished: %s", run_id, stats)
                return stats

            digest_result = self.communication.dispatch_digest(
                run_id=run_id,
                mode=mode,
                new_notes=[],
                target_notes=[],
                summaries=summaries,
                attachments=digest_attachments,
                channel_names=digest_channels,
            )
            send_logs = digest_result.logs
            digest_sent = any(str(getattr(log, "send_status", "")).strip().lower() == "success" for log in send_logs)

            if send_logs:
                self.store.write(raw=[], summaries=[], send_logs=send_logs, jobs=[])

            if digest_sent:
                now = datetime.now(timezone.utc)
                self._mark_digest_sent(now, run_id)
                self.state.save()

            notify_note_ids = sorted({log.note_id for log in send_logs})
            stats = {
                "runtime_name": self.settings.agent.runtime_name,
                "action": "send_latest_stored",
                "requested_limit": top_n,
                "loaded_summaries": len(summaries),
                "send_logs": len(send_logs),
                "digest_sent": digest_sent,
            }
            self.journal.write(
                run_id,
                {
                    "stats": stats,
                    "mode": mode,
                    "notification_mode": "digest",
                    "target_note_ids": [item.note_id for item in summaries],
                    "notify_note_ids": notify_note_ids,
                    "digest": {
                        "subject": digest_result.subject,
                        "channels": digest_channels,
                        "attachments": digest_attachments,
                    },
                },
            )
            self.logger.info("manual send %s finished: %s", run_id, stats)
            return stats
        finally:
            self.lock.release()

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        value = (mode or "auto").strip().lower()
        if value == "smart":
            value = "agent"
        if value not in {"auto", "agent"}:
            return "auto"
        return value

    @staticmethod
    def _normalize_notification_mode(mode: str) -> str:
        value = (mode or "digest").strip().lower()
        if value not in {"digest", "realtime", "off"}:
            return "digest"
        return value

    def _collect_digest_attachments(self) -> list[str]:
        paths: list[str] = []
        if self.settings.notification.attach_excel:
            excel = Path(self.settings.storage.excel_path)
            if excel.exists():
                paths.append(str(excel))
        if self.settings.notification.attach_jobs_csv:
            jobs_csv = Path(self.settings.storage.jobs_csv_path)
            if jobs_csv.exists():
                paths.append(str(jobs_csv))
        return paths

    def _is_digest_due(self, now: datetime) -> bool:
        interval = int(self.settings.notification.digest_interval_minutes)
        if hasattr(self.state, "is_digest_due"):
            return bool(self.state.is_digest_due(now, interval))
        return True

    def _mark_digest_sent(self, now: datetime, run_id: str) -> None:
        if hasattr(self.state, "mark_digest_sent"):
            self.state.mark_digest_sent(now, run_id)

    def _load_latest_summaries_from_store(self, limit: int) -> list[SummaryRecord]:
        excel_path = Path(self.settings.storage.excel_path)
        if not excel_path.exists():
            return []

        wb = load_workbook(excel_path, read_only=True, data_only=True)
        try:
            if "succession_summary" not in wb.sheetnames:
                return []
            ws = wb["succession_summary"]
            rows = self._read_sheet_rows(ws)
        finally:
            wb.close()

        rows.sort(
            key=lambda item: (
                int(item.get("publish_timestamp") or 0),
                str(item.get("publish_time") or ""),
                str(item.get("created_at") or ""),
            ),
            reverse=True,
        )

        summaries: list[SummaryRecord] = []
        for row in rows[: max(1, int(limit))]:
            note_id = str(row.get("note_id") or "").strip()
            if not note_id:
                continue
            try:
                confidence = float(row.get("confidence") or 1.0)
            except Exception:
                confidence = 1.0
            summaries.append(
                SummaryRecord(
                    run_id=str(row.get("run_id") or f"from-store:{note_id[:12]}"),
                    note_id=note_id,
                    keyword=str(row.get("keyword") or ""),
                    publish_time=self._to_datetime(row.get("publish_time")),
                    title=str(row.get("title") or ""),
                    author=str(row.get("author") or ""),
                    summary=str(row.get("summary") or ""),
                    confidence=confidence,
                    risk_flags=str(row.get("risk_flags") or ""),
                    url=str(row.get("url") or ""),
                    created_at=self._to_datetime(row.get("created_at")),
                )
            )
        return summaries

    @staticmethod
    def _read_sheet_rows(ws) -> list[dict[str, Any]]:
        iterator = ws.iter_rows(values_only=True)
        try:
            headers_row = next(iterator)
        except StopIteration:
            return []
        headers = [str(x or "").strip() for x in headers_row]
        if not any(headers):
            headers = list(SUMMARY_HEADERS)

        rows: list[dict[str, Any]] = []
        for values in iterator:
            if not values:
                continue
            row: dict[str, Any] = {}
            for idx, value in enumerate(values):
                if idx >= len(headers):
                    break
                key = headers[idx]
                if key:
                    row[key] = value
            rows.append(row)
        return rows

    @staticmethod
    def _to_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            dt = value
        else:
            text = str(value or "").strip()
            if not text:
                return datetime.now(timezone.utc)
            try:
                dt = datetime.fromisoformat(text)
            except Exception:
                return datetime.now(timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
