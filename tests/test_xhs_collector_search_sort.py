from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
