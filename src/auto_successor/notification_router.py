from __future__ import annotations

from dataclasses import dataclass

from .models import SendLogRecord, SendResult, SummaryRecord


@dataclass
class NotificationChannel:
    name: str
    sender: object

    def send_summary(self, summary: SummaryRecord) -> SendResult:
        body = self._format_single_summary(summary)
        if self.name == "email":
            subject = f"successor note | {summary.title[:50]}"
            return self.sender.send_text(subject=subject, text=body)
        return self.sender.send_text(body)

    def send_digest(self, subject: str, text: str, attachments: list[str] | None = None) -> SendResult:
        if self.name == "email":
            return self.sender.send_text_with_attachments(subject=subject, text=text, attachments=attachments)
        return self.sender.send_text(text)

    @staticmethod
    def _format_single_summary(summary: SummaryRecord) -> str:
        publish = summary.publish_time.strftime("%Y-%m-%d %H:%M")
        lines = [
            "SuccessionPilot 线索通知",
            "====================",
            "",
            "【基础信息】",
            f"- 标题：{summary.title or '（无标题）'}",
            f"- 作者：{summary.author or '未知'}",
            f"- 发布时间：{publish}",
            f"- 原文：{summary.url}",
        ]
        if summary.risk_flags:
            lines.append(f"- 风险标签：{summary.risk_flags}")

        lines.extend(
            [
                "",
                "【摘要详情】",
                NotificationChannel._normalize_multiline(summary.summary),
            ]
        )
        return "\n".join(lines).strip()

    @staticmethod
    def _normalize_multiline(text: str) -> str:
        raw = (text or "").replace("\r\n", "\n").strip()
        if not raw:
            return "（空）"

        lines = [line.rstrip() for line in raw.split("\n")]
        compact: list[str] = []
        blank = False
        for line in lines:
            if not line.strip():
                if not blank:
                    compact.append("")
                blank = True
                continue
            compact.append(line)
            blank = False
        return "\n".join(compact).strip()


class NotificationRouter:
    def __init__(self, channels: list[NotificationChannel], logger) -> None:
        self.channels = channels
        self.logger = logger

    def dispatch_summary(self, run_id: str, summary: SummaryRecord, channel_names: list[str] | None = None) -> list[SendLogRecord]:
        logs: list[SendLogRecord] = []
        for channel in self._iter_channels(channel_names):
            try:
                result = channel.send_summary(summary)
            except Exception as exc:
                result = SendResult(status="failed", response=f"unexpected error: {exc}")
            logs.append(
                SendLogRecord(
                    run_id=run_id,
                    note_id=summary.note_id,
                    channel=channel.name,
                    send_status=result.status,
                    send_response=result.response,
                )
            )
        return logs

    # backward compatibility for old pipeline/tests
    def dispatch(self, run_id: str, summary: SummaryRecord) -> list[SendLogRecord]:
        return self.dispatch_summary(run_id=run_id, summary=summary, channel_names=None)

    def dispatch_digest(
        self,
        run_id: str,
        subject: str,
        text: str,
        attachments: list[str] | None = None,
        channel_names: list[str] | None = None,
    ) -> list[SendLogRecord]:
        logs: list[SendLogRecord] = []
        digest_note_id = f"digest:{run_id}"
        for channel in self._iter_channels(channel_names):
            try:
                result = channel.send_digest(subject=subject, text=text, attachments=attachments)
            except Exception as exc:
                result = SendResult(status="failed", response=f"unexpected error: {exc}")
            logs.append(
                SendLogRecord(
                    run_id=run_id,
                    note_id=digest_note_id,
                    channel=channel.name,
                    send_status=result.status,
                    send_response=result.response,
                )
            )
        return logs

    def _iter_channels(self, channel_names: list[str] | None):
        if not channel_names:
            return list(self.channels)
        allow = {name.strip() for name in channel_names if str(name).strip()}
        return [channel for channel in self.channels if channel.name in allow]
