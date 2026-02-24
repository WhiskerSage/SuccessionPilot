from __future__ import annotations

import unittest
from datetime import datetime, timezone

from auto_successor.agents import CommunicationAgent
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
from auto_successor.models import NoteRecord, SendLogRecord, SendResult, SummaryRecord
from auto_successor.notification_router import NotificationChannel


class _NullLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class _CaptureSender:
    def __init__(self):
        self.subject = ""
        self.text = ""
        self.attachments = []

    def send_text(self, subject: str = "", text: str = "") -> SendResult:
        self.subject = subject
        self.text = text
        return SendResult(status="success", response="ok")

    def send_text_with_attachments(self, subject: str, text: str, attachments=None) -> SendResult:
        self.subject = subject
        self.text = text
        self.attachments = list(attachments or [])
        return SendResult(status="success", response="ok")


class _CaptureRouter:
    def __init__(self):
        self.subject = ""
        self.text = ""
        self.attachments = []

    def dispatch_digest(self, run_id: str, subject: str, text: str, attachments=None, channel_names=None):
        self.subject = subject
        self.text = text
        self.attachments = list(attachments or [])
        return [
            SendLogRecord(
                run_id=run_id,
                note_id=f"digest:{run_id}",
                channel="email",
                send_status="success",
                send_response="ok",
            )
        ]


def _build_settings() -> Settings:
    return Settings(
        app=AppConfig(),
        xhs=XHSConfig(),
        pipeline=PipelineConfig(),
        llm=LLMConfig(enabled=False),
        wechat_service=WeChatServiceConfig(enabled=False),
        email=EmailConfig(enabled=False),
        storage=StorageConfig(
            excel_path="data/test_output.xlsx",
            jobs_csv_path="data/test_jobs.csv",
            state_path="data/test_state.json",
        ),
        notification=NotificationConfig(
            mode="digest",
            digest_top_summaries=5,
            digest_channels=["email"],
            realtime_channels=["email"],
        ),
        agent=AgentConfig(mode="auto"),
    )


def _note(note_id: str) -> NoteRecord:
    return NoteRecord(
        run_id="r-format",
        keyword="继任",
        note_id=note_id,
        title="找继任：测试岗位",
        author="tester",
        publish_time=datetime.now(timezone.utc),
        publish_time_text="刚刚",
        like_count=10,
        comment_count=2,
        share_count=1,
        url=f"https://www.xiaohongshu.com/explore/{note_id}",
        raw_json="{}",
        detail_text="岗位职责：整理流程。到岗时间：下周。",
        comments_preview="评论A|评论B",
    )


class TestNotificationFormat(unittest.TestCase):
    def test_email_single_summary_has_readable_sections(self):
        sender = _CaptureSender()
        channel = NotificationChannel(name="email", sender=sender)

        summary = SummaryRecord(
            run_id="r-format",
            note_id="n-format",
            keyword="继任",
            publish_time=datetime.now(timezone.utc),
            title="找继任：数据实习",
            author="Alice",
            summary="【继任追踪】找继任：数据实习\n正文信息（详细）：第一段\n\n贴主补充评论：未见贴主补充评论",
            confidence=1.0,
            risk_flags="信息不完整",
            url="https://www.xiaohongshu.com/explore/n-format",
        )

        result = channel.send_summary(summary)

        self.assertEqual(result.status, "success")
        self.assertIn("SuccessionPilot 线索通知", sender.text)
        self.assertIn("【基础信息】", sender.text)
        self.assertIn("【摘要详情】", sender.text)
        self.assertIn("- 风险标签：信息不完整", sender.text)
        self.assertIn("正文信息（详细）：第一段", sender.text)

    def test_digest_body_uses_blocks_and_spacing(self):
        settings = _build_settings()
        router = _CaptureRouter()
        agent = CommunicationAgent(router=router, settings=settings, logger=_NullLogger())

        note = _note("n-digest-format")
        summary = SummaryRecord(
            run_id="r-format",
            note_id=note.note_id,
            keyword="继任",
            publish_time=note.publish_time,
            title=note.title,
            author=note.author,
            summary="【继任追踪】找继任：测试岗位\n正文信息（详细）：第一段\n\n贴主补充评论：未见贴主补充评论",
            confidence=1.0,
            risk_flags="",
            url=note.url,
        )

        result = agent.dispatch_digest(
            run_id="r-format",
            mode="auto",
            new_notes=[note],
            target_notes=[note],
            summaries=[summary],
            attachments=["data/output.xlsx", "data/jobs.csv"],
            channel_names=["email"],
        )

        self.assertTrue(result.sent)
        self.assertNotIn("【运行信息】", result.body)
        self.assertIn("【统计】", result.body)
        self.assertIn("【附件】", result.body)
        self.assertIn("- output.xlsx", result.body)
        self.assertIn("- jobs.csv", result.body)
        self.assertIn("【岗位详情】", result.body)
        self.assertIn("摘要内容：", result.body)
        self.assertIn("正文信息（详细）：第一段", result.body)

    def test_no_truncation_for_long_summary_text(self):
        sender = _CaptureSender()
        channel = NotificationChannel(name="email", sender=sender)
        long_block = "非常详细的岗位说明。" * 500
        summary = SummaryRecord(
            run_id="r-long",
            note_id="n-long",
            keyword="继任",
            publish_time=datetime.now(timezone.utc),
            title="长文本测试",
            author="Alice",
            summary=f"【继任追踪】长文本测试\n正文信息（详细）：{long_block}",
            confidence=1.0,
            risk_flags="",
            url="https://www.xiaohongshu.com/explore/n-long",
        )

        channel.send_summary(summary)
        self.assertNotIn("已截断", sender.text)
        self.assertIn(long_block, sender.text)


if __name__ == "__main__":
    unittest.main()
