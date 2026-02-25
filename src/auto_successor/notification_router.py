from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape

from .models import SendLogRecord, SendResult, SummaryRecord


@dataclass
class NotificationChannel:
    name: str
    sender: object

    def send_summary(self, summary: SummaryRecord) -> SendResult:
        body = self._format_single_summary(summary)
        html = self._format_single_summary_html(summary)
        if self.name == "email":
            subject = f"SuccessionPilot | 线索 | {summary.title[:50]}"
            return self.sender.send_text_with_attachments(
                subject=subject,
                text=body,
                attachments=None,
                html=html,
            )
        return self.sender.send_text(body)

    def send_digest(
        self,
        subject: str,
        text: str,
        attachments: list[str] | None = None,
        html: str | None = None,
    ) -> SendResult:
        if self.name == "email":
            return self.sender.send_text_with_attachments(
                subject=subject,
                text=text,
                attachments=attachments,
                html=html,
            )
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
    def _format_single_summary_html(summary: SummaryRecord) -> str:
        publish = summary.publish_time.strftime("%Y-%m-%d %H:%M")

        def esc(v: object) -> str:
            return html_escape(str(v or ""))

        def esc_multiline(v: object) -> str:
            value = str(v or "").replace("\r\n", "\n").strip()
            if not value:
                return "（空）"
            return "<br>".join(esc(line) for line in value.split("\n"))

        risk_row = ""
        if summary.risk_flags:
            risk_row = f"<tr><td class=\"label\">风险标签</td><td class=\"value pre\">{esc_multiline(summary.risk_flags)}</td></tr>"

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SuccessionPilot 线索通知</title>
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 100%;
      background-color: #eef2f6;
    }}
    body, table, td, a {{
      -webkit-text-size-adjust: 100%;
      -ms-text-size-adjust: 100%;
    }}
    table {{
      border-collapse: collapse;
      border-spacing: 0;
    }}
    body {{
      color: #1f2937;
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
      font-size: 96%;
      line-height: 1.6;
    }}
    .shell {{
      width: 100%;
      background-color: #eef2f6;
    }}
    .container {{
      width: 100%;
      max-width: 54rem;
      margin: 0 auto;
      background-color: #ffffff;
      border: 1px solid #d7dde7;
    }}
    .pad {{
      padding: 1.125rem 1.25rem;
    }}
    .title {{
      margin: 0;
      font-size: 1.25em;
      font-weight: 700;
      line-height: 1.35;
      color: #0f172a;
    }}
    .section-title {{
      margin: 1.125rem 0 0.625rem;
      font-size: 1em;
      font-weight: 700;
      line-height: 1.35;
      color: #111827;
    }}
    .meta {{
      width: 100%;
      margin-bottom: 0.875rem;
      border: 1px solid #d7dde7;
    }}
    .label {{
      width: 24%;
      min-width: 5rem;
      padding: 0.5625rem 0.6875rem;
      border-top: 1px solid #e2e8f0;
      background-color: #f8fafc;
      color: #111827;
      font-weight: 600;
      vertical-align: top;
      white-space: nowrap;
    }}
    .value {{
      padding: 0.5625rem 0.6875rem;
      border-top: 1px solid #e2e8f0;
      background-color: #ffffff;
      color: #1f2937;
      vertical-align: top;
      word-break: break-word;
      overflow-wrap: anywhere;
    }}
    .pre {{
      white-space: pre-wrap;
    }}
    .link a {{
      color: #0b57d0;
      text-decoration: none;
      word-break: break-all;
    }}
    .footer {{
      margin: 0.75rem 0 0;
      color: #6b7280;
      font-size: 0.875em;
    }}
    @media screen and (max-width: 40rem) {{
      .pad {{
        padding: 0.875rem 0.75rem !important;
      }}
      .title {{
        font-size: 1.0625em !important;
      }}
      .section-title {{
        font-size: 0.95em !important;
      }}
      .label {{
        width: 32% !important;
        white-space: normal !important;
      }}
    }}
  </style>
</head>
<body>
  <table role="presentation" class="shell" width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding: 0.875rem 0.5rem;">
        <!--[if mso]>
        <table role="presentation" width="864" cellpadding="0" cellspacing="0"><tr><td>
        <![endif]-->
        <table role="presentation" class="container" width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td class="pad">
              <p class="title">SuccessionPilot 线索通知</p>

              <p class="section-title">基础信息</p>
              <table role="presentation" class="meta" cellpadding="0" cellspacing="0">
                <tr><td class="label">标题</td><td class="value pre">{esc_multiline(summary.title or "（无标题）")}</td></tr>
                <tr><td class="label">作者</td><td class="value">{esc(summary.author or "未知")}</td></tr>
                <tr><td class="label">发布时间</td><td class="value">{esc(publish)}</td></tr>
                <tr><td class="label">原文</td><td class="value link"><a href="{esc(summary.url)}">{esc(summary.url)}</a></td></tr>
                {risk_row}
              </table>

              <p class="section-title">摘要详情</p>
              <table role="presentation" class="meta" cellpadding="0" cellspacing="0">
                <tr><td class="value pre">{esc_multiline(summary.summary)}</td></tr>
              </table>

              <p class="footer">由 SuccessionPilot 自动生成。</p>
            </td>
          </tr>
        </table>
        <!--[if mso]></td></tr></table><![endif]-->
      </td>
    </tr>
  </table>
</body>
</html>"""

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
        html: str | None = None,
        attachments: list[str] | None = None,
        channel_names: list[str] | None = None,
    ) -> list[SendLogRecord]:
        logs: list[SendLogRecord] = []
        digest_note_id = f"digest:{run_id}"
        for channel in self._iter_channels(channel_names):
            try:
                result = channel.send_digest(subject=subject, text=text, attachments=attachments, html=html)
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
