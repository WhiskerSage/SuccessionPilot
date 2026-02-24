from __future__ import annotations

from pathlib import Path


class RunLock:
    """Simple lock-file to avoid overlapping runs in daemon mode."""

    def __init__(self, lock_file: str = "data/.run.lock") -> None:
        self.path = Path(lock_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def acquire(self) -> bool:
        if self.path.exists():
            return False
        self.path.write_text("locked", encoding="utf-8")
        return True

    def release(self) -> None:
        if self.path.exists():
            self.path.unlink(missing_ok=True)

