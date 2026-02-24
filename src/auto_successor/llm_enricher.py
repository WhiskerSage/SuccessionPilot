from __future__ import annotations

from dataclasses import dataclass
import re

from .agent_memory import AgentMemoryLoader
from .llm_client import LLMClient
from .models import JobRecord, NoteRecord, SummaryRecord
from .succession import extract_apply_info, extract_arrival_info, extract_jd_full, extract_poster_comment_update

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

    def classify_target(self, note: NoteRecord, allow_llm: bool = True) -> FilterDecision:
        cfg = self.settings.llm
        rule_decision = self._rule_classify(note)
        if not getattr(cfg, "enabled_for_filter", True):
            return rule_decision

        if not (allow_llm and cfg.enabled and self.client.is_available()):
            return rule_decision

        system_prompt = (
            "你是帖子筛选助手。任务：判断该帖子是否属于“找继任/找接任的岗位交接信息”。"
            "严格返回 JSON，不要 markdown。"
            "字段：is_target(boolean), relevance_score(0-1), reason(string)。"
            "如果帖子是政治、军事、历史、娱乐剧情等非招聘语境，is_target 必须为 false。"
        )
        system_prompt = self._with_memory(system_prompt)
        user_prompt = (
            f"title: {note.title}\n"
            f"author: {note.author}\n"
            f"publish_time: {note.publish_time_text}\n"
            f"like_count: {note.like_count}\n"
            f"comment_count: {note.comment_count}\n"
            f"detail_text: {note.detail_text}\n"
            f"comments_preview: {note.comments_preview}\n"
            f"url: {note.url}\n"
        )
        self.calls += 1
        obj = self.client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        if not obj:
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
            # Strict mode: avoid false positive when only one side is confident.
            is_target = llm_target and llm_score >= threshold and (rule_decision.is_target or rule_decision.score >= 0.45)
            score = max(llm_score, rule_decision.score) if is_target else min(llm_score, rule_decision.score)
            return FilterDecision(is_target=is_target, score=score, reason=reason, source="hybrid")

        score = max(llm_score, rule_decision.score) if (llm_target or rule_decision.is_target) else min(
            llm_score, rule_decision.score
        )
        is_target = score >= threshold and (llm_target or rule_decision.is_target)
        return FilterDecision(is_target=is_target, score=score, reason=reason, source="hybrid")

    def enrich_job(self, note: NoteRecord, current: JobRecord) -> JobRecord:
        cfg = self.settings.llm
        if not (cfg.enabled and cfg.enabled_for_jobs and self.client.is_available()):
            return current

        system_prompt = (
            "你是岗位信息结构化助手。"
            "请从输入帖子信息中抽取岗位字段，输出严格 JSON，不要 markdown。"
            "字段: company, position, location, requirements。"
            "缺失时填'未知'。requirements 最多两条，用中文分号拼接。"
        )
        system_prompt = self._with_memory(system_prompt)
        user_prompt = (
            f"title: {note.title}\n"
            f"author: {note.author}\n"
            f"publish_time: {note.publish_time_text}\n"
            f"detail_text: {note.detail_text}\n"
            f"comments_preview: {note.comments_preview}\n"
            f"url: {note.url}\n"
        )
        self.calls += 1
        obj = self.client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        if not obj:
            self.fail += 1
            return current

        try:
            company = str(obj.get("company") or current.company).strip() or current.company
            position = str(obj.get("position") or current.position).strip() or current.position
            location = str(obj.get("location") or current.location).strip() or current.location
            requirements_raw = obj.get("requirements")
            if isinstance(requirements_raw, list):
                requirements = "；".join(self._clean_line(str(item)) for item in requirements_raw if str(item).strip())
            else:
                requirements = str(requirements_raw or current.requirements).strip() or current.requirements
            self.success += 1
            current.company = self._clean_line(company)[:60] or "未知"
            current.position = self._clean_line(position)[:80] or "未知"
            current.location = self._clean_line(location)[:40] or "未知"
            current.requirements = self._clean_line(requirements)[:180] or "未提取到明确要求"
        except Exception:
            self.fail += 1
        return current

    def enrich_summary(self, note: NoteRecord, current: SummaryRecord, mode: str = "auto") -> SummaryRecord:
        cfg = self.settings.llm
        if not (cfg.enabled and cfg.enabled_for_summary and self.client.is_available()):
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
        obj = self.client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
        if not obj:
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
    def _clean_line(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    def _with_memory(self, system_prompt: str) -> str:
        if not self.system_prefix:
            return system_prompt
        return f"{self.system_prefix}\n\n[Current Task]\n{system_prompt}"

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
