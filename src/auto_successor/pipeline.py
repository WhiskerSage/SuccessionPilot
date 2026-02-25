from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from .agents import CommunicationAgent, IntelligenceAgent, PlannerAgent
from .config import Settings
from .email_sender import EmailSender
from .excel_store import ExcelStore, JOB_HEADERS
from .llm_client import LLMClient
from .llm_enricher import LLMEnricher
from .models import JobRecord, SummaryRecord
from .notification_router import NotificationChannel, NotificationRouter
from .resume_loader import ResumeLoader
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
        self.resume_loader = ResumeLoader(settings.resume, logger)

        channels = [
            NotificationChannel(name="wechat_service", sender=WeChatServiceSender(settings, logger)),
            NotificationChannel(name="email", sender=EmailSender(settings, logger)),
        ]
        self.router = NotificationRouter(channels=channels, logger=logger)
        self.planner = PlannerAgent(settings=settings, logger=logger)
        self.intelligence = IntelligenceAgent(llm_enricher=self.llm_enricher, logger=logger)
        self.communication = CommunicationAgent(
            router=self.router,
            settings=settings,
            llm_enricher=self.llm_enricher,
            logger=logger,
        )

    def run_once(self, run_id: str, mode: str = "auto") -> dict:
        keyword = self.settings.xhs.keyword
        mode = self._normalize_mode(mode or self.settings.agent.mode or "auto")
        notification_mode = self._normalize_notification_mode(self.settings.notification.mode)
        orchestrator = RuntimeOrchestrator(runtime_name=self.settings.agent.runtime_name, logger=self.logger)

        if not self.lock.acquire():
            self.logger.warning("跳过运行 | run=%s | 原因=检测到上一次运行锁未释放", run_id)
            return {"skipped": True, "reason": "run_locked"}

        try:
            self.logger.info("运行开始 | run=%s | keyword=%s | mode=%s | notify=%s", run_id, keyword, mode, notification_mode)
            self._log_progress(run_id, 5, "初始化运行上下文")
            self.llm_enricher.reset_stats()
            self.llm_client.clear_error_counts()

            resume_text = orchestrator.run_stage(
                "resume.load_text",
                lambda: self.resume_loader.load_resume_text(),
                meta={"resume_source": self.settings.resume.source_txt_path},
            )

            orchestrator.run_stage(
                "collector.ensure_logged_in",
                lambda: self.collector.ensure_logged_in(),
                meta={"browser_path": self.settings.xhs.browser_path},
            )
            self._log_progress(run_id, 12, "登录态检查完成")

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
            self._log_progress(run_id, 28, f"搜索完成，抓取到 {len(notes)} 条")

            pre_new_notes = orchestrator.run_stage(
                "state.prefilter_new_notes",
                lambda: [note for note in notes if not self.state.has(note.note_id)],
                meta={"existing_state_size": len(self.state.processed_note_ids)},
            )
            self._log_progress(run_id, 36, f"预过滤完成，候选新增 {len(pre_new_notes)} 条")

            initial_plan = self.planner.build_plan(mode=mode, fetched_count=len(notes), new_count=len(pre_new_notes))
            orchestrator.run_stage(
                "collector.enrich_note_details",
                lambda: self.collector.enrich_note_details(pre_new_notes, max_notes=initial_plan.detail_fetch_limit),
                meta={"max_detail_fetch": initial_plan.detail_fetch_limit},
            )
            self._log_progress(run_id, 46, f"正文补全完成，详情抓取上限 {initial_plan.detail_fetch_limit}")

            new_notes = orchestrator.run_stage(
                "state.filter_new_notes",
                lambda: [note for note in pre_new_notes if not self.state.has(note.note_id)],
                meta={"prefiltered_count": len(pre_new_notes)},
            )
            new_notes = sorted(new_notes, key=lambda n: n.publish_time, reverse=True)
            self._log_progress(run_id, 55, f"增量过滤完成，新增 {len(new_notes)} 条")

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
            llm_stage_calls = self.llm_enricher.stage_call_counts()
            llm_stage_fallbacks = self.llm_enricher.stage_fallback_counts()
            self._log_progress(
                run_id,
                66,
                (
                    f"目标筛选完成，命中 {len(target_notes)} 条，过滤 {len(filtered_out)} 条，"
                    f"LLM筛选调用 {int(llm_stage_calls.get('filter', 0))} 次，"
                    f"规则回退 {int(llm_stage_fallbacks.get('filter', 0))} 次"
                ),
            )

            jobs = orchestrator.run_stage(
                "agent.intelligence.build_jobs",
                lambda: self.intelligence.build_jobs(
                    target_notes,
                    max_job_items=plan.max_job_items,
                    resume_text=resume_text,
                    mode=mode,
                ),
                meta={"max_job_items": plan.max_job_items},
            )

            jobs = orchestrator.run_stage(
                "agent.intelligence.mark_opportunities",
                lambda: self.intelligence.mark_opportunities(jobs),
                meta={"jobs": len(jobs)},
            )

            jobs = orchestrator.run_stage(
                "agent.intelligence.attach_outreach_messages",
                lambda: self.intelligence.attach_outreach_messages(jobs, resume_text=resume_text),
                meta={"opportunity_jobs": sum(1 for item in jobs if item.opportunity_point)},
            )
            parse_details: list[dict[str, str]] = []
            job_parse_rule = 0
            job_parse_llm = 0
            for item in jobs:
                raw_parse_source = str(getattr(item, "parse_source", "") or "").strip().lower()[:20]
                parse_source = raw_parse_source if raw_parse_source in {"rule", "llm"} else "rule"
                if parse_source == "llm":
                    job_parse_llm += 1
                else:
                    job_parse_rule += 1
                parse_details.append({"post_id": item.post_id, "parse_source": parse_source})
                self.logger.info("岗位解析来源 | run=%s | post_id=%s | source=%s", run_id, item.post_id, parse_source)
            summaries = self._jobs_to_summary_records(run_id=run_id, jobs=jobs)
            llm_stage_calls = self.llm_enricher.stage_call_counts()
            llm_stage_fallbacks = self.llm_enricher.stage_fallback_counts()
            self._log_progress(
                run_id,
                80,
                (
                    f"岗位结构化完成，岗位 {len(jobs)} 条（LLM解析 {job_parse_llm}，规则解析 {job_parse_rule}），"
                    f"LLM提取调用 {int(llm_stage_calls.get('job', 0))} 次，"
                    f"规则回退 {int(llm_stage_fallbacks.get('job', 0))} 次"
                ),
            )

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
            self._log_progress(run_id, 88, "本地存储已更新（Excel/CSV）")

            send_logs = []
            notify_note_ids: list[str] = []
            digest_due = False
            digest_sent = False
            digest_subject = ""
            digest_channels: list[str] = []
            digest_attachments: list[str] = []
            opportunity_post_ids = [item.post_id for item in jobs if item.opportunity_point]

            if notification_mode == "realtime":
                if jobs:
                    dispatch_result = orchestrator.run_stage(
                        "agent.communication.batch_dispatch_realtime",
                        lambda: self._dispatch_batch_with_compat(
                            run_id=run_id,
                            mode=mode,
                            jobs=jobs,
                            top_n=plan.top_n,
                            resume_text=resume_text,
                            channel_names=list(self.settings.notification.realtime_channels),
                            attachments=[],
                            digest_style=False,
                        ),
                        meta={
                            "mode": mode,
                            "channels": list(self.settings.notification.realtime_channels),
                            "job_count": len(jobs),
                        },
                    )
                    send_logs = dispatch_result["logs"]
                    notify_note_ids = sorted({log.note_id for log in send_logs})
                    digest_subject = dispatch_result["subject"]
                self._log_progress(run_id, 94, f"实时通知完成，发送日志 {len(send_logs)} 条")

            elif notification_mode == "digest":
                now = datetime.now(timezone.utc)
                digest_due = self._is_digest_due(now)
                enough_new = len(new_notes) >= max(0, int(self.settings.notification.digest_min_new_notes))
                allow_no_new = bool(self.settings.notification.digest_send_when_no_new)
                if digest_due and (enough_new or allow_no_new) and jobs:
                    digest_attachments = self._collect_digest_attachments()
                    digest_channels = list(self.settings.notification.digest_channels)
                    dispatch_result = orchestrator.run_stage(
                        "agent.communication.batch_dispatch_digest",
                        lambda: self._dispatch_batch_with_compat(
                            run_id=run_id,
                            mode=mode,
                            jobs=jobs,
                            top_n=plan.top_n,
                            resume_text=resume_text,
                            channel_names=digest_channels,
                            attachments=digest_attachments,
                            digest_style=True,
                        ),
                        meta={
                            "channels": digest_channels,
                            "attachment_count": len(digest_attachments),
                            "new_notes": len(new_notes),
                            "target_notes": len(target_notes),
                        },
                    )
                    send_logs = dispatch_result["logs"]
                    notify_note_ids = sorted({log.note_id for log in send_logs})
                    digest_subject = dispatch_result["subject"]
                    digest_sent = any(
                        str(getattr(log, "send_status", "")).strip().lower() == "success"
                        for log in send_logs
                    )
                    if digest_sent:
                        self._mark_digest_sent(now, run_id)
                if digest_due and (enough_new or allow_no_new):
                    self._log_progress(run_id, 94, f"摘要通知完成，发送日志 {len(send_logs)} 条")
                else:
                    self._log_progress(run_id, 94, "摘要通知按策略跳过（未到时间窗或新增不足）")
            else:
                self._log_progress(run_id, 94, "通知已关闭")

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
            self._log_progress(run_id, 100, "本轮运行完成")

            stage_records = orchestrator.stage_records()
            stage_timing = self._summarize_stage_timing(stage_records)
            stage_error_codes = self._collect_stage_error_codes(stage_records)
            llm_error_codes = self.llm_client.error_counts()
            llm_stage_calls = self.llm_enricher.stage_call_counts()
            llm_stage_fallbacks = self.llm_enricher.stage_fallback_counts()
            llm_fallback_total = sum(int(v) for v in llm_stage_fallbacks.values())

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
                "opportunities": len(opportunity_post_ids),
                "summaries": len(jobs),
                "send_logs": len(send_logs),
                "stages": len(stage_records),
                "stage_total_ms": stage_timing["total_ms"],
                "stage_avg_ms": stage_timing["avg_ms"],
                "stage_failed_count": stage_timing["failed_count"],
                "stage_slowest": stage_timing["slowest"],
                "stage_top_slow": stage_timing["top_slow"],
                "llm_enabled": self.llm_client.is_enabled(),
                "llm_available": self.llm_client.is_available(),
                "llm_calls": self.llm_enricher.calls,
                "llm_success": self.llm_enricher.success,
                "llm_fail": self.llm_enricher.fail,
                "llm_error_codes": llm_error_codes,
                "llm_stage_calls": llm_stage_calls,
                "llm_stage_fallbacks": llm_stage_fallbacks,
                "llm_fallback_total": llm_fallback_total,
                "stage_error_codes": stage_error_codes,
                "job_parse_rule": job_parse_rule,
                "job_parse_llm": job_parse_llm,
                "job_parse_details_count": len(parse_details),
                "digest_due": digest_due,
                "digest_sent": digest_sent,
                "resume_chars": len(resume_text),
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
                    "opportunity_post_ids": opportunity_post_ids,
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
                    "job_parse": {
                        "rule": job_parse_rule,
                        "llm": job_parse_llm,
                        "details_count": len(parse_details),
                        "details": parse_details,
                    },
                    "stage_records": stage_records,
                },
            )
            self.logger.info(
                "LLM统计 | run=%s | 调用=%s | 成功=%s | 失败=%s | 阶段调用=%s | 阶段回退=%s",
                run_id,
                self.llm_enricher.calls,
                self.llm_enricher.success,
                self.llm_enricher.fail,
                llm_stage_calls,
                llm_stage_fallbacks,
            )
            self.logger.info("运行结束 | run=%s | stats=%s", run_id, stats)
            return stats
        finally:
            self.lock.release()

    def _log_progress(self, run_id: str, percent: int, message: str) -> None:
        pct = max(0, min(100, int(percent)))
        width = 24
        done = max(0, min(width, int(round(pct * width / 100))))
        bar = f"{'#' * done}{'-' * (width - done)}"
        self.logger.info("运行进度 | run=%s | [%s] %3d%% | %s", run_id, bar, pct, message)

    def send_latest_stored(self, run_id: str, limit: int = 5) -> dict:
        mode = self._normalize_mode(self.settings.agent.mode or "auto")

        if not self.lock.acquire():
            self.logger.warning("跳过发送 | run=%s | 原因=检测到上一次运行锁未释放", run_id)
            return {"skipped": True, "reason": "run_locked"}

        try:
            top_n = max(1, int(limit))
            self._log_progress(run_id, 8, f"准备发送本地最新岗位，目标条数 {top_n}")
            summaries = list(self._load_latest_summaries_from_store(limit=top_n) or [])
            if summaries:
                jobs = self._summaries_to_jobs(summaries)
            else:
                jobs = self._load_latest_jobs_from_store(limit=top_n)
            self._log_progress(run_id, 32, f"已加载本地岗位 {len(jobs)} 条")
            resume_text = self.resume_loader.load_resume_text()
            digest_attachments = self._collect_digest_attachments()
            digest_channels = list(self.settings.notification.digest_channels)

            if not jobs:
                stats = {
                    "runtime_name": self.settings.agent.runtime_name,
                    "action": "send_latest_stored",
                    "requested_limit": top_n,
                    "loaded_jobs": 0,
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
                self._log_progress(run_id, 100, "无可发送岗位，任务结束")
                self.logger.info("手动发送完成 | run=%s | stats=%s", run_id, stats)
                return stats

            dispatch_result = self._dispatch_batch_with_compat(
                run_id=run_id,
                mode=mode,
                jobs=jobs,
                top_n=top_n,
                resume_text=resume_text,
                channel_names=digest_channels,
                attachments=digest_attachments,
                digest_style=True,
            )
            self._log_progress(run_id, 72, "通知分发执行完成，正在写入发送日志")
            send_logs = dispatch_result["logs"]
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
                "loaded_jobs": len(jobs),
                "loaded_summaries": len(summaries) if summaries else len(jobs),
                "send_logs": len(send_logs),
                "digest_sent": digest_sent,
            }
            self.journal.write(
                run_id,
                {
                    "stats": stats,
                    "mode": mode,
                    "notification_mode": "digest",
                    "target_note_ids": [item.post_id for item in jobs],
                    "notify_note_ids": notify_note_ids,
                    "digest": {
                        "subject": dispatch_result["subject"],
                        "channels": digest_channels,
                        "attachments": digest_attachments,
                    },
                },
            )
            self._log_progress(run_id, 100, f"发送任务完成，发送日志 {len(send_logs)} 条")
            self.logger.info("手动发送完成 | run=%s | stats=%s", run_id, stats)
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

    def _load_latest_jobs_from_store(self, limit: int) -> list[JobRecord]:
        excel_path = Path(self.settings.storage.excel_path)
        if not excel_path.exists():
            return []

        wb = load_workbook(excel_path, read_only=True, data_only=True)
        try:
            if "jobs" not in wb.sheetnames:
                return []
            ws = wb["jobs"]
            rows = self._read_sheet_rows(ws)
        finally:
            wb.close()

        rows.sort(
            key=lambda item: (
                str(item.get("publish_time") or ""),
                str(item.get("PostID") or ""),
            ),
            reverse=True,
        )

        jobs: list[JobRecord] = []
        for row in rows[: max(1, int(limit))]:
            post_id = str(row.get("PostID") or "").strip()
            if not post_id:
                continue
            jobs.append(
                JobRecord(
                    run_id=str(row.get("run_id") or f"from-store:{post_id[:12]}"),
                    post_id=post_id,
                    company=str(row.get("Company") or ""),
                    position=str(row.get("Position") or ""),
                    location=str(row.get("Location") or ""),
                    requirements=str(row.get("Requirements") or ""),
                    arrival_time=str(row.get("arrival_time") or ""),
                    application_method=str(row.get("application_method") or ""),
                    author=str(row.get("author") or ""),
                    risk_line=str(row.get("risk_line") or "low"),
                    match_score=float(row.get("match_score") or 0.0),
                    match_reason=str(row.get("match_reason") or ""),
                    link=str(row.get("Link") or ""),
                    mode=str(row.get("mode") or "auto"),
                    publish_time=self._to_datetime(row.get("publish_time")),
                    source_title=str(row.get("source_title") or ""),
                    comment_count=int(row.get("comment_count") or 0),
                    comments_preview=str(row.get("comments_preview") or ""),
                    original_text=str(row.get("original_text") or ""),
                    opportunity_point=bool(row.get("opportunity_point")),
                    outreach_message=str(row.get("outreach_message") or ""),
                )
            )
        return jobs

    def _dispatch_batch_with_compat(
        self,
        *,
        run_id: str,
        mode: str,
        jobs: list[JobRecord],
        top_n: int,
        resume_text: str,
        channel_names: list[str],
        attachments: list[str],
        digest_style: bool,
    ) -> dict:
        if hasattr(self.communication, "dispatch_batch"):
            result = self.communication.dispatch_batch(
                run_id=run_id,
                mode=mode,
                jobs=jobs,
                resume_text=resume_text,
                channel_names=channel_names,
                attachments=attachments,
            )
            return {"logs": result.logs, "subject": result.subject}

        realtime_jobs = jobs
        if not digest_style and mode == "agent":
            realtime_jobs = sorted(jobs, key=lambda item: float(item.match_score), reverse=True)[: max(1, int(top_n))]
        summaries = self._jobs_to_summary_records(run_id=run_id, jobs=realtime_jobs)
        if digest_style:
            result = self.communication.dispatch_digest(
                run_id=run_id,
                mode=mode,
                new_notes=[],
                target_notes=[],
                summaries=summaries,
                attachments=attachments,
                channel_names=channel_names,
            )
            return {"logs": result.logs, "subject": result.subject}

        logs = self.communication.dispatch_realtime(
            run_id=run_id,
            summaries=summaries,
            channel_names=channel_names,
        )
        return {"logs": logs, "subject": ""}

    def _jobs_to_summary_records(self, run_id: str, jobs: list[JobRecord]) -> list[SummaryRecord]:
        output: list[SummaryRecord] = []
        for item in jobs:
            original_text = (item.original_text or "").strip()
            if not original_text:
                original_text = item.requirements or ""
            summary_text = (
                f"公司：{item.company}\n"
                f"岗位：{item.position}\n"
                f"地点：{item.location}\n"
                f"岗位要求：{item.requirements}\n"
                f"到岗时间：{item.arrival_time}\n"
                f"投递方式：{item.application_method}\n"
                f"风险等级：{item.risk_line}\n"
                f"简历匹配度：{item.match_score:.2f}\n"
                f"原文：{original_text}"
            )
            output.append(
                SummaryRecord(
                    run_id=run_id,
                    note_id=item.post_id,
                    keyword=self.settings.xhs.keyword,
                    publish_time=item.publish_time,
                    title=item.source_title or item.position,
                    author=item.author,
                    summary=summary_text,
                    confidence=1.0,
                    risk_flags=item.risk_line,
                    url=item.link,
                )
            )
        return output

    def _summaries_to_jobs(self, summaries: list[SummaryRecord]) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        for item in summaries:
            jobs.append(
                JobRecord(
                    run_id=item.run_id,
                    post_id=item.note_id,
                    company="",
                    position=item.title or "",
                    location="",
                    requirements=item.summary or "",
                    link=item.url,
                    publish_time=item.publish_time,
                    source_title=item.title,
                    comment_count=0,
                    comments_preview="",
                    original_text=item.summary or "",
                    author=item.author,
                    risk_line=item.risk_flags or "low",
                    match_score=0.0,
                    mode=self._normalize_mode(self.settings.agent.mode or "auto"),
                )
            )
        return jobs

    # backward compatibility for tests/callers
    def _load_latest_summaries_from_store(self, limit: int):
        jobs = self._load_latest_jobs_from_store(limit=limit)
        return self._jobs_to_summary_records(run_id="from-store", jobs=jobs)

    @staticmethod
    def _read_sheet_rows(ws) -> list[dict[str, Any]]:
        iterator = ws.iter_rows(values_only=True)
        try:
            headers_row = next(iterator)
        except StopIteration:
            return []
        headers = [str(x or "").strip() for x in headers_row]
        if not any(headers):
            headers = list(JOB_HEADERS)

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

    @staticmethod
    def _summarize_stage_timing(stage_records: list[dict[str, Any]]) -> dict[str, Any]:
        normalized: list[dict[str, Any]] = []
        failed_count = 0
        total_ms = 0

        for item in stage_records or []:
            name = str(item.get("name") or "").strip()
            status = str(item.get("status") or "").strip().lower()
            try:
                duration_ms = int(item.get("duration_ms") or 0)
            except Exception:
                duration_ms = 0
            duration_ms = max(0, duration_ms)
            total_ms += duration_ms
            if status == "failed":
                failed_count += 1
            normalized.append(
                {
                    "name": name,
                    "duration_ms": duration_ms,
                    "status": status or "success",
                }
            )

        count = len(normalized)
        avg_ms = int(total_ms / count) if count > 0 else 0
        top = sorted(normalized, key=lambda x: int(x.get("duration_ms") or 0), reverse=True)[:3]
        slowest = top[0] if top else {"name": "", "duration_ms": 0, "status": ""}

        return {
            "total_ms": total_ms,
            "avg_ms": avg_ms,
            "failed_count": failed_count,
            "slowest": slowest,
            "top_slow": top,
        }

    @staticmethod
    def _collect_stage_error_codes(stage_records: list[dict[str, Any]]) -> dict[str, int]:
        counters: dict[str, int] = {}
        for item in stage_records or []:
            status = str(item.get("status") or "").strip().lower()
            if status != "failed":
                continue
            code = str(item.get("error_code") or "").strip().lower() or "stage_failed"
            counters[code] = int(counters.get(code, 0)) + 1
        return counters
