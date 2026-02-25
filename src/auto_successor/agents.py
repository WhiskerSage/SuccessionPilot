from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape
from math import floor
from pathlib import Path

from .config import Settings
from .job_processor import normalize_job_record, to_job_record
from .llm_enricher import LLMEnricher
from .models import JobRecord, NoteRecord, SendLogRecord, SummaryRecord
from .notification_router import NotificationRouter

URGENT_TOKENS = ["急招", "尽快到岗", "马上到岗", "asap", "urgent", "立即入职"]


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
class BatchDispatchResult:
    sent: bool
    logs: list[SendLogRecord]
    subject: str
    body: str
    opportunity_post_ids: list[str]


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
            max_filter_items = new_count
            max_job_items = new_count
            max_summary_items = new_count
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
            "规划结果 | mode=%s | detail_fetch=%s | filter=%s | jobs=%s | summaries=%s | top_n=%s | full_llm=%s",
            plan.mode,
            plan.detail_fetch_limit,
            plan.max_filter_items,
            plan.max_job_items,
            plan.max_summary_items,
            plan.top_n,
            "on" if plan.max_filter_items >= new_count and plan.max_job_items >= new_count and plan.max_summary_items >= new_count else "off",
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
        total = len(notes)
        llm_budget = max(0, int(max_filter_items))
        progress_step = max(1, total // 5) if total > 0 else 1
        self.logger.info("[阶段] 目标筛选开始：总条数=%s，LLM配额=%s", total, llm_budget)

        for idx, note in enumerate(notes):
            allow_llm = idx < llm_budget
            decision = self.llm_enricher.classify_target(note, allow_llm=allow_llm)
            scores[note.note_id] = float(decision.score)
            if decision.is_target:
                targets.append(note)
            else:
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
                    "过滤帖子 | note=%s | score=%.2f | source=%s | reason=%s",
                    note.note_id,
                    decision.score,
                    decision.source,
                    decision.reason,
                )
            current = idx + 1
            if current == total or current % progress_step == 0:
                pct = int(round(current * 100 / max(1, total)))
                self.logger.info(
                    "[阶段进度] 目标筛选 %s/%s (%s%%) | 命中=%s | 过滤=%s",
                    current,
                    total,
                    pct,
                    len(targets),
                    len(filtered_out),
                )

        return FilterOutcome(targets=targets, filtered_out=filtered_out, scores=scores)

    def build_jobs(self, notes: list[NoteRecord], max_job_items: int, resume_text: str, mode: str) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        total = len(notes)
        llm_budget = max(0, int(max_job_items))
        progress_step = max(1, total // 5) if total > 0 else 1
        self.logger.info("[阶段] 岗位结构化开始：总条数=%s，LLM配额=%s", total, llm_budget)
        for idx, note in enumerate(notes):
            job = to_job_record(note)
            job.mode = mode
            if idx < llm_budget:
                job = self.llm_enricher.enrich_job(note, job, resume_text=resume_text, mode=mode)
            jobs.append(normalize_job_record(job))
            current = idx + 1
            if current == total or current % progress_step == 0:
                pct = int(round(current * 100 / max(1, total)))
                self.logger.info("[阶段进度] 岗位结构化 %s/%s (%s%%)", current, total, pct)
        jobs.sort(key=lambda item: item.publish_time, reverse=True)
        return jobs

    def mark_opportunities(self, jobs: list[JobRecord]) -> list[JobRecord]:
        if not jobs:
            return jobs

        max_score = max(float(item.match_score or 0.0) for item in jobs)
        if max_score <= 0.0:
            for job in jobs:
                job.opportunity_point = False
            return jobs

        limit = max(1, min(len(jobs), floor(len(jobs) * 0.3)))

        for job in jobs:
            job.opportunity_point = False

        ranked = sorted(
            jobs,
            key=lambda item: (
                self._is_urgent(item),
                float(item.match_score),
            ),
            reverse=True,
        )

        selected = ranked[:limit]
        if selected:
            selected[0].opportunity_point = True
        for item in selected:
            item.opportunity_point = True
        return jobs

    def attach_outreach_messages(self, jobs: list[JobRecord], resume_text: str) -> list[JobRecord]:
        opp_total = sum(1 for item in jobs if item.opportunity_point)
        self.logger.info("[阶段] 套磁生成开始：机会点岗位=%s", opp_total)
        for job in jobs:
            if not job.opportunity_point:
                job.outreach_message = ""
                continue
            job.outreach_message = self.llm_enricher.build_outreach_message(job, resume_text=resume_text)
        return jobs

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

    @staticmethod
    def _is_urgent(job: JobRecord) -> int:
        text = "\n".join([job.source_title or "", job.requirements or "", job.arrival_time or ""]).lower()
        return int(any(token in text for token in URGENT_TOKENS))


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
            original_text = (job.original_text or "").strip() or (job.requirements or "")
            lines.append(f"----------------------------------------")
            lines.append(f"[{idx}] {job.company} | {job.position}")
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
            original_text = (job.original_text or "").strip() or (job.requirements or "")
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
