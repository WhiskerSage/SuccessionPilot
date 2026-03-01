from __future__ import annotations

import unittest
from datetime import datetime, timezone

from auto_successor.agents import DigestDispatchResult
from auto_successor.config import (
    AgentConfig,
    AppConfig,
    EmailConfig,
    LLMConfig,
    NotificationConfig,
    PipelineConfig,
    Settings,
    StorageConfig,
    WeChatServiceConfig,
    XHSConfig,
)
from auto_successor.models import JobRecord, NoteRecord, SendLogRecord, SummaryRecord
from auto_successor.pipeline import AutoSuccessorPipeline


def _build_settings() -> Settings:
    return Settings(
        app=AppConfig(),
        xhs=XHSConfig(max_results=20, max_detail_fetch=0),
        pipeline=PipelineConfig(min_confidence=0.55),
        llm=LLMConfig(
            enabled=False,
            enabled_for_filter=True,
            filter_threshold=0.62,
            strict_filter=True,
            max_filter_items=20,
        ),
        wechat_service=WeChatServiceConfig(enabled=False),
        email=EmailConfig(enabled=False),
        storage=StorageConfig(
            excel_path="data/test_output.xlsx",
            jobs_csv_path="data/test_jobs.csv",
            state_path="data/test_state.json",
        ),
        notification=NotificationConfig(
            mode="realtime",
            realtime_channels=["email"],
            digest_channels=["email"],
        ),
        agent=AgentConfig(
            mode="auto",
            agent_full_detail_fetch=True,
            agent_send_top_n=1,
            agent_include_jd_full=True,
        ),
    )


def _note(note_id: str, title: str, detail: str) -> NoteRecord:
    return NoteRecord(
        run_id="r-test",
        keyword="继任",
        note_id=note_id,
        title=title,
        author="tester",
        publish_time=datetime.now(timezone.utc),
        publish_time_text="2026-02-23",
        like_count=66,
        comment_count=22,
        share_count=3,
        url=f"https://www.xiaohongshu.com/explore/{note_id}",
        raw_json="{}",
        detail_text=detail,
        comments_preview="评论预览",
    )


def _summary(note: NoteRecord) -> SummaryRecord:
    return SummaryRecord(
        run_id=note.run_id,
        note_id=note.note_id,
        keyword=note.keyword,
        publish_time=note.publish_time,
        title=note.title,
        author=note.author,
        summary=f"【继任追踪】{note.title}\n正文信息（详细）：{note.detail_text}",
        confidence=1.0,
        risk_flags="",
        url=note.url,
    )


class _NullLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class _DummyCollector:
    def __init__(self, notes):
        self._notes = list(notes)

    def ensure_logged_in(self):
        return None

    def search_notes(self, run_id: str, keyword: str, max_results: int):
        return self._notes[:max_results]

    def enrich_note_details(self, notes, max_notes: int):
        return None


class _DummyStore:
    def __init__(self):
        self.raw = []
        self.jobs = []
        self.summaries = []
        self.logs = []
        self.export_path = ""

    def write(self, raw, summaries, send_logs, jobs=None):
        if raw:
            self.raw = list(raw)
        if jobs:
            self.jobs = list(jobs or [])
        if summaries:
            self.summaries = list(summaries)
        if send_logs:
            self.logs.extend(list(send_logs))

    def export_jobs_csv(self, csv_path: str):
        self.export_path = csv_path


class _DummyState:
    def __init__(self):
        self.processed_note_ids = set()
        self.saved = False
        self.digest_due = True
        self.digest_marked = False
        self.digest_run_id = ""

    def has(self, note_id: str) -> bool:
        return note_id in self.processed_note_ids

    def mark(self, note_id: str):
        self.processed_note_ids.add(note_id)

    def save(self):
        self.saved = True

    def is_digest_due(self, now, interval_minutes: int) -> bool:
        return self.digest_due

    def mark_digest_sent(self, now, run_id: str):
        self.digest_marked = True
        self.digest_run_id = run_id


class _DummyCommunication:
    def __init__(self, digest_status: str = "success"):
        self.realtime_calls = []
        self.digest_calls = []
        self.digest_status = digest_status

    def dispatch_realtime(self, run_id: str, summaries, channel_names):
        self.realtime_calls.append({"run_id": run_id, "count": len(summaries), "channels": list(channel_names)})
        logs = []
        for summary in summaries:
            logs.append(
                SendLogRecord(
                    run_id=run_id,
                    note_id=summary.note_id,
                    channel="email",
                    send_status="success",
                    send_response="ok",
                )
            )
        return logs

    def dispatch_digest(self, run_id: str, mode: str, new_notes, target_notes, summaries, attachments, channel_names):
        self.digest_calls.append(
            {
                "run_id": run_id,
                "mode": mode,
                "new_notes": len(new_notes),
                "target_notes": len(target_notes),
                "attachments": list(attachments),
                "channels": list(channel_names),
            }
        )
        return DigestDispatchResult(
            sent=self.digest_status == "success",
            logs=[
                SendLogRecord(
                    run_id=run_id,
                    note_id=f"digest:{run_id}",
                    channel="email",
                    send_status=self.digest_status,
                    send_response="ok" if self.digest_status == "success" else "smtp error",
                )
            ],
            subject="digest",
            body="body",
        )


class _DummyRouter:
    def __init__(self, send_status: str = "success"):
        self.send_status = send_status
        self.calls = []

    def dispatch_digest(self, run_id: str, subject: str, text: str, html=None, attachments=None, channel_names=None):
        self.calls.append(
            {
                "run_id": run_id,
                "subject": subject,
                "text": text,
                "channels": list(channel_names or []),
            }
        )
        return [
            SendLogRecord(
                run_id=run_id,
                note_id=f"digest:{run_id}",
                channel="email",
                send_status=self.send_status,
                send_response="ok" if self.send_status == "success" else "failed",
            )
        ]


class _DummyJournal:
    def __init__(self):
        self.writes = []

    def write(self, run_id: str, payload: dict):
        self.writes.append((run_id, payload))
        return None


class _DummyLock:
    def acquire(self):
        return True

    def release(self):
        return None


class _FailingLoginCollector:
    def ensure_logged_in(self):
        raise RuntimeError("login check failed")

    def search_notes(self, run_id: str, keyword: str, max_results: int):
        return []

    def enrich_note_details(self, notes, max_notes: int):
        return {
            "target_notes": 0,
            "attempted": 0,
            "success": 0,
            "failed": 0,
            "skipped_no_token": 0,
            "detail_filled": 0,
            "detail_missing": 0,
            "blocked": 0,
        }


class TestPipelineFlow(unittest.TestCase):
    def test_pipeline_filters_non_target_notes_before_jobs_and_notify(self):
        settings = _build_settings()
        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        target_note = _note(
            note_id="n1",
            title="找继任：招聘接任同学，实习岗位上海",
            detail="团队招实习，欢迎投递简历。",
        )
        non_target_note = _note(
            note_id="n2",
            title="军事继任观察：某国军队将领变动",
            detail="政治军事分析文章。",
        )

        pipeline.collector = _DummyCollector([target_note, non_target_note])
        pipeline.store = _DummyStore()
        pipeline.state = _DummyState()
        pipeline.communication = _DummyCommunication()
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()

        stats = pipeline.run_once(run_id="r-test")

        self.assertEqual(stats["fetched"], 2)
        self.assertEqual(stats["new_notes"], 2)
        self.assertEqual(stats["target_notes"], 1)
        self.assertEqual(stats["filtered_out"], 1)
        self.assertEqual(stats["jobs"], 1)
        self.assertEqual(stats["summaries"], 1)
        self.assertEqual(stats["send_logs"], 1)
        self.assertEqual(stats["notification_mode"], "realtime")
        self.assertEqual(len(pipeline.communication.realtime_calls), 1)
        self.assertEqual(len(pipeline.store.raw), 2)
        self.assertEqual(len(pipeline.store.jobs), 1)
        self.assertEqual(len(pipeline.store.summaries), 1)
        self.assertEqual(pipeline.store.jobs[0].post_id, "n1")
        self.assertTrue(pipeline.state.saved)
        self.assertEqual(pipeline.state.processed_note_ids, {"n1", "n2"})
        self.assertEqual(len(pipeline.journal.writes), 1)

    def test_pipeline_upserts_all_fetched_notes_while_processing_only_new_notes(self):
        settings = _build_settings()
        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        existing_note = _note(
            note_id="n-existing",
            title="找继任：历史帖子",
            detail="历史帖子正文。",
        )
        new_note = _note(
            note_id="n-new",
            title="找继任：新增岗位，实习岗位上海",
            detail="新增岗位正文。",
        )

        state = _DummyState()
        state.processed_note_ids.add("n-existing")

        pipeline.collector = _DummyCollector([existing_note, new_note])
        pipeline.store = _DummyStore()
        pipeline.state = state
        pipeline.communication = _DummyCommunication()
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()

        stats = pipeline.run_once(run_id="r-upsert")

        self.assertEqual(stats["fetched"], 2)
        self.assertEqual(stats["new_notes"], 1)
        self.assertEqual(stats["updated_existing_notes"], 1)
        self.assertEqual(stats["target_notes"], 1)
        self.assertEqual(stats["jobs"], 1)
        self.assertEqual(len(pipeline.store.raw), 2)
        self.assertEqual(state.processed_note_ids, {"n-existing", "n-new"})

    def test_agent_mode_realtime_dispatches_top_n_only(self):
        settings = _build_settings()
        settings.agent.mode = "agent"
        settings.agent.agent_send_top_n = 1
        settings.notification.mode = "realtime"

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        note_high = _note(
            note_id="n-high",
            title="找继任：产品实习，急招下周到岗",
            detail="组内招聘，base 上海，尽快到岗，简历投递邮箱在正文。",
        )
        note_low = _note(
            note_id="n-low",
            title="找继任：运营实习",
            detail="有兴趣可投递。",
        )
        note_high.like_count = 120
        note_high.comment_count = 66
        note_low.like_count = 3
        note_low.comment_count = 1

        pipeline.collector = _DummyCollector([note_high, note_low])
        pipeline.store = _DummyStore()
        pipeline.state = _DummyState()
        pipeline.communication = _DummyCommunication()
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()

        stats = pipeline.run_once(run_id="r-agent", mode="agent")

        self.assertEqual(stats["mode"], "agent")
        self.assertEqual(stats["target_notes"], 2)
        self.assertEqual(stats["summaries"], 2)
        self.assertEqual(stats["send_logs"], 1)
        self.assertEqual(pipeline.communication.realtime_calls[0]["count"], 1)

    def test_digest_mode_sends_periodic_table_notification(self):
        settings = _build_settings()
        settings.notification.mode = "digest"
        settings.notification.digest_channels = ["email"]
        settings.notification.digest_interval_minutes = 30
        settings.notification.digest_send_when_no_new = False

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        note = _note(
            note_id="n-digest",
            title="找继任：数据实习",
            detail="下周到岗，邮箱投递。",
        )

        pipeline.collector = _DummyCollector([note])
        pipeline.store = _DummyStore()
        pipeline.state = _DummyState()
        pipeline.communication = _DummyCommunication()
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()

        stats = pipeline.run_once(run_id="r-digest")

        self.assertEqual(stats["notification_mode"], "digest")
        self.assertTrue(stats["digest_due"])
        self.assertTrue(stats["digest_sent"])
        self.assertEqual(stats["send_logs"], 1)
        self.assertTrue(pipeline.state.digest_marked)
        self.assertEqual(pipeline.state.digest_run_id, "r-digest")
        self.assertEqual(len(pipeline.communication.digest_calls), 1)

    def test_digest_not_marked_when_dispatch_fails(self):
        settings = _build_settings()
        settings.notification.mode = "digest"
        settings.notification.digest_channels = ["email"]
        settings.notification.digest_interval_minutes = 30
        settings.notification.digest_send_when_no_new = False

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        note = _note(
            note_id="n-digest-fail",
            title="找继任：策略实习",
            detail="明天可到岗，邮箱投递。",
        )

        pipeline.collector = _DummyCollector([note])
        pipeline.store = _DummyStore()
        pipeline.state = _DummyState()
        pipeline.communication = _DummyCommunication(digest_status="failed")
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()

        stats = pipeline.run_once(run_id="r-digest-fail")

        self.assertEqual(stats["notification_mode"], "digest")
        self.assertTrue(stats["digest_due"])
        self.assertFalse(stats["digest_sent"])
        self.assertEqual(stats["send_logs"], 1)
        self.assertFalse(pipeline.state.digest_marked)
        self.assertEqual(pipeline.state.digest_run_id, "")
        self.assertEqual(len(pipeline.communication.digest_calls), 1)

    def test_send_latest_stored_dispatches_existing_top_n(self):
        settings = _build_settings()
        settings.notification.mode = "digest"
        settings.notification.digest_channels = ["email"]

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        note = _note(
            note_id="n-stored",
            title="找继任：已存岗位",
            detail="这是已存储在本地表的数据。",
        )
        stored_summary = _summary(note)

        pipeline.store = _DummyStore()
        pipeline.state = _DummyState()
        pipeline.communication = _DummyCommunication()
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()
        pipeline._load_latest_summaries_from_store = lambda limit: [stored_summary]

        stats = pipeline.send_latest_stored(run_id="r-send-latest", limit=5)

        self.assertEqual(stats["action"], "send_latest_stored")
        self.assertEqual(stats["loaded_summaries"], 1)
        self.assertEqual(stats["send_logs"], 1)
        self.assertTrue(stats["digest_sent"])
        self.assertTrue(pipeline.state.digest_marked)
        self.assertTrue(pipeline.state.saved)
        self.assertEqual(len(pipeline.communication.digest_calls), 1)

    def test_send_latest_stored_no_summary(self):
        settings = _build_settings()
        settings.notification.mode = "digest"
        settings.notification.digest_channels = ["email"]

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        pipeline.store = _DummyStore()
        pipeline.state = _DummyState()
        pipeline.communication = _DummyCommunication()
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()
        pipeline._load_latest_summaries_from_store = lambda limit: []

        stats = pipeline.send_latest_stored(run_id="r-send-latest-empty", limit=5)

        self.assertEqual(stats["action"], "send_latest_stored")
        self.assertEqual(stats["loaded_summaries"], 0)
        self.assertEqual(stats["send_logs"], 0)
        self.assertFalse(stats["digest_sent"])
        self.assertFalse(pipeline.state.digest_marked)
        self.assertFalse(pipeline.state.saved)
        self.assertEqual(len(pipeline.communication.digest_calls), 0)

    def test_threshold_alert_auto_notifies_when_fetch_fail_streak_hit(self):
        settings = _build_settings()
        settings.notification.mode = "off"
        settings.observability.alerts.enabled = True
        settings.observability.alerts.fetch_fail_streak_threshold = 1
        settings.observability.alerts.fetch_fail_streak = {
            "short_window_runs": 1,
            "short_threshold": 1,
            "short_min_runs": 1,
            "long_window_runs": 1,
            "long_threshold": 1,
            "long_min_runs": 1,
        }
        settings.observability.alerts.channels = ["email"]
        settings.observability.alerts.cooldown_minutes = 60

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)
        pipeline.collector = _FailingLoginCollector()
        pipeline.store = _DummyStore()
        pipeline.state = _DummyState()
        pipeline.communication = _DummyCommunication()
        pipeline.router = _DummyRouter(send_status="success")
        pipeline.journal = _DummyJournal()
        pipeline.lock = _DummyLock()

        stats = pipeline.run_once(run_id="r-alert")

        self.assertEqual(stats["fetch_fail_streak"], 1)
        self.assertEqual(stats["alerts_triggered_count"], 1)
        self.assertIn("fetch_fail_streak", [item.get("code") for item in stats["alerts_triggered"]])
        self.assertEqual(stats["alerts_notified_count"], 1)
        self.assertEqual(stats["alerts_notified"], ["fetch_fail_streak"])
        self.assertEqual(len(pipeline.router.calls), 1)
        self.assertIn("阈值告警", pipeline.router.calls[0]["subject"])

    def test_dual_window_llm_timeout_requires_long_window_trend(self):
        settings = _build_settings()
        settings.observability.alerts.enabled = True
        settings.observability.alerts.llm_timeout_rate = {
            "short_window_runs": 1,
            "short_threshold": 0.5,
            "short_min_samples": 4,
            "long_window_runs": 3,
            "long_threshold": 0.3,
            "long_min_samples": 12,
        }

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)
        stats = {
            "fetch_fail_streak": 0,
            "llm_calls": 4,
            "llm_timeout_count": 3,
            "llm_timeout_rate": 0.75,
            "detail_target_notes": 0,
            "detail_missing": 0,
            "detail_missing_rate": 0.0,
        }

        pipeline._load_recent_alert_stats = lambda limit, exclude_run_id: [
            {"llm_calls": 10, "llm_timeout_count": 0},
            {"llm_calls": 10, "llm_timeout_count": 0},
        ]
        eval_low_long = pipeline._evaluate_threshold_alerts(run_id="r-low-long", stats=stats)
        self.assertNotIn("llm_timeout_rate", [item.get("code") for item in eval_low_long["triggered"]])

        pipeline._load_recent_alert_stats = lambda limit, exclude_run_id: [
            {"llm_calls": 10, "llm_timeout_count": 4},
            {"llm_calls": 10, "llm_timeout_count": 4},
        ]
        eval_high_long = pipeline._evaluate_threshold_alerts(run_id="r-high-long", stats=stats)
        self.assertIn("llm_timeout_rate", [item.get("code") for item in eval_high_long["triggered"]])

    def test_dual_window_fetch_fail_requires_long_window_min_runs(self):
        settings = _build_settings()
        settings.observability.alerts.enabled = True
        settings.observability.alerts.fetch_fail_streak = {
            "short_window_runs": 1,
            "short_threshold": 2,
            "short_min_runs": 1,
            "long_window_runs": 4,
            "long_threshold": 1.0,
            "long_min_runs": 3,
        }

        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)
        stats = {
            "fetch_fail_streak": 2,
            "llm_calls": 0,
            "llm_timeout_count": 0,
            "llm_timeout_rate": 0.0,
            "detail_target_notes": 0,
            "detail_missing": 0,
            "detail_missing_rate": 0.0,
        }

        pipeline._load_recent_alert_stats = lambda limit, exclude_run_id: []
        eval_insufficient_runs = pipeline._evaluate_threshold_alerts(run_id="r-no-history", stats=stats)
        self.assertNotIn("fetch_fail_streak", [item.get("code") for item in eval_insufficient_runs["triggered"]])

        pipeline._load_recent_alert_stats = lambda limit, exclude_run_id: [
            {"fetch_fail_streak": 1},
            {"fetch_fail_streak": 1},
        ]
        eval_triggered = pipeline._evaluate_threshold_alerts(run_id="r-with-history", stats=stats)
        self.assertIn("fetch_fail_streak", [item.get("code") for item in eval_triggered["triggered"]])

    def test_jobs_to_summary_records_avoid_duplicate_original_text(self):
        settings = _build_settings()
        logger = _NullLogger()
        pipeline = AutoSuccessorPipeline(settings, logger)

        job = JobRecord(
            run_id="r-dup",
            post_id="n-dup",
            company="测试公司",
            position="测试岗位",
            location="上海",
            requirements="岗位职责：整理日报，维护台账",
            link="https://www.xiaohongshu.com/explore/n-dup",
            publish_time=datetime.now(timezone.utc),
            source_title="找继任：测试岗位",
            comment_count=0,
            comments_preview="",
            original_text="岗位职责：整理日报，维护台账",
            author="tester",
            risk_line="low",
            match_score=88.0,
            mode="auto",
        )

        records = pipeline._jobs_to_summary_records(run_id="r-dup", jobs=[job])
        self.assertEqual(len(records), 1)
        summary_text = records[0].summary
        self.assertIn("岗位要求：岗位职责：整理日报，维护台账", summary_text)
        self.assertIn("原文：原文与岗位要求高度重合", summary_text)
        self.assertNotIn("原文：岗位职责：整理日报，维护台账", summary_text)


if __name__ == "__main__":
    unittest.main()
