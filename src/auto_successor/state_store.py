from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class StateStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.processed_note_ids: set[str] = set()
        self.last_digest_sent_at: str = ""
        self.last_digest_run_id: str = ""
        self.alert_last_sent_at: dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            ids = data.get("processed_note_ids", [])
            if isinstance(ids, list):
                self.processed_note_ids = {str(x) for x in ids if x}
            self.last_digest_sent_at = str(data.get("last_digest_sent_at") or "").strip()
            self.last_digest_run_id = str(data.get("last_digest_run_id") or "").strip()
            raw_alert_times = data.get("alert_last_sent_at")
            if isinstance(raw_alert_times, dict):
                self.alert_last_sent_at = {
                    str(k).strip(): str(v).strip()
                    for k, v in raw_alert_times.items()
                    if str(k).strip() and str(v).strip()
                }
            else:
                self.alert_last_sent_at = {}
        except Exception:
            self.processed_note_ids = set()
            self.last_digest_sent_at = ""
            self.last_digest_run_id = ""
            self.alert_last_sent_at = {}

    def save(self) -> None:
        payload = {
            "processed_note_ids": sorted(self.processed_note_ids),
            "last_digest_sent_at": self.last_digest_sent_at,
            "last_digest_run_id": self.last_digest_run_id,
            "alert_last_sent_at": self.alert_last_sent_at,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def has(self, note_id: str) -> bool:
        return note_id in self.processed_note_ids

    def mark(self, note_id: str) -> None:
        self.processed_note_ids.add(note_id)

    def get_last_digest_time(self) -> datetime | None:
        raw = (self.last_digest_sent_at or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def is_digest_due(self, now: datetime, interval_minutes: int) -> bool:
        last = self.get_last_digest_time()
        if last is None:
            return True
        delta_seconds = (now - last).total_seconds()
        return delta_seconds >= max(1, int(interval_minutes)) * 60

    def mark_digest_sent(self, sent_at: datetime, run_id: str) -> None:
        self.last_digest_sent_at = sent_at.astimezone(timezone.utc).isoformat()
        self.last_digest_run_id = run_id

    def get_alert_last_sent_time(self, alert_code: str) -> datetime | None:
        key = str(alert_code or "").strip().lower()
        if not key:
            return None
        raw = str(self.alert_last_sent_at.get(key) or "").strip()
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def is_alert_due(self, alert_code: str, now: datetime, cooldown_minutes: int) -> bool:
        last = self.get_alert_last_sent_time(alert_code)
        if last is None:
            return True
        delta_seconds = (now - last).total_seconds()
        return delta_seconds >= max(1, int(cooldown_minutes)) * 60

    def mark_alert_sent(self, alert_code: str, sent_at: datetime) -> None:
        key = str(alert_code or "").strip().lower()
        if not key:
            return
        self.alert_last_sent_at[key] = sent_at.astimezone(timezone.utc).isoformat()
