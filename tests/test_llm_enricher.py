from __future__ import annotations

import unittest
from datetime import datetime, timezone

from auto_successor.config import (
    AppConfig,
    EmailConfig,
    LLMConfig,
    PipelineConfig,
    Settings,
    StorageConfig,
    WeChatServiceConfig,
    XHSConfig,
)
from auto_successor.llm_enricher import LLMEnricher
from auto_successor.models import NoteRecord
from auto_successor.succession import build_summary


def _build_settings(llm_enabled: bool) -> Settings:
    return Settings(
        app=AppConfig(),
        xhs=XHSConfig(),
        pipeline=PipelineConfig(min_confidence=0.55),
        llm=LLMConfig(
            enabled=llm_enabled,
            enabled_for_jobs=True,
            enabled_for_summary=True,
            enabled_for_filter=True,
            filter_threshold=0.62,
            strict_filter=True,
        ),
        wechat_service=WeChatServiceConfig(),
        email=EmailConfig(),
        storage=StorageConfig(),
    )


def _note(title: str, detail: str = "", comments: str = "") -> NoteRecord:
    return NoteRecord(
        run_id="r1",
        keyword="继任",
        note_id=f"n-{abs(hash(title)) % 100000}",
        title=title,
        author="tester",
        publish_time=datetime.now(timezone.utc),
        publish_time_text="2026-02-23",
        like_count=80,
        comment_count=36,
        share_count=5,
        url="https://www.xiaohongshu.com/explore/abc",
        raw_json="{}",
        detail_text=detail,
        comments_preview=comments,
    )


class _NullLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class _FakeClient:
    def __init__(self, available: bool, filter_resp=None, summary_resp=None):
        self._available = available
        self._filter_resp = filter_resp
        self._summary_resp = summary_resp

    def is_available(self) -> bool:
        return self._available

    def chat_json(self, system_prompt: str, user_prompt: str):
        if "帖子筛选助手" in system_prompt:
            return self._filter_resp
        if "继任信息分析助手" in system_prompt:
            return self._summary_resp
        return None


class TestLLMEnricher(unittest.TestCase):
    def test_rule_filter_accepts_job_succession(self):
        enricher = LLMEnricher(
            llm_client=_FakeClient(available=False),
            settings=_build_settings(llm_enabled=False),
            logger=_NullLogger(),
        )
        note = _note(
            title="找继任｜招聘接任同学，实习岗位在上海",
            detail="团队招聘，简历投递后安排面试。",
        )

        decision = enricher.classify_target(note, allow_llm=False)
        self.assertTrue(decision.is_target)
        self.assertGreaterEqual(decision.score, 0.62)

    def test_hard_negative_topic_is_rejected(self):
        enricher = LLMEnricher(
            llm_client=_FakeClient(
                available=True,
                filter_resp={"is_target": True, "relevance_score": 0.95, "reason": "contains 继任"},
            ),
            settings=_build_settings(llm_enabled=True),
            logger=_NullLogger(),
        )
        note = _note(
            title="军事继任观察：某国军队将领更替",
            detail="这是政治军事分析，不是招聘。",
        )

        decision = enricher.classify_target(note, allow_llm=True)
        self.assertFalse(decision.is_target)
        self.assertIn("非目标主题", decision.reason)

    def test_summary_keeps_standard_format(self):
        enricher = LLMEnricher(
            llm_client=_FakeClient(
                available=True,
                summary_resp={
                    "detail_summary": "岗位是运营实习交接，要求每周到岗 4 天。",
                    "poster_comment_update": "未见贴主补充评论。",
                    "risk_flags": "无明确风险",
                },
            ),
            settings=_build_settings(llm_enabled=True),
            logger=_NullLogger(),
        )
        note = _note(
            title="找继任｜运营实习接任",
            detail="base 上海，要求每周到岗 4 天。",
            comments="有人问是否支持远程。",
        )

        summary = build_summary(note)
        result = enricher.enrich_summary(note, summary)
        self.assertIn("【继任追踪】", result.summary)
        self.assertIn("正文信息（详细）：岗位是运营实习交接", result.summary)
        self.assertIn("贴主补充评论：未见贴主补充评论。", result.summary)
        self.assertNotIn("评论信息（详细）", result.summary)
        self.assertNotIn("置信度：", result.summary)
        self.assertIn("链接：https://www.xiaohongshu.com/explore/abc", result.summary)


if __name__ == "__main__":
    unittest.main()
