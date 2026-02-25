from __future__ import annotations

from dataclasses import dataclass
import json
import re

from .agent_memory import AgentMemoryLoader
from .llm_client import LLMClient
from .models import JobRecord, NoteRecord, SummaryRecord
from .succession import extract_apply_info, extract_arrival_info, extract_jd_full, extract_poster_comment_update
from .text_utils import clean_line

TARGET_TOKENS = [
    "继任",
    "找继任",
    "接任",
    "接班",
    "交接",
]

JOB_CONTEXT_TOKENS = [
    "实习",
    "招聘",
    "招人",
    "岗位",
    "简历",
    "面试",
    "offer",
    "base",
    "入职",
    "团队",
    "hc",
    "组内",
]

NEGATIVE_TOKENS = [
    "小说",
    "动漫",
    "剧情",
    "总统",
    "国家",
    "王位",
    "皇位",
    "政权",
    "历史",
]

HARD_NEGATIVE_TOKENS = [
    "军人",
    "军队",
    "部队",
    "军事",
    "战争",
    "政坛",
    "选举",
]

BROKER_TOKENS = ["中介", "代投", "内推收费", "保证入职", "保offer", "付费推荐", "代理"]


@dataclass
class FilterDecision:
    is_target: bool
    score: float
    reason: str
    source: str


class LLMEnricher:
    def __init__(self, llm_client: LLMClient, settings, logger) -> None:
        self.client = llm_client
        self.settings = settings
        self.logger = logger
        self.calls = 0
        self.success = 0
        self.fail = 0
        self._degrade_notice_filter = False
        self._degrade_notice_job = False
        self._degrade_notice_summary = False
        memory_loader = AgentMemoryLoader(
            global_path=self.settings.agent.global_memory_path,
            main_path=self.settings.agent.main_memory_path,
            max_chars=self.settings.agent.memory_max_chars,
        )
        self.memory = memory_loader.load()
        self.system_prefix = self.memory.as_system_prefix()

    def reset_stats(self) -> None:
        self.calls = 0
        self.success = 0
        self.fail = 0
        self._degrade_notice_filter = False
        self._degrade_notice_job = False
        self._degrade_notice_summary = False

    def classify_target(self, note: NoteRecord, allow_llm: bool = True) -> FilterDecision:
        cfg = self.settings.llm
        rule_decision = self._rule_classify(note)
        if not getattr(cfg, "enabled_for_filter", True):
            return rule_decision

        if not (allow_llm and cfg.enabled and self.client.is_available()):
            if allow_llm and cfg.enabled and (not self._degrade_notice_filter):
                self.logger.warning("llm degraded: filter stage fallback to rule-only")
                self._degrade_notice_filter = True
            return rule_decision

        system_prompt = (
            "你是帖子筛选助手。"
            "判断是否是“找继任/接任的招聘帖子”。"
            "只返回JSON: {is_target, relevance_score, reason}。"
            "政治/军事/历史/剧情语境必须false。"
        )
        system_prompt = self._with_memory(system_prompt)
        user_prompt = (
            f"title: {note.title}\n"
            f"detail_text: {note.detail_text}\n"
            f"comments_preview: {note.comments_preview}\n"
        )
        self.calls += 1
        obj = self.client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, model=self._parse_model())
        if not obj:
            self.logger.warning("llm fallback(filter): note=%s use=rule", note.note_id)
            self.fail += 1
            return rule_decision

        try:
            llm_target = self._to_bool(obj.get("is_target"))
            llm_score = self._clamp_score(obj.get("relevance_score", rule_decision.score))
            reason = self._clean_line(str(obj.get("reason") or ""))[:120] or rule_decision.reason
            self.success += 1
        except Exception:
            self.fail += 1
            return rule_decision

        threshold = self._clamp_score(getattr(cfg, "filter_threshold", 0.62))
        strict_filter = bool(getattr(cfg, "strict_filter", True))
        text = self._note_text(note)
        has_hard_negative = any(token in text for token in HARD_NEGATIVE_TOKENS)
        has_job_context = any(token in text for token in JOB_CONTEXT_TOKENS)
        has_non_job_negation = bool(re.search(r"(不是|非|无关).{0,3}(招聘|招人|岗位|实习)", text))

        if has_hard_negative and (not has_job_context or has_non_job_negation):
            return FilterDecision(
                is_target=False,
                score=min(rule_decision.score, llm_score),
                reason="命中政治/军事类非目标主题",
                source="hybrid",
            )

        if strict_filter:
            is_target = llm_target and llm_score >= threshold and (rule_decision.is_target or rule_decision.score >= 0.45)
            score = max(llm_score, rule_decision.score) if is_target else min(llm_score, rule_decision.score)
            return FilterDecision(is_target=is_target, score=score, reason=reason, source="hybrid")

        score = max(llm_score, rule_decision.score) if (llm_target or rule_decision.is_target) else min(
            llm_score, rule_decision.score
        )
        is_target = score >= threshold and (llm_target or rule_decision.is_target)
        return FilterDecision(is_target=is_target, score=score, reason=reason, source="hybrid")

    def enrich_job(self, note: NoteRecord, current: JobRecord, resume_text: str, mode: str) -> JobRecord:
        cfg = self.settings.llm
        current.mode = (mode or "auto").strip().lower() or "auto"
        current.parse_source = "rule"
        current.author = note.author
        current.arrival_time = current.arrival_time or extract_arrival_info(note.detail_text or "")[:120]
        current.application_method = current.application_method or extract_apply_info(note.detail_text or "")[:180]
        current.risk_line = current.risk_line or self._infer_risk_line(note)
        current.match_score = self._fallback_match_score(note, resume_text)
        current.match_reason = current.match_reason or "rule fallback"

        if not (cfg.enabled and cfg.enabled_for_jobs and self.client.is_available()):
            if cfg.enabled and cfg.enabled_for_jobs and (not self._degrade_notice_job):
                self.logger.warning("llm degraded: job extraction fallback to rule fields")
                self._degrade_notice_job = True
            return current

        system_prompt = (
            "你是岗位结构化提取助手。"
            "基于帖子与简历文本，输出严格 JSON（英文字段名，不要 markdown）。"
            "字段: company, position, publish_time, location, requirements, arrival_time, application_method, author, risk_line, match_score, match_reason, link, post_id, mode。"
            "其中 risk_line 只能是 low|medium|high，并按正文判断是否可能是中介广告。"
            "match_score 范围 0-100。"
        )
        system_prompt = self._with_memory(system_prompt)
        user_prompt = (
            f"resume_text: {resume_text}\n"
            f"title: {note.title}\n"
            f"author: {note.author}\n"
            f"publish_time: {note.publish_time.isoformat()}\n"
            f"detail_text: {note.detail_text}\n"
            f"comments_preview: {note.comments_preview}\n"
            f"url: {note.url}\n"
            f"mode: {mode}\n"
        )
        self.calls += 1
        obj = self.client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, model=self._parse_model())
        if not obj:
            self.logger.warning("llm fallback(job): note=%s use=rule_fields", note.note_id)
            self.fail += 1
            return current

        try:
            current.company = self._pick_text(obj, "company", current.company, 60)
            current.position = self._pick_text(obj, "position", current.position, 80)
            current.location = self._pick_text(obj, "location", current.location, 40)
            current.requirements = self._pick_text(obj, "requirements", current.requirements, 380)
            current.arrival_time = self._pick_text(obj, "arrival_time", current.arrival_time, 120)
            current.application_method = self._pick_text(obj, "application_method", current.application_method, 180)
            current.author = self._pick_text(obj, "author", current.author, 80)
            risk_line = self._pick_text(obj, "risk_line", current.risk_line, 20).lower()
            if risk_line not in {"low", "medium", "high"}:
                risk_line = self._infer_risk_line(note)
            current.risk_line = risk_line
            current.match_score = self._clamp_score_100(obj.get("match_score"), default=current.match_score)
            current.match_reason = self._pick_text(obj, "match_reason", current.match_reason, 220)
            current.link = self._pick_text(obj, "link", current.link or note.url, 600)
            current.post_id = self._pick_text(obj, "post_id", current.post_id or note.note_id, 120)
            current.mode = self._pick_text(obj, "mode", current.mode or mode, 20)
            current.parse_source = "llm"
            self.success += 1
        except Exception:
            self.fail += 1
        return current

    def summarize_push_batch(self, *, run_id: str, mode: str, jobs: list[JobRecord], resume_text: str) -> dict:
        if not jobs:
            return {
                "headline": f"run {run_id}: no new target jobs",
                "overview": "本轮没有可推送的目标岗位。",
            }

        cfg = self.settings.llm
        fallback = self._fallback_batch_summary(run_id=run_id, mode=mode, jobs=jobs)
        if not (cfg.enabled and cfg.enabled_for_summary and self.client.is_available()):
            return fallback

        system_prompt = (
            "你是岗位批次摘要助手。"
            "基于岗位结构化信息与简历文本，输出严格 JSON（英文字段名）。"
            "字段: headline, overview。"
            "overview 控制在 120-220 中文字符，突出本轮机会点与风险。"
        )
        compact_jobs = [
            {
                "company": item.company,
                "position": item.position,
                "location": item.location,
                "requirements": item.requirements[:240],
                "arrival_time": item.arrival_time,
                "application_method": item.application_method,
                "risk_line": item.risk_line,
                "match_score": round(item.match_score, 2),
                "post_id": item.post_id,
                "opportunity_point": bool(item.opportunity_point),
            }
            for item in jobs
        ]
        user_prompt = (
            f"run_id: {run_id}\n"
            f"mode: {mode}\n"
            f"resume_text: {resume_text}\n"
            f"jobs_json: {json.dumps(compact_jobs, ensure_ascii=False)}\n"
        )

        self.calls += 1
        obj = self.client.chat_json(
            system_prompt=self._with_memory(system_prompt),
            user_prompt=user_prompt,
            model=self._parse_model(),
        )
        if not obj:
            self.fail += 1
            return fallback

        try:
            headline = self._pick_text(obj, "headline", fallback["headline"], 140)
            overview = self._pick_text(obj, "overview", fallback["overview"], 420)
            self.success += 1
            return {"headline": headline, "overview": overview}
        except Exception:
            self.fail += 1
            return fallback

    def build_outreach_message(self, job: JobRecord, resume_text: str) -> str:
        system_prompt = self._with_memory(
            "你是一名求职邮件撰写助手。"
            "请根据候选人简历与岗位信息，生成一封简短、专业、真诚的中文套磁邮件。"
            "必须遵守："
            "1) 输出为邮件格式（含主题和正文）；"
            "2) 正文先自我介绍：姓名、院校、专业、毕业年份（若缺失可写“信息未提供”）；"
            "3) 默认可立即到岗（除非简历明确给出其他时间）；"
            "4) 说明2-3条与岗位匹配点；"
            "5) 不得出现“匹配度XX分/评分/打分/算法”等表述；"
            "6) 语气礼貌，长度约100-140字；"
            "7) 仅输出邮件文本，不要Markdown，不要解释。"
        )

        user_prompt = (
            f"岗位信息：\n"
            f"- Company: {job.company}\n"
            f"- Position: {job.position}\n"
            f"- Location: {job.location}\n"
            f"- Requirements: {job.requirements}\n"
            f"- arrival_time: {job.arrival_time}\n"
            f"- application_method: {job.application_method}\n"
            f"- Link: {job.link}\n\n"
            f"候选人简历原文：\n{resume_text}\n\n"
            "请按要求生成邮件。"
        )

        try:
            text = self.client.chat_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.4,
                max_tokens=260,
                model=self._outreach_model(),
            )
            cleaned = self._clean_line(text or "").replace("\\n", "\n").strip()
            if cleaned:
                return cleaned[:800]

            retry_prompt = (
                f"请直接输出中文邮件正文（含主题和称呼），不要解释。\n"
                f"岗位：{job.company}-{job.position}，地点：{job.location}。\n"
                f"岗位要求：{job.requirements}\n"
                f"候选人简历：{resume_text[:2200]}"
            )
            text_retry = self.client.chat_text(
                system_prompt="你是求职套磁文案助手，输出精炼中文邮件。",
                user_prompt=retry_prompt,
                temperature=0.3,
                max_tokens=260,
                model=self._outreach_model(),
            )
            cleaned_retry = self._clean_line(text_retry or "").replace("\\n", "\n").strip()
            if cleaned_retry:
                return cleaned_retry[:800]

            self.logger.warning("outreach llm returned empty content, fallback used for post=%s", job.post_id)
            return self._fallback_outreach_message(job)
        except Exception as exc:
            self.logger.warning("outreach llm failed for post=%s: %s", job.post_id, exc)
            return self._fallback_outreach_message(job)

    def _rule_classify(self, note: NoteRecord) -> FilterDecision:
        text = self._note_text(note)
        threshold = self._clamp_score(getattr(self.settings.llm, "filter_threshold", 0.62))

        target_hits = [token for token in TARGET_TOKENS if token in text]
        job_hits = [token for token in JOB_CONTEXT_TOKENS if token in text]
        negative_hits = [token for token in NEGATIVE_TOKENS if token in text]
        hard_negative_hits = [token for token in HARD_NEGATIVE_TOKENS if token in text]

        score = 0.18
        score += min(len(target_hits), 2) * 0.22
        score += min(len(job_hits), 3) * 0.13
        score -= min(len(negative_hits), 2) * 0.17
        score -= min(len(hard_negative_hits), 2) * 0.25
        if note.comment_count >= 20:
            score += 0.06
        if note.like_count >= 50:
            score += 0.04
        score = self._clamp_score(score)

        has_core_intent = bool(target_hits)
        has_job_intent = bool(job_hits)
        has_hard_negative = bool(hard_negative_hits)

        is_target = has_core_intent and score >= threshold and (has_job_intent or not has_hard_negative)
        if has_hard_negative and not has_job_intent:
            is_target = False
            score = min(score, 0.35)

        reason_parts = []
        if target_hits:
            reason_parts.append(f"target={','.join(target_hits[:3])}")
        if job_hits:
            reason_parts.append(f"job={','.join(job_hits[:3])}")
        if hard_negative_hits:
            reason_parts.append(f"hard_neg={','.join(hard_negative_hits[:2])}")
        elif negative_hits:
            reason_parts.append(f"neg={','.join(negative_hits[:2])}")
        reason = " | ".join(reason_parts) if reason_parts else "rule_only"
        return FilterDecision(is_target=is_target, score=score, reason=reason, source="rule")

    def _parse_model(self) -> str:
        cfg = self.settings.llm
        return (getattr(cfg, "parse_model", "") or "").strip() or cfg.model

    def _outreach_model(self) -> str:
        cfg = self.settings.llm
        return (getattr(cfg, "outreach_model", "") or "").strip() or cfg.model

    @staticmethod
    def _note_text(note: NoteRecord) -> str:
        return "\n".join(
            [
                note.title or "",
                note.detail_text or "",
                note.comments_preview or "",
            ]
        ).lower()

    @staticmethod
    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "是", "对"}

    @staticmethod
    def _clamp_score(value) -> float:
        try:
            score = float(value)
        except Exception:
            score = 0.0
        return max(0.0, min(1.0, score))

    @staticmethod
    def _clamp_score_100(value, default: float = 0.0) -> float:
        try:
            score = float(value)
        except Exception:
            score = float(default or 0.0)
        return max(0.0, min(100.0, score))

    @staticmethod
    def _clean_line(text: str) -> str:
        return clean_line(text)

    def _with_memory(self, system_prompt: str) -> str:
        if not self.system_prefix:
            return system_prompt
        return f"{self.system_prefix}\n\n[Current Task]\n{system_prompt}"

    def _pick_text(self, obj: dict, key: str, default: str, max_len: int) -> str:
        text = self._clean_line(str(obj.get(key) or default or ""))
        if not text:
            text = self._clean_line(str(default or ""))
        return text[:max_len]

    def _infer_risk_line(self, note: NoteRecord) -> str:
        text = self._note_text(note)
        broker_hits = sum(1 for token in BROKER_TOKENS if token in text)
        if broker_hits >= 2:
            return "high"
        if broker_hits == 1:
            return "medium"
        return "low"

    def _fallback_match_score(self, note: NoteRecord, resume_text: str) -> float:
        if not resume_text.strip():
            return 50.0
        note_text = self._note_text(note)
        resume_tokens = [token for token in self._tokenize(resume_text) if len(token) >= 2]
        if not resume_tokens:
            return 50.0
        hit = sum(1 for token in resume_tokens[:80] if token in note_text)
        ratio = hit / max(6, min(len(resume_tokens), 80))
        return round(max(0.0, min(100.0, ratio * 160)), 2)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", (text or "").lower())
        return [item.strip() for item in clean.split() if item.strip()]

    def _fallback_batch_summary(self, *, run_id: str, mode: str, jobs: list[JobRecord]) -> dict:
        opp_count = sum(1 for item in jobs if item.opportunity_point)
        max_score = max((float(item.match_score or 0.0) for item in jobs), default=0.0)
        if max_score <= 0:
            opportunity_desc = "未发现明显机会点"
        else:
            top = [item for item in sorted(jobs, key=lambda item: item.match_score, reverse=True) if float(item.match_score or 0.0) > 0][:3]
            top_text = "；".join(f"{item.company}-{item.position}" for item in top) or "未发现明显机会点"
            opportunity_desc = f"机会点关注：{top_text}"
        return {
            "headline": f"SuccessionPilot batch summary | run={run_id} | jobs={len(jobs)} | opp={opp_count}",
            "overview": f"本轮模式 {mode}，共识别 {len(jobs)} 个岗位，机会点 {opp_count} 个。{opportunity_desc}。",
        }

    def _fallback_outreach_message(self, job: JobRecord) -> str:
        return (
            f"主题：应聘{job.company}-{job.position}\n"
            "您好，\n"
            "我叫张三，XX大学XX专业，预计202X年毕业，可立即到岗。"
            "我在相关项目中积累了与岗位相关的实践经验，具备数据分析与协同执行能力，"
            "期待有机会进一步沟通。感谢您的时间！"
        )[:800]

    # backward compatibility for legacy callers/tests
    def enrich_summary(self, note: NoteRecord, current: SummaryRecord, mode: str = "auto") -> SummaryRecord:
        cfg = self.settings.llm
        if not (cfg.enabled and cfg.enabled_for_summary and self.client.is_available()):
            if cfg.enabled and cfg.enabled_for_summary and (not self._degrade_notice_summary):
                self.logger.warning("llm degraded: summary generation fallback to local summary")
                self._degrade_notice_summary = True
            return current
        mode = (mode or "auto").strip().lower()
        if mode == "smart":
            mode = "agent"
        if mode not in {"auto", "agent"}:
            mode = "auto"
        agent_mode = mode == "agent"

        if agent_mode:
            system_prompt = (
                "你是继任信息分析助手。"
                "基于输入生成详细中文摘要，输出严格 JSON，不要 markdown。"
                "字段: detail_summary, poster_comment_update, jd_full, apply_info, arrival_info, risk_flags。"
                "detail_summary 150-320 字，poster_comment_update 只写“贴主是否有补充信息”，不要总结普通评论。"
                "jd_full 尽可能完整提取岗位职责/要求；无则返回空字符串。"
                "apply_info 提取投递方式；arrival_info 提取到岗时间。"
                "内容必须事实化，不编造。"
            )
        else:
            system_prompt = (
                "你是继任信息分析助手。"
                "基于输入生成详细中文摘要，输出严格 JSON，不要 markdown。"
                "字段: detail_summary, poster_comment_update, risk_flags。"
                "detail_summary 120-260 字；poster_comment_update 只写“贴主是否有补充信息”，不需要评论总结。"
                "risk_flags 用逗号分隔，若无填空字符串。"
            )
        system_prompt = self._with_memory(system_prompt)
        user_prompt = (
            f"title: {note.title}\n"
            f"author: {note.author}\n"
            f"publish_time: {note.publish_time_text}\n"
            f"like_count: {note.like_count}\n"
            f"comment_count: {note.comment_count}\n"
            f"share_count: {note.share_count}\n"
            f"detail_text: {note.detail_text}\n"
            f"comments_preview: {note.comments_preview}\n"
            f"url: {note.url}\n"
            f"mode: {mode}\n"
            "要求：如果正文/评论缺失，要明确说明信息缺口，不要编造。"
        )
        self.calls += 1
        obj = self.client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt, model=self._parse_model())
        if not obj:
            self.logger.warning("llm fallback(summary): note=%s use=local_summary", note.note_id)
            self.fail += 1
            return current

        try:
            detail_summary = self._clean_line(str(obj.get("detail_summary") or ""))[:320]
            poster_comment_update = self._normalize_poster_comment_update(
                str(obj.get("poster_comment_update") or obj.get("comment_summary") or "")
            )
            jd_full = self._clean_line(str(obj.get("jd_full") or ""))[:1800]
            apply_info = self._clean_line(str(obj.get("apply_info") or ""))[:180]
            arrival_info = self._clean_line(str(obj.get("arrival_info") or ""))[:140]
            risk_flags = str(obj.get("risk_flags") or current.risk_flags).strip()

            if not detail_summary:
                detail_summary = self._fallback_detail_summary(note)
            if not poster_comment_update:
                poster_comment_update = self._fallback_poster_comment_update(note)
            if not jd_full:
                jd_full = self._fallback_jd_full(note, smart_mode=agent_mode)
            if not apply_info:
                apply_info = self._fallback_apply_info(note)
            if not arrival_info:
                arrival_info = self._fallback_arrival_info(note)

            current.summary = self._compose_standard_summary(
                note=note,
                detail_summary=detail_summary,
                poster_comment_update=poster_comment_update,
                jd_full=jd_full,
                apply_info=apply_info,
                arrival_info=arrival_info,
                risk_flags=risk_flags,
                mode=mode,
            )
            current.confidence = 1.0
            current.risk_flags = self._clean_line(risk_flags)[:200]
            self.success += 1
        except Exception:
            self.fail += 1
        return current

    def _compose_standard_summary(
        self,
        note: NoteRecord,
        detail_summary: str,
        poster_comment_update: str,
        jd_full: str,
        apply_info: str,
        arrival_info: str,
        risk_flags: str,
        mode: str,
    ) -> str:
        title = note.title or "(无标题)"
        risk_line = self._clean_line(risk_flags) or "无"
        mode = (mode or "auto").strip().lower()
        if mode == "agent":
            jd_line = jd_full or "未提取到完整JD（可查看原帖图片/附件）"
        else:
            jd_line = (jd_full or "未提取到完整JD（可查看原帖图片/附件）")[:360]
        return (
            f"【继任追踪】{title}\n"
            f"作者：{note.author or '未知'}\n"
            f"发布时间：{note.publish_time_text or note.publish_time.strftime('%Y-%m-%d')}\n"
            f"互动：赞{note.like_count} 评{note.comment_count} 转{note.share_count}\n"
            f"正文信息（详细）：{detail_summary or '暂无'}\n"
            f"贴主补充评论：{poster_comment_update or '未见贴主补充评论'}\n"
            f"到岗信息：{arrival_info or '未明确'}\n"
            f"投递方式：{apply_info or '未明确'}\n"
            f"JD全文：{jd_line}\n"
            f"风险标记：{risk_line}\n"
            f"链接：{note.url}"
        )

    def _fallback_detail_summary(self, note: NoteRecord) -> str:
        detail = self._clean_line(note.detail_text)[:380]
        if detail:
            return detail
        title = self._clean_line(note.title)[:120]
        if title:
            return f"帖子可见信息主要来自标题：{title}。当前未抓取到稳定正文，建议人工点开原帖确认岗位要求、地点与投递方式。"
        return "当前未抓取到稳定正文，建议人工点开原帖确认岗位要求、地点与投递方式。"

    def _fallback_poster_comment_update(self, note: NoteRecord) -> str:
        return extract_poster_comment_update(
            comments_preview=note.comments_preview or "",
            comment_count=note.comment_count,
        )

    def _normalize_poster_comment_update(self, text: str) -> str:
        value = self._clean_line(text)
        if not value:
            return ""
        if re.search(r"(否|没有|无|未|none|no)", value, flags=re.IGNORECASE):
            return "未见贴主补充评论。"
        if re.search(r"(有|补充|更新|回复|yes)", value, flags=re.IGNORECASE):
            return "检测到贴主有补充评论，建议查看原帖评论区。"
        return value[:220]

    def _fallback_jd_full(self, note: NoteRecord, smart_mode: bool) -> str:
        jd = extract_jd_full(note.detail_text or "")
        if not jd:
            return ""
        if smart_mode:
            return jd[:1800]
        return jd[:360]

    @staticmethod
    def _fallback_apply_info(note: NoteRecord) -> str:
        return extract_apply_info(note.detail_text or "")[:180]

    @staticmethod
    def _fallback_arrival_info(note: NoteRecord) -> str:
        return extract_arrival_info(note.detail_text or "")[:140]
