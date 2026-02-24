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
from auto_successor.models import NoteRecord, SendLogRecord, SummaryRecord
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


if __name__ == "__main__":
    unittest.main()
