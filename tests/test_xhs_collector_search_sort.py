from __future__ import annotations

import unittest
from datetime import datetime

from auto_successor.config import XHSConfig
from auto_successor.xhs_collector import XHSMcpCliCollector


class _NullLogger:
    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def exception(self, *args, **kwargs):
        return None


class _FakeCollector(XHSMcpCliCollector):
    def _run_search_payload(self, keyword: str, max_results: int) -> dict:
        return {
            "success": True,
            "feeds": [
                {
                    "id": "note-1",
                    "model_type": "note",
                    "xsec_token": "tok-1",
                    "note_card": {
                        "display_title": "上海找继任",
                        "user": {"nick_name": "tester"},
                        "interact_info": {
                            "liked_count": "12",
                            "comment_count": "5",
                            "shared_count": "3",
                        },
                        "corner_tag_info": [{"type": "publish_time", "text": "1天前"}],
                    },
                },
                {"id": "q1", "model_type": "hot_query"},
            ],
        }


class _FallbackCollector(XHSMcpCliCollector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fallback_called = 0

    def _run_search_script(self, keyword: str, sort: str, max_results: int) -> dict:
        return {
            "success": False,
            "sort": sort,
            "response": {"success": False, "code": 300011, "msg": "risk_control"},
        }

    def _run_json(self, tail_args: list[str]) -> dict:
        self.fallback_called += 1
        return {
            "success": True,
            "feeds": [
                {
                    "id": "note-fallback",
                    "modelType": "note",
                    "xsecToken": "tok-fallback",
                    "noteCard": {
                        "displayTitle": "fallback title",
                        "user": {"nickName": "fallback-author"},
                        "interactInfo": {"likedCount": 1, "commentCount": 2, "sharedCount": 0},
                        "cornerTagInfo": [{"type": "publish_time", "text": "1天前"}],
                    },
                }
            ],
        }


class _FallbackExceptionCollector(_FallbackCollector):
    def _run_search_script(self, keyword: str, sort: str, max_results: int) -> dict:
        raise RuntimeError("script_broken")


class TestXHSCollectorSearchSort(unittest.TestCase):
    def test_parse_snake_case_feed_payload(self):
        collector = _FakeCollector(
            cfg=XHSConfig(search_sort="time_descending"),
            timezone="Asia/Shanghai",
            logger=_NullLogger(),
        )

        notes = collector.search_notes(run_id="r1", keyword="继任", max_results=20)
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(note.note_id, "note-1")
        self.assertEqual(note.title, "上海找继任")
        self.assertEqual(note.author, "tester")
        self.assertEqual(note.like_count, 12)
        self.assertEqual(note.comment_count, 5)
        self.assertEqual(note.share_count, 3)
        self.assertIn("xsec_token=tok-1", note.url)

    def test_fallback_to_general_search_when_explicit_sort_payload_fails(self):
        collector = _FallbackCollector(
            cfg=XHSConfig(search_sort="time_descending"),
            timezone="Asia/Shanghai",
            logger=_NullLogger(),
        )
        notes = collector.search_notes(run_id="r2", keyword="继任", max_results=20)
        self.assertEqual(collector.fallback_called, 1)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].note_id, "note-fallback")

    def test_fallback_to_general_search_when_explicit_sort_script_raises(self):
        collector = _FallbackExceptionCollector(
            cfg=XHSConfig(search_sort="time_descending"),
            timezone="Asia/Shanghai",
            logger=_NullLogger(),
        )
        notes = collector.search_notes(run_id="r3", keyword="继任", max_results=20)
        self.assertEqual(collector.fallback_called, 1)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].note_id, "note-fallback")

    def test_publish_time_parser_supports_relative_and_absolute_formats(self):
        collector = _FakeCollector(
            cfg=XHSConfig(search_sort="time_descending"),
            timezone="Asia/Shanghai",
            logger=_NullLogger(),
        )
        base = datetime(2026, 2, 26, 15, 30, tzinfo=collector.tz)

        dt1, q1 = collector._parse_publish_time_with_quality("昨天 09:15", reference=base)
        self.assertEqual(q1, "parsed")
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 2)
        self.assertEqual(dt1.day, 25)
        self.assertEqual(dt1.hour, 9)
        self.assertEqual(dt1.minute, 15)

        dt2, q2 = collector._parse_publish_time_with_quality("发布于 2026-02-23 20:01", reference=base)
        self.assertEqual(q2, "parsed")
        self.assertEqual(dt2.year, 2026)
        self.assertEqual(dt2.month, 2)
        self.assertEqual(dt2.day, 23)
        self.assertEqual(dt2.hour, 20)
        self.assertEqual(dt2.minute, 1)

        dt3, q3 = collector._parse_publish_time_with_quality("2月24日 08:40", reference=base)
        self.assertEqual(q3, "parsed")
        self.assertEqual(dt3.year, 2026)
        self.assertEqual(dt3.month, 2)
        self.assertEqual(dt3.day, 24)
        self.assertEqual(dt3.hour, 8)
        self.assertEqual(dt3.minute, 40)

        dt4, q4 = collector._parse_publish_time_with_quality("未知时间格式", reference=base)
        self.assertEqual(q4, "fallback")
        self.assertEqual(dt4, base)


if __name__ == "__main__":
    unittest.main()
