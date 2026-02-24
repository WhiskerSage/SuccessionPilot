from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class StageRecord:
    name: str
    status: str
    started_at: str
    ended_at: str
    duration_ms: int
    meta: dict = field(default_factory=dict)
    error: str = ""


class RuntimeOrchestrator:
    """
    Lightweight nanoclaw-style stage orchestrator.
    Keeps a stage audit trail so each run can be inspected and replayed.
    """

    def __init__(self, runtime_name: str, logger) -> None:
        self.runtime_name = runtime_name
        self.logger = logger
        self._stages: list[StageRecord] = []

    def run_stage(self, name: str, fn: Callable[[], T], meta: dict | None = None) -> T:
        started = datetime.now(timezone.utc).isoformat()
        started_perf = perf_counter()
        meta = meta or {}
        try:
            result = fn()
            duration_ms = int((perf_counter() - started_perf) * 1000)
            ended = datetime.now(timezone.utc).isoformat()
            self._stages.append(
                StageRecord(
                    name=name,
                    status="success",
                    started_at=started,
                    ended_at=ended,
                    duration_ms=duration_ms,
                    meta=meta,
                )
            )
            return result
        except Exception as exc:
            duration_ms = int((perf_counter() - started_perf) * 1000)
            ended = datetime.now(timezone.utc).isoformat()
            self._stages.append(
                StageRecord(
                    name=name,
                    status="failed",
                    started_at=started,
                    ended_at=ended,
                    duration_ms=duration_ms,
                    meta=meta,
                    error=str(exc),
                )
            )
            raise

    def stage_records(self) -> list[dict]:
        return [
            {
                "name": stage.name,
                "status": stage.status,
                "started_at": stage.started_at,
                "ended_at": stage.ended_at,
                "duration_ms": stage.duration_ms,
                "meta": stage.meta,
                "error": stage.error,
            }
            for stage in self._stages
        ]
