from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from auto_successor.dashboard import _dashboard_lock_path, dashboard_instance_lock


class TestDashboardSingleInstance(unittest.TestCase):
    def test_blocks_second_instance_on_same_host_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            with dashboard_instance_lock(workspace=workspace, host="127.0.0.1", port=8787):
                with self.assertRaises(RuntimeError):
                    with dashboard_instance_lock(workspace=workspace, host="127.0.0.1", port=8787):
                        pass

    def test_recovers_stale_lock_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            lock_path = _dashboard_lock_path(workspace=workspace, host="127.0.0.1", port=8787)
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                '{"pid": 99999999, "host": "127.0.0.1", "port": 8787, "started_at": "stale"}',
                encoding="utf-8",
            )

            with dashboard_instance_lock(workspace=workspace, host="127.0.0.1", port=8787):
                self.assertTrue(lock_path.exists())

            self.assertFalse(lock_path.exists())


if __name__ == "__main__":
    unittest.main()

