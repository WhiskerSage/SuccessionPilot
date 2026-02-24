from __future__ import annotations

import unittest

from auto_successor.succession import extract_apply_info, extract_arrival_info, extract_jd_full, extract_poster_comment_update


class TestSuccessionHelpers(unittest.TestCase):
    def test_extract_jd_full_when_keywords_exist(self):
        text = (
            "我们组找继任，base上海。岗位职责：负责内容运营与数据复盘；"
            "岗位要求：每周到岗4天，至少实习3个月。投递邮箱 test@example.com"
        )
        jd = extract_jd_full(text)
        self.assertIn("岗位职责", jd)
        self.assertIn("岗位要求", jd)

    def test_extract_apply_info_prefers_email(self):
        text = "请将简历发送到 abc.hr@company.com，标题格式学校-姓名-到岗时间"
        apply_info = extract_apply_info(text)
        self.assertIn("abc.hr@company.com", apply_info)

    def test_extract_arrival_info(self):
        text = "岗位急招，下周到岗，最晚3.15前到岗。"
        arrival = extract_arrival_info(text)
        self.assertTrue(("下周" in arrival) or ("3.15" in arrival) or ("到岗" in arrival))

    def test_extract_poster_comment_update(self):
        with_update = "作者回复：补充一下，最晚下周二到岗。"
        without_update = "大家都在问薪资和面试流程"
        self.assertIn("贴主有补充", extract_poster_comment_update(with_update, comment_count=2))
        self.assertIn("未识别到贴主补充", extract_poster_comment_update(without_update, comment_count=2))
        self.assertIn("未见贴主补充", extract_poster_comment_update("", comment_count=0))


if __name__ == "__main__":
    unittest.main()
