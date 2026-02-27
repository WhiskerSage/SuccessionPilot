from __future__ import annotations

import json
import os
import time
from pathlib import Path


class RunLock:
    """Simple lock-file to avoid overlapping runs in daemon mode."""

    def __init__(self, lock_file: str = "data/.run.lock", stale_seconds: int = 1800) -> None:
        self.path = Path(lock_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stale_seconds = max(60, int(stale_seconds or 1800))

    def acquire(self) -> bool:
        if self.path.exists():
            if self._should_break_existing_lock():
                self.path.unlink(missing_ok=True)
            else:
                return False
        payload = {
            "pid": os.getpid(),
            "created_at": int(time.time()),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return True

    def release(self) -> None:
        if self.path.exists():
            self.path.unlink(missing_ok=True)

    def _should_break_existing_lock(self) -> bool:
        payload = self._read_payload()
        now = time.time()
        try:
            modified_at = float(self.path.stat().st_mtime)
        except Exception:
            modified_at = now

        if payload:
            pid = payload.get("pid")
            created_at = payload.get("created_at", modified_at)
            try:
                created_at = float(created_at)
            except Exception:
                created_at = modified_at

            if isinstance(pid, int) and pid > 0:
                if self._pid_exists(pid):
                    return False
                return True
            return max(0.0, now - created_at) >= self.stale_seconds

        # Legacy lock format (plain text "locked"): no pid info.
        # Avoid blocking forever after abrupt termination.
        legacy_grace = max(120, self.stale_seconds // 6)
        return max(0.0, now - modified_at) >= legacy_grace

    def _read_payload(self) -> dict:
        try:
            text = self.path.read_text(encoding="utf-8").strip()
        except Exception:
            return {}
        if not text:
            return {}
        try:
            value = json.loads(text)
        except Exception:
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            # Process exists but current user may not have full permission.
            return True
        except OSError:
            return False
