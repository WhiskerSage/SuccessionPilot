from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agents import CommunicationAgent, IntelligenceAgent, PlannerAgent
from .config import Settings
from .email_sender import EmailSender
from .excel_store import ExcelStore
from .llm_client import LLMClient
from .llm_enricher import LLMEnricher
from .notification_router import NotificationChannel, NotificationRouter
from .retry_queue import RetryQueue
from .resume_loader import ResumeLoader
from .run_journal import RunJournal
from .run_lock import RunLock
from .runtime_orchestrator import RuntimeOrchestrator
from .state_store import StateStore
from .wechat_service_sender import WeChatServiceSender
from .xhs_collector import XHSMcpCliCollector
from .pipeline_service import PipelineServiceMixin


class AutoSuccessorPipeline(PipelineServiceMixin):
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
        self.retry_queue = RetryQueue(
            path=settings.storage.retry_queue_path,
            base_backoff_seconds=settings.retry.base_backoff_seconds,
            max_backoff_seconds=settings.retry.max_backoff_seconds,
            max_attempts_by_type={
                "fetch": settings.retry.fetch_max_attempts,
                "llm_timeout": settings.retry.llm_timeout_max_attempts,
                "email": settings.retry.email_max_attempts,
            },
        )
        self._retry_enabled = bool(settings.retry.enabled)
        self._retry_worker_interval = max(5, int(settings.retry.worker_interval_seconds))
        self._retry_batch_size = max(1, int(settings.retry.replay_batch_size))
        self._retry_stop = threading.Event()
        self._retry_worker: threading.Thread | None = None
        self._fetch_fail_streak = 0

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
        if self._retry_enabled:
            self._retry_worker = threading.Thread(target=self._retry_worker_loop, name="retry-worker", daemon=True)
            self._retry_worker.start()

    def run_once(self, run_id: str, mode: str = "auto") -> dict:
        keyword = self.settings.xhs.keyword
        mode = self._normalize_mode(mode or self.settings.agent.mode or "auto")
        notification_mode = self._normalize_notification_mode(self.settings.notification.mode)
        orchestrator = RuntimeOrchestrator(runtime_name=self.settings.agent.runtime_name, logger=self.logger)

        if not self.lock.acquire():
            self.logger.warning(
                "跳过运行 | run=%s | 原因=检测到上一次运行锁未释放 | lock=%s",
                run_id,
                self.lock.path,
            )
            return {"skipped": True, "reason": "run_locked"}

        try:
            self.logger.info("运行开始 | run=%s | keyword=%s | mode=%s | notify=%s", run_id, keyword, mode, notification_mode)
            self._log_progress(run_id, 5, "初始化运行上下文")
            self.llm_enricher.reset_stats()
            self.llm_client.clear_error_counts()
            fetch_fail_events: list[dict[str, str]] = []
            detail_enrich_stats: dict[str, int] = {
                "target_notes": 0,
                "attempted": 0,
                "success": 0,
                "failed": 0,
                "skipped_no_token": 0,
                "detail_filled": 0,
                "detail_missing": 0,
                "blocked": 0,
            }
            xhs_failure_diagnosis: dict[str, Any] = {}
            xhs_data_empty = False

            resume_text = orchestrator.run_stage(
                "resume.load_text",
                lambda: self.resume_loader.load_resume_text(),
                meta={"resume_source": self.settings.resume.source_txt_path},
            )

            try:
                orchestrator.run_stage(
                    "collector.ensure_logged_in",
                    lambda: self.collector.ensure_logged_in(),
                    meta={"browser_path": self.settings.xhs.browser_path},
                )
            except Exception as exc:
                fetch_fail_events.append({"stage": "collector.ensure_logged_in", "error": str(exc)[:280]})
                self._enqueue_retry(
                    queue_type="fetch",
                    action="ensure_logged_in",
                    run_id=run_id,
                    error=str(exc),
                    payload={
                        "browser_path": self.settings.xhs.browser_path,
                        "account": self.settings.xhs.account,
                    },
                    dedupe_key=f"ensure-login:{self.settings.xhs.account}",
                )
            self._log_progress(run_id, 12, "登录态检查完成")

            try:
                notes = orchestrator.run_stage(
                    "collector.search_notes",
                    lambda: self.collector.search_notes(
                        run_id=run_id,
                        keyword=keyword,
                        max_results=self.settings.xhs.max_results,
                    ),
                    meta={"keyword": keyword, "max_results": self.settings.xhs.max_results},
                )
            except Exception as exc:
                notes = []
                fetch_fail_events.append({"stage": "collector.search_notes", "error": str(exc)[:280]})
                self._enqueue_retry(
                    queue_type="fetch",
                    action="search_notes",
                    run_id=run_id,
                    error=str(exc),
                    payload={
                        "keyword": keyword,
                        "max_results": self.settings.xhs.max_results,
                    },
                    dedupe_key=f"search:{keyword}:{self.settings.xhs.max_results}",
                )
                self.logger.warning("搜索失败已入重试队列 | run=%s | error=%s", run_id, exc)
            notes = sorted(notes, key=lambda n: (n.publish_time, n.note_id), reverse=True)
            xhs_data_empty = len(notes) == 0 and not fetch_fail_events
            self._log_progress(run_id, 28, f"搜索完成，抓取到 {len(notes)} 条")

            pre_new_notes = orchestrator.run_stage(
                "state.prefilter_new_notes",
                lambda: [note for note in notes if not self.state.has(note.note_id)],
                meta={"existing_state_size": len(self.state.processed_note_ids)},
            )
            updated_existing_notes = max(0, len(notes) - len(pre_new_notes))
            self._log_progress(run_id, 36, f"预过滤完成，候选新增 {len(pre_new_notes)} 条")

            initial_plan = self.planner.build_plan(mode=mode, fetched_count=len(notes), new_count=len(pre_new_notes))
            try:
                detail_enrich_stats = orchestrator.run_stage(
                    "collector.enrich_note_details",
                    lambda: self.collector.enrich_note_details(pre_new_notes, max_notes=initial_plan.detail_fetch_limit),
                    meta={
                        "max_detail_fetch": initial_plan.detail_fetch_limit,
                        "detail_workers": int(getattr(self.settings.xhs, "detail_workers", 1)),
                    },
                )
                if not isinstance(detail_enrich_stats, dict):
                    detail_enrich_stats = {
                        "target_notes": max(0, int(initial_plan.detail_fetch_limit)),
                        "attempted": 0,
                        "success": 0,
                        "failed": 0,
                        "skipped_no_token": 0,
                        "detail_filled": 0,
                        "detail_missing": 0,
                        "blocked": 0,
                    }
            except Exception as exc:
                fetch_fail_events.append({"stage": "collector.enrich_note_details", "error": str(exc)[:280]})
                queued = 0
                for note in pre_new_notes[: max(0, int(initial_plan.detail_fetch_limit))]:
                    if not str(getattr(note, "xsec_token", "") or "").strip():
                        continue
                    self._enqueue_retry(
                        queue_type="fetch",
                        action="enrich_note_detail",
                        run_id=run_id,
                        error=str(exc),
                        payload={"note_id": note.note_id, "xsec_token": note.xsec_token},
                        dedupe_key=f"detail:{note.note_id}",
                    )
                    queued += 1
                self.logger.warning("详情抓取失败已入队 | run=%s | queued=%s | error=%s", run_id, queued, exc)
                detail_enrich_stats = {
                    "target_notes": max(0, int(initial_plan.detail_fetch_limit)),
                    "attempted": 0,
                    "success": 0,
                    "failed": 1,
                    "skipped_no_token": 0,
                    "detail_filled": 0,
                    "detail_missing": 0,
                    "blocked": 0,
                }
            self._log_progress(
                run_id,
                46,
                (
                    f"正文补全完成，详情抓取上限 {initial_plan.detail_fetch_limit}，"
                    f"并行 {int(getattr(self.settings.xhs, 'detail_workers', 1))}"
                ),
            )

            if fetch_fail_events:
                self._fetch_fail_streak += 1
            else:
                self._fetch_fail_streak = 0

            if self._fetch_fail_streak >= 2:
                xhs_failure_diagnosis = self._probe_xhs_fetch_failure(run_id=run_id, fetch_fail_events=fetch_fail_events)

            new_notes = orchestrator.run_stage(
                "state.filter_new_notes",
                lambda: [note for note in pre_new_notes if not self.state.has(note.note_id)],
                meta={"prefiltered_count": len(pre_new_notes)},
            )
            new_notes = sorted(new_notes, key=lambda n: (n.publish_time, n.note_id), reverse=True)
            self._log_progress(run_id, 55, f"增量过滤完成，新增 {len(new_notes)} 条")

            plan = orchestrator.run_stage(
                "agent.planner.build_plan",
                lambda: self.planner.build_plan(mode=mode, fetched_count=len(notes), new_count=len(new_notes)),
                meta={"mode": mode},
            )
            process_workers = max(1, int(getattr(self.settings.pipeline, "process_workers", 1)))
            self.logger.info("提取并行配置 | run=%s | process_workers=%s", run_id, process_workers)
            use_single_pass_extract = bool(getattr(self.settings.llm, "single_pass_extract", True)) and bool(
                self.settings.llm.enabled
            )
            note_agent_stats: dict[str, int] = {}
            note_agent_details: list[dict[str, Any]] = []
            if use_single_pass_extract:
                extract_outcome = orchestrator.run_stage(
                    "agent.intelligence.process_notes_with_agents",
                    lambda: self.intelligence.process_notes_with_agents(
                        notes=new_notes,
                        resume_text=resume_text,
                        mode=mode,
                        workers=process_workers,
                    ),
                    meta={
                        "job_extract_llm_budget": "all",
                        "single_pass_extract": True,
                        "process_workers": process_workers,
                    },
                )
                target_notes = extract_outcome.targets
                filtered_out = extract_outcome.filtered_out
                jobs = extract_outcome.jobs
                note_agent_stats = dict(getattr(extract_outcome, "note_agent_stats", {}) or {})
                note_agent_details = list(getattr(extract_outcome, "note_agent_details", []) or [])
                llm_stage_calls = self.llm_enricher.stage_call_counts()
                llm_stage_fallbacks = self.llm_enricher.stage_fallback_counts()
                self._log_progress(
                    run_id,
                    66,
                    (
                        f"直接提取完成，命中 {len(target_notes)} 条，过滤 {len(filtered_out)} 条，"
                        f"LLM提取调用 {int(llm_stage_calls.get('job', 0))} 次，"
                        f"规则回退 {int(llm_stage_fallbacks.get('job', 0))} 次，"
                        f"每帖Agent回退 {int(note_agent_stats.get('worker_fallback', 0))} 次"
                    ),
                )
            else:
                filter_outcome = orchestrator.run_stage(
                    "agent.intelligence.filter_target_notes",
                    lambda: self.intelligence.filter_target_notes(
                        new_notes,
                        max_filter_items=plan.max_filter_items,
                        workers=process_workers,
                    ),
                    meta={"max_filter_items": plan.max_filter_items, "process_workers": process_workers},
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
                        workers=process_workers,
                    ),
                    meta={"max_job_items": plan.max_job_items, "process_workers": process_workers},
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
                lambda: self.store.write(notes, summaries, [], jobs=jobs),
                meta={
                    "excel_path": self.settings.storage.excel_path,
                    "upsert_notes": len(notes),
                    "new_notes": len(new_notes),
                    "updated_existing_notes": updated_existing_notes,
                },
            )
            orchestrator.run_stage(
                "storage.export_jobs_csv",
                lambda: self.store.export_jobs_csv(self.settings.storage.jobs_csv_path),
                meta={"jobs_csv_path": self.settings.storage.jobs_csv_path},
            )
            self._log_progress(
                run_id,
                88,
                f"本地存储已更新（新增 {len(new_notes)}，更新 {updated_existing_notes}，Excel/CSV）",
            )

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
                    realtime_channels = list(self.settings.notification.realtime_channels)
                    try:
                        dispatch_result = orchestrator.run_stage(
                            "agent.communication.batch_dispatch_realtime",
                            lambda: self._dispatch_batch_with_compat(
                                run_id=run_id,
                                mode=mode,
                                jobs=jobs,
                                top_n=plan.top_n,
                                resume_text=resume_text,
                                channel_names=realtime_channels,
                                attachments=[],
                                digest_style=False,
                            ),
                            meta={
                                "mode": mode,
                                "channels": realtime_channels,
                                "job_count": len(jobs),
                            },
                        )
                    except Exception as exc:
                        dispatch_result = self._build_retry_dispatch_fallback(
                            run_id=run_id,
                            mode=mode,
                            jobs=jobs,
                            channels=realtime_channels,
                            attachments=[],
                            reason=f"dispatch_realtime_failed: {exc}",
                        )
                        self._enqueue_retry(
                            queue_type="email",
                            action="dispatch_digest",
                            run_id=run_id,
                            error=str(exc),
                            payload=dispatch_result,
                            dedupe_key=f"email:realtime:{run_id}",
                        )
                        self.logger.warning("实时通知失败已入队 | run=%s | error=%s", run_id, exc)
                    send_logs = dispatch_result["logs"]
                    notify_note_ids = sorted({log.note_id for log in send_logs})
                    digest_subject = dispatch_result["subject"]
                    self._enqueue_failed_email_dispatch(run_id=run_id, send_logs=send_logs, dispatch_result=dispatch_result)
                self._log_progress(run_id, 94, f"实时通知完成，发送日志 {len(send_logs)} 条")

            elif notification_mode == "digest":
                now = datetime.now(timezone.utc)
                digest_due = self._is_digest_due(now)
                enough_new = len(new_notes) >= max(0, int(self.settings.notification.digest_min_new_notes))
                allow_no_new = bool(self.settings.notification.digest_send_when_no_new)
                if digest_due and (enough_new or allow_no_new) and jobs:
                    digest_attachments = self._collect_digest_attachments()
                    digest_channels = list(self.settings.notification.digest_channels)
                    try:
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
                    except Exception as exc:
                        dispatch_result = self._build_retry_dispatch_fallback(
                            run_id=run_id,
                            mode=mode,
                            jobs=jobs,
                            channels=digest_channels,
                            attachments=digest_attachments,
                            reason=f"dispatch_digest_failed: {exc}",
                        )
                        self._enqueue_retry(
                            queue_type="email",
                            action="dispatch_digest",
                            run_id=run_id,
                            error=str(exc),
                            payload=dispatch_result,
                            dedupe_key=f"email:digest:{run_id}",
                        )
                        self.logger.warning("摘要通知失败已入队 | run=%s | error=%s", run_id, exc)
                    send_logs = dispatch_result["logs"]
                    notify_note_ids = sorted({log.note_id for log in send_logs})
                    digest_subject = dispatch_result["subject"]
                    self._enqueue_failed_email_dispatch(run_id=run_id, send_logs=send_logs, dispatch_result=dispatch_result)
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
            self._enqueue_llm_timeout_retries(run_id=run_id, llm_error_codes=llm_error_codes)
            llm_timeout_count = self._sum_timeout_error_counts(llm_error_codes)
            llm_timeout_rate = (
                float(llm_timeout_count) / float(self.llm_enricher.calls)
                if int(self.llm_enricher.calls) > 0
                else 0.0
            )
            detail_target_notes = int(detail_enrich_stats.get("target_notes", 0))
            detail_missing = int(detail_enrich_stats.get("detail_missing", 0))
            detail_missing_rate = (
                float(detail_missing) / float(detail_target_notes)
                if detail_target_notes > 0
                else 0.0
            )

            stats = {
                "runtime_name": self.settings.agent.runtime_name,
                "mode": mode,
                "notification_mode": notification_mode,
                "fetched": len(notes),
                "new_notes": len(new_notes),
                "updated_existing_notes": updated_existing_notes,
                "target_notes": len(target_notes),
                "filtered_out": len(filtered_out),
                "notify_note_count": len(notify_note_ids),
                "jobs": len(jobs),
                "opportunities": len(opportunity_post_ids),
                "summaries": len(jobs),
                "process_workers": process_workers,
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
                "llm_timeout_count": int(llm_timeout_count),
                "llm_timeout_rate": llm_timeout_rate,
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
                "fetch_fail_count_run": len(fetch_fail_events),
                "fetch_fail_streak": int(self._fetch_fail_streak),
                "xhs_data_empty": bool(xhs_data_empty),
                "detail_target_notes": detail_target_notes,
                "detail_attempted": int(detail_enrich_stats.get("attempted", 0)),
                "detail_success": int(detail_enrich_stats.get("success", 0)),
                "detail_failed": int(detail_enrich_stats.get("failed", 0)),
                "detail_skipped_no_token": int(detail_enrich_stats.get("skipped_no_token", 0)),
                "detail_filled": int(detail_enrich_stats.get("detail_filled", 0)),
                "detail_missing": detail_missing,
                "detail_missing_rate": detail_missing_rate,
                "detail_blocked": int(detail_enrich_stats.get("blocked", 0)),
                "detail_workers": int(getattr(self.settings.xhs, "detail_workers", 1)),
                "xhs_diagnosis": xhs_failure_diagnosis,
                "note_agent_total": int(note_agent_stats.get("total", 0)),
                "note_agent_llm_budgeted": int(note_agent_stats.get("llm_budgeted", 0)),
                "note_agent_rule_budgeted": int(note_agent_stats.get("rule_budgeted", 0)),
                "note_agent_worker_fallback": int(note_agent_stats.get("worker_fallback", 0)),
                "note_agent_errors": int(note_agent_stats.get("errors", 0)),
            }
            alert_eval = self._evaluate_threshold_alerts(run_id=run_id, stats=stats)
            stats["alerts_enabled"] = bool(alert_eval.get("enabled"))
            stats["alerts_triggered"] = list(alert_eval.get("triggered", []))
            stats["alerts_triggered_count"] = int(len(stats["alerts_triggered"]))
            stats["alerts_thresholds"] = dict(alert_eval.get("thresholds", {}))
            alert_dispatch = self._dispatch_threshold_alerts(
                run_id=run_id,
                mode=mode,
                stats=stats,
                triggered_alerts=list(stats["alerts_triggered"]),
            )
            stats["alerts_notified"] = list(alert_dispatch.get("notified_codes", []))
            stats["alerts_notified_count"] = int(len(stats["alerts_notified"]))
            stats["alerts_suppressed"] = list(alert_dispatch.get("suppressed_codes", []))
            stats["alerts_failed"] = list(alert_dispatch.get("failed_codes", []))
            stats["alerts_notification_channels"] = list(alert_dispatch.get("channels", []))
            stats["alerts_notification_logs"] = int(alert_dispatch.get("send_logs_count", 0))

            retry_snapshot = self.retry_queue.snapshot()
            stats["retry_pending"] = retry_snapshot.get("pending", {})
            stats["retry_running"] = retry_snapshot.get("running", {})
            stats["retry_enqueued"] = int(retry_snapshot.get("stats", {}).get("enqueued", 0))
            stats["retry_retried"] = int(retry_snapshot.get("stats", {}).get("retried", 0))
            stats["retry_succeeded"] = int(retry_snapshot.get("stats", {}).get("succeeded", 0))
            stats["retry_dropped"] = int(retry_snapshot.get("stats", {}).get("dropped", 0))
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
                    "fetch_fail_events": fetch_fail_events,
                    "xhs_diagnosis": xhs_failure_diagnosis,
                    "agent_plan": {
                        "detail_fetch_limit": plan.detail_fetch_limit,
                        "max_filter_items": plan.max_filter_items,
                        "max_job_items": plan.max_job_items,
                        "max_summary_items": plan.max_summary_items,
                        "top_n": plan.top_n,
                        "process_workers": process_workers,
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
                    "note_agent": {
                        "stats": note_agent_stats,
                        "details_count": len(note_agent_details),
                        "details": note_agent_details[:200],
                    },
                    "alerts": {
                        "enabled": bool(stats.get("alerts_enabled")),
                        "triggered_count": int(stats.get("alerts_triggered_count", 0)),
                        "triggered": list(stats.get("alerts_triggered") or []),
                        "notified_count": int(stats.get("alerts_notified_count", 0)),
                        "notified_codes": list(stats.get("alerts_notified") or []),
                        "suppressed_codes": list(stats.get("alerts_suppressed") or []),
                        "failed_codes": list(stats.get("alerts_failed") or []),
                        "channels": list(stats.get("alerts_notification_channels") or []),
                    },
                    "retry": retry_snapshot,
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
            self.logger.warning(
                "跳过发送 | run=%s | 原因=检测到上一次运行锁未释放 | lock=%s",
                run_id,
                self.lock.path,
            )
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

            try:
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
            except Exception as exc:
                dispatch_result = self._build_retry_dispatch_fallback(
                    run_id=run_id,
                    mode=mode,
                    jobs=jobs,
                    channels=digest_channels,
                    attachments=digest_attachments,
                    reason=f"send_latest_failed: {exc}",
                )
                self._enqueue_retry(
                    queue_type="email",
                    action="dispatch_digest",
                    run_id=run_id,
                    error=str(exc),
                    payload=dispatch_result,
                    dedupe_key=f"email:send-latest:{run_id}",
                )
                self.logger.warning("发送最新失败已入队 | run=%s | error=%s", run_id, exc)
            self._log_progress(run_id, 72, "通知分发执行完成，正在写入发送日志")
            send_logs = dispatch_result["logs"]
            self._enqueue_failed_email_dispatch(run_id=run_id, send_logs=send_logs, dispatch_result=dispatch_result)
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
