from __future__ import annotations

import unittest
from datetime import datetime, timezone

from auto_successor.job_processor import normalize_job_record, to_job_record
from auto_successor.models import JobRecord, NoteRecord


class TestJobProcessor(unittest.TestCase):
    def test_normalize_job_record_fills_required_fields(self):
        job = JobRecord(
            run_id="r1",
            post_id="",
            company="",
            position="",
            location="",
            requirements="",
            link="invalid_link",
            publish_time=datetime.now(timezone.utc),
            source_title="",
            comment_count=0,
            comments_preview="",
        )

        normalized = normalize_job_record(job)
        self.assertEqual(normalized.company, "未知")
        self.assertEqual(normalized.position, "未知")
        self.assertEqual(normalized.location, "未知")
        self.assertEqual(normalized.requirements, "未提取到明确要求")
        self.assertTrue(normalized.link.startswith("https://www.xiaohongshu.com/explore/"))
        self.assertEqual(normalized.post_id, "unknown_post")

    def test_to_job_record_outputs_stable_format(self):
        note = NoteRecord(
            run_id="r1",
            keyword="继任",
            note_id="67abc",
            title="找继任｜产品实习岗位 base 上海",
            author="tester",
            publish_time=datetime.now(timezone.utc),
            publish_time_text="2026-02-23",
            like_count=10,
            comment_count=2,
            share_count=1,
            url="https://www.xiaohongshu.com/explore/67abc",
            raw_json="{}",
            detail_text="团队招实习，要求每周到岗 4 天；可连续 3 个月。",
            comments_preview="请问要投简历吗？",
        )
        job = to_job_record(note)

        self.assertEqual(job.post_id, "67abc")
        self.assertTrue(bool(job.company))
        self.assertTrue(bool(job.position))
        self.assertTrue(bool(job.location))
        self.assertTrue(bool(job.requirements))
        self.assertTrue(job.link.startswith("https://"))
        self.assertNotIn("\n", job.requirements)

    def test_normalize_company_and_location_noise(self):
        job = JobRecord(
            run_id="r2",
            post_id="n2",
            company="急招：美团找继任",
            position="运营实习生",
            location="鍖椾含路娴锋穩",
            requirements="每周 4 天",
            link="https://www.xiaohongshu.com/explore/n2",
            publish_time=datetime.now(timezone.utc),
            source_title="",
            comment_count=0,
            comments_preview="",
        )

        normalized = normalize_job_record(job)
        self.assertEqual(normalized.company, "美团")
        self.assertEqual(normalized.location, "北京")


if __name__ == "__main__":
    unittest.main()
