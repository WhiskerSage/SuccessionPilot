from __future__ import annotations

import unittest
from datetime import datetime, timezone

from auto_successor.config import XHSConfig
from auto_successor.models import NoteRecord
from auto_successor.xhs_collector import XHSMcpCliCollector


class _NullLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None


class _PosterCommentCollector(XHSMcpCliCollector):
    def _run_detail_script(self, script_path: str, feed_id: str, xsec_token: str) -> dict:
        return {
            "success": True,
            "detail_text": "岗位职责：数据支持，base 上海。",
            "poster_comments_preview": "作者回复：仍在招，可以先发简历。",
            "comments_preview": "普通评论：请问双休吗？ | 普通评论：支持远程吗？",
            "comment_count_text": "12",
        }


class TestXHSCollectorSanitize(unittest.TestCase):
    def test_sanitize_comments_removes_footer_noise(self):
        raw = (
            "© 2014-2024 | 行吟信息科技（上海）有限公司 | 地址：上海市黄浦区... | 电话：9501-3888 | "
            "请问这个岗位还在招吗？ | 创作服务 | 直播管理 | 我已投递，求捞！"
        )
        cleaned = XHSMcpCliCollector._sanitize_comments_preview(raw)
        self.assertIn("请问这个岗位还在招吗？", cleaned)
        self.assertIn("我已投递，求捞！", cleaned)
        self.assertNotIn("行吟信息科技", cleaned)
        self.assertNotIn("创作服务", cleaned)
        self.assertNotIn("电话：", cleaned)

    def test_enrich_prefers_poster_comments_preview(self):
        collector = _PosterCommentCollector(
            cfg=XHSConfig(),
            timezone="Asia/Shanghai",
            logger=_NullLogger(),
        )
        note = NoteRecord(
            run_id="r1",
            keyword="继任",
            note_id="n1",
            title="找继任",
            author="tester",
            publish_time=datetime.now(timezone.utc),
            publish_time_text="刚刚",
            like_count=0,
            comment_count=0,
            share_count=0,
            url="https://www.xiaohongshu.com/explore/n1",
            raw_json="{}",
            xsec_token="tok",
        )

        collector.enrich_note_details([note], max_notes=1)

        self.assertIn("作者回复", note.comments_preview)
        self.assertNotIn("普通评论", note.comments_preview)
        self.assertEqual(note.comment_count, 12)


if __name__ == "__main__":
    unittest.main()
