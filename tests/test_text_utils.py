from __future__ import annotations

import unittest

from auto_successor.text_utils import clean_line, repair_mojibake


class TestTextUtils(unittest.TestCase):
    def test_clean_line_keeps_normal_chinese(self):
        src = "急招：美团找继任"
        self.assertEqual(clean_line(src), src)

    def test_repair_mojibake_keeps_normal_chinese(self):
        src = "北京"
        self.assertEqual(repair_mojibake(src), src)


if __name__ == "__main__":
    unittest.main()
