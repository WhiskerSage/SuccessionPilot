from __future__ import annotations

from .config import Settings
from .agents_types import AgentPlan


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

__all__ = ["PlannerAgent"]
