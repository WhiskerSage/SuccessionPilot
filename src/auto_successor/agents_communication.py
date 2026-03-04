from __future__ import annotations

from html import escape as html_escape
from pathlib import Path

from .config import Settings
from .llm_enricher import LLMEnricher
from .models import JobRecord, NoteRecord, SendLogRecord, SummaryRecord
from .notification_router import NotificationRouter
from .agents_types import BatchDispatchResult, DigestDispatchResult


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
        html = self._build_body_html(
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
            html=html,
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

    def build_retry_fallback_message(
        self,
        *,
        run_id: str,
        mode: str,
        jobs: list[JobRecord],
        attachments: list[str],
        reason: str,
    ) -> tuple[str, str]:
        subject = self._build_subject(
            run_id=run_id,
            mode=mode,
            jobs=jobs,
            headline="notification retry",
        )
        body = self._build_body(
            run_id=run_id,
            mode=mode,
            jobs=jobs,
            headline="notification retry",
            overview=f"主流程通知失败，已写入重试队列。reason={reason}",
            attachments=attachments,
        )
        return subject, body

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
        # Keep subject short for mobile inbox readability.
        return f"SuccessionPilot | 岗位{len(jobs)} | 机会点{opp} | {run_id}"

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
            "SuccessionPilot 岗位批次通知",
            "========================================",
            f"运行ID：{run_id}",
            f"运行模式：{mode}",
            f"岗位数量：{len(jobs)}",
            f"机会点数量：{len(opp_jobs)}",
            "",
            "【批次标题】",
            *self._wrap_text(headline or "-"),
            "",
            "【批次概览】",
            *self._wrap_text(overview or "-"),
            "",
            "【附件】",
        ]
        if att:
            lines.extend([f"- {name}" for name in att])
        else:
            lines.append("- 无")

        if opp_jobs:
            lines.extend(["", "【机会点（优先跟进）】"])
            for idx, job in enumerate(opp_jobs, start=1):
                lines.append(f"[机会点 {idx}] {job.company} | {job.position}")
                lines.append(f"地点：{job.location}")
                lines.append(f"到岗：{job.arrival_time}")
                lines.append(f"投递：{job.application_method}")
                lines.append(f"匹配度：{job.match_score:.2f}")
                lines.append(f"链接：{job.link}")
                if job.outreach_message:
                    lines.append("套磁文案：")
                    lines.extend(self._indent_lines(self._wrap_text(job.outreach_message), prefix="  "))
                lines.append("")

        lines.extend(["【岗位详情】"])
        for idx, job in enumerate(jobs, start=1):
            original_text = self._display_original_text(job)
            lines.append(f"----------------------------------------")
            lines.append(f"[{idx}] {job.company} | {job.position}")
            lines.append(f"帖子标题：{job.source_title or '-'}")
            lines.append(f"发布时间：{job.publish_time.strftime('%Y-%m-%d %H:%M')}")
            lines.append(f"地点：{job.location}")
            lines.append("岗位要求：")
            lines.extend(self._indent_lines(self._wrap_text(job.requirements), prefix="  "))
            lines.append(f"到岗时间：{job.arrival_time}")
            lines.append(f"投递方式：{job.application_method}")
            lines.append(f"发布者：{job.author}")
            lines.append(f"简历匹配度：{job.match_score:.2f}")
            lines.append("原文：")
            lines.extend(self._indent_lines(self._wrap_text(original_text), prefix="  "))
            lines.append(f"链接：{job.link}")
            lines.append(f"机会点：{'是' if job.opportunity_point else '否'}")
            if job.outreach_message:
                lines.append("套磁文案：")
                lines.extend(self._indent_lines(self._wrap_text(job.outreach_message), prefix="  "))
            lines.append("")

        return "\n".join(lines).strip()

    def _build_body_html(
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

        def esc(v: object) -> str:
            return html_escape(str(v or ""))

        def esc_multiline(v: object) -> str:
            value = str(v or "").strip()
            if not value:
                return "-"
            value = value.replace("\r\n", "\n")
            return "<br>".join(esc(line) for line in value.split("\n"))

        def esc_singleline(v: object) -> str:
            value = str(v or "").strip()
            return esc(value) if value else "-"

        summary_rows = "".join(
            [
                f"<tr><td class=\"label\">运行ID</td><td class=\"value\">{esc(run_id)}</td></tr>",
                f"<tr><td class=\"label\">运行模式</td><td class=\"value\">{esc(mode)}</td></tr>",
                f"<tr><td class=\"label\">岗位数量</td><td class=\"value\">{len(jobs)}</td></tr>",
                f"<tr><td class=\"label\">机会点数量</td><td class=\"value\">{len(opp_jobs)}</td></tr>",
            ]
        )

        attach_rows = "".join([f"<tr><td class=\"value\">{esc(name)}</td></tr>" for name in att]) if att else "<tr><td class=\"value\">无</td></tr>"

        opp_blocks = []
        for idx, job in enumerate(opp_jobs, start=1):
            outreach_row = ""
            if job.outreach_message:
                outreach_row = (
                    "<tr><td class=\"label\">套磁文案</td>"
                    f"<td class=\"value pre\">{esc_multiline(job.outreach_message)}</td></tr>"
                )
            opp_blocks.append(
                (
                    "<table role=\"presentation\" class=\"item\" cellpadding=\"0\" cellspacing=\"0\">"
                    f"<tr><td class=\"item-head\" colspan=\"2\">机会点 {idx} | {esc(job.company)} | {esc(job.position)}</td></tr>"
                    f"<tr><td class=\"label\">帖子标题</td><td class=\"value pre\">{esc_multiline(job.source_title)}</td></tr>"
                    f"<tr><td class=\"label\">地点</td><td class=\"value\">{esc_singleline(job.location)}</td></tr>"
                    f"<tr><td class=\"label\">到岗时间</td><td class=\"value\">{esc_singleline(job.arrival_time)}</td></tr>"
                    f"<tr><td class=\"label\">投递方式</td><td class=\"value pre\">{esc_multiline(job.application_method)}</td></tr>"
                    f"<tr><td class=\"label\">匹配度</td><td class=\"value\">{float(job.match_score or 0.0):.2f}</td></tr>"
                    f"<tr><td class=\"label\">链接</td><td class=\"value link\"><a href=\"{esc(job.link)}\">{esc(job.link)}</a></td></tr>"
                    f"{outreach_row}"
                    "</table>"
                )
            )
        opportunity_html = "".join(opp_blocks) if opp_blocks else "<table role=\"presentation\" class=\"empty\" cellpadding=\"0\" cellspacing=\"0\"><tr><td>无机会点。</td></tr></table>"

        detail_blocks = []
        for idx, job in enumerate(jobs, start=1):
            original_text = self._display_original_text(job)
            outreach_row = ""
            if job.outreach_message:
                outreach_row = (
                    "<tr><td class=\"label\">套磁文案</td>"
                    f"<td class=\"value pre\">{esc_multiline(job.outreach_message)}</td></tr>"
                )
            detail_blocks.append(
                (
                    "<table role=\"presentation\" class=\"item\" cellpadding=\"0\" cellspacing=\"0\">"
                    f"<tr><td class=\"item-head\" colspan=\"2\">[{idx}] {esc(job.company)} | {esc(job.position)}</td></tr>"
                    f"<tr><td class=\"label\">帖子标题</td><td class=\"value pre\">{esc_multiline(job.source_title)}</td></tr>"
                    f"<tr><td class=\"label\">发布时间</td><td class=\"value\">{esc(job.publish_time.strftime('%Y-%m-%d %H:%M'))}</td></tr>"
                    f"<tr><td class=\"label\">发布者</td><td class=\"value\">{esc_singleline(job.author)}</td></tr>"
                    f"<tr><td class=\"label\">地点</td><td class=\"value\">{esc_singleline(job.location)}</td></tr>"
                    f"<tr><td class=\"label\">机会点</td><td class=\"value\">{'是' if job.opportunity_point else '否'}</td></tr>"
                    f"<tr><td class=\"label\">到岗时间</td><td class=\"value\">{esc_singleline(job.arrival_time)}</td></tr>"
                    f"<tr><td class=\"label\">匹配度</td><td class=\"value\">{float(job.match_score or 0.0):.2f}</td></tr>"
                    f"<tr><td class=\"label\">投递方式</td><td class=\"value pre\">{esc_multiline(job.application_method)}</td></tr>"
                    f"<tr><td class=\"label\">岗位要求</td><td class=\"value pre\">{esc_multiline(job.requirements)}</td></tr>"
                    f"<tr><td class=\"label\">原文摘要</td><td class=\"value pre\">{esc_multiline(original_text)}</td></tr>"
                    f"<tr><td class=\"label\">链接</td><td class=\"value link\"><a href=\"{esc(job.link)}\">{esc(job.link)}</a></td></tr>"
                    f"{outreach_row}"
                    "</table>"
                )
            )
        details_html = "".join(detail_blocks) if detail_blocks else "<table role=\"presentation\" class=\"empty\" cellpadding=\"0\" cellspacing=\"0\"><tr><td>无岗位数据。</td></tr></table>"

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SuccessionPilot 岗位批次通知</title>
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
    .meta, .item, .empty {{
      width: 100%;
      margin-bottom: 0.875rem;
      border: 1px solid #d7dde7;
    }}
    .item-head {{
      padding: 0.625rem 0.75rem;
      background-color: #f2f5fa;
      border-bottom: 1px solid #d7dde7;
      font-size: 1em;
      font-weight: 700;
      color: #0f172a;
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
    .empty td {{
      padding: 0.6875rem 0.75rem;
      color: #6b7280;
      background-color: #fbfcfe;
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
        font-size: 1em !important;
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
              <p class="title">SuccessionPilot 岗位批次通知</p>

              <p class="section-title">运行摘要</p>
              <table role="presentation" class="meta" cellpadding="0" cellspacing="0">
                {summary_rows}
              </table>

              <p class="section-title">批次标题</p>
              <table role="presentation" class="meta" cellpadding="0" cellspacing="0">
                <tr><td class="value pre">{esc_multiline(headline or "-")}</td></tr>
              </table>

              <p class="section-title">批次概览</p>
              <table role="presentation" class="meta" cellpadding="0" cellspacing="0">
                <tr><td class="value pre">{esc_multiline(overview or "-")}</td></tr>
              </table>

              <p class="section-title">附件</p>
              <table role="presentation" class="meta" cellpadding="0" cellspacing="0">
                {attach_rows}
              </table>

              <p class="section-title">机会点（优先跟进）</p>
              {opportunity_html}

              <p class="section-title">岗位详情</p>
              {details_html}

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

    @classmethod
    def _display_original_text(cls, job: JobRecord) -> str:
        original_text = str(job.original_text or "").strip()
        requirements = str(job.requirements or "").strip()
        if original_text:
            if cls._is_duplicate_text(original_text, requirements):
                return "原文与岗位要求高度重合，建议查看原帖链接获取完整上下文。"
            return original_text

        extras: list[str] = []
        title = str(job.source_title or "").strip()
        comments = str(job.comments_preview or "").strip()
        if title:
            extras.append(f"标题：{title}")
        if comments:
            extras.append(f"评论线索：{comments}")
        if extras:
            return "；".join(extras)[:700]
        return "未抓取到可用原文摘要，请查看原帖链接/图片。"

    @staticmethod
    def _is_duplicate_text(a: str, b: str) -> bool:
        left = CommunicationAgent._normalize_compare_text(a)
        right = CommunicationAgent._normalize_compare_text(b)
        if not left or not right:
            return False
        if left == right:
            return True
        short, long = (left, right) if len(left) <= len(right) else (right, left)
        if len(short) >= 24 and short in long:
            overlap = len(short) / max(1, len(long))
            return overlap >= 0.7
        return False

    @staticmethod
    def _normalize_compare_text(text: str) -> str:
        value = str(text or "").lower().strip()
        if not value:
            return ""
        return "".join(ch for ch in value if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")

    @staticmethod
    def _wrap_text(text: str, width: int = 70) -> list[str]:
        value = str(text or "").replace("\r\n", "\n").strip()
        if not value:
            return ["-"]
        out: list[str] = []
        for raw in value.split("\n"):
            line = raw.strip()
            if not line:
                out.append("")
                continue
            while len(line) > width:
                out.append(line[:width])
                line = line[width:]
            out.append(line)
        return out or ["-"]

    @staticmethod
    def _indent_lines(lines: list[str], prefix: str = "  ") -> list[str]:
        return [f"{prefix}{line}" if line else "" for line in lines]

__all__ = ["CommunicationAgent"]
