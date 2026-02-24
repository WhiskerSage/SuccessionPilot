from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class RunJournal:
    """Simplified run snapshot inspired by nanoclaw task snapshots."""

    def __init__(self, base_dir: str = "data/runs") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, run_id: str, payload: dict[str, Any]) -> Path:
        target = self.base_dir / f"{run_id}.json"
        body = {"run_id": run_id, "recorded_at": datetime.utcnow().isoformat(), **payload}
        target.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

