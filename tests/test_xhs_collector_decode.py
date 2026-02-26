from __future__ import annotations

import json
import unittest

from auto_successor.xhs_collector import XHSMcpCliCollector


class TestXHSCollectorDecode(unittest.TestCase):
    def test_decode_json_output_utf8(self):
        payload = {"success": True, "message": "北京"}
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        text = XHSMcpCliCollector._decode_json_output(raw)
        self.assertEqual(json.loads(text)["message"], "北京")

    def test_decode_json_output_gb18030(self):
        payload = {"success": True, "message": "上海"}
        raw = json.dumps(payload, ensure_ascii=False).encode("gb18030")
        text = XHSMcpCliCollector._decode_json_output(raw)
        self.assertEqual(json.loads(text)["message"], "上海")


if __name__ == "__main__":
    unittest.main()

