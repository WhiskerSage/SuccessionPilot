from __future__ import annotations

import unittest

from auto_successor.xhs_collector import XHSMcpCliCollector


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


if __name__ == "__main__":
    unittest.main()
