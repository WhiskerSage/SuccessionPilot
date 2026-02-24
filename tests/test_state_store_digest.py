from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from auto_successor.state_store import StateStore


class TestStateStoreDigest(unittest.TestCase):
    def test_state_store_loads_legacy_format_and_marks_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"processed_note_ids": ["a", "b"]}), encoding="utf-8")

            store = StateStore(str(path))
            self.assertEqual(store.processed_note_ids, {"a", "b"})
            self.assertEqual(store.last_digest_sent_at, "")
            self.assertIsNone(store.get_last_digest_time())

            now = datetime.now(timezone.utc)
            store.mark_digest_sent(now, run_id="run-1")
            store.save()

            loaded = StateStore(str(path))
            self.assertEqual(loaded.last_digest_run_id, "run-1")
            self.assertIsNotNone(loaded.get_last_digest_time())

    def test_digest_due_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = StateStore(str(path))

            now = datetime.now(timezone.utc)
            self.assertTrue(store.is_digest_due(now, interval_minutes=60))

            store.mark_digest_sent(now, "run-2")
            self.assertFalse(store.is_digest_due(now + timedelta(minutes=10), interval_minutes=60))
            self.assertTrue(store.is_digest_due(now + timedelta(minutes=61), interval_minutes=60))


if __name__ == "__main__":
    unittest.main()
