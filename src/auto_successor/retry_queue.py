from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except Exception:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class RetryQueue:
    QUEUE_TYPES = {"fetch", "llm_timeout", "email"}

    def __init__(
        self,
        path: str,
        *,
        base_backoff_seconds: int = 20,
        max_backoff_seconds: int = 1200,
        max_attempts_by_type: dict[str, int] | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.base_backoff_seconds = max(1, int(base_backoff_seconds))
        self.max_backoff_seconds = max(self.base_backoff_seconds, int(max_backoff_seconds))
        self.max_attempts_by_type = {
            "fetch": 3,
            "llm_timeout": 3,
            "email": 4,
        }
        if isinstance(max_attempts_by_type, dict):
            for key, value in max_attempts_by_type.items():
                q = str(key or "").strip().lower()
                if q in self.QUEUE_TYPES:
                    self.max_attempts_by_type[q] = max(1, int(value))
        self._lock = threading.Lock()
        self._items: list[dict[str, Any]] = []
        self._stats: dict[str, int] = {
            "enqueued": 0,
            "retried": 0,
            "succeeded": 0,
            "dropped": 0,
        }
        self._load()

    def enqueue(
        self,
        *,
        queue_type: str,
        action: str,
        payload: dict[str, Any] | None = None,
        run_id: str = "",
        error: str = "",
        max_attempts: int | None = None,
        dedupe_key: str = "",
    ) -> dict[str, Any]:
        qtype = str(queue_type or "").strip().lower()
        if qtype not in self.QUEUE_TYPES:
            raise ValueError(f"unsupported queue type: {queue_type}")

        now = _utc_now()
        with self._lock:
            dedupe = str(dedupe_key or "").strip()
            if dedupe:
                for item in self._items:
                    if item.get("status") != "pending":
                        continue
                    if str(item.get("queue_type") or "") != qtype:
                        continue
                    if str(item.get("dedupe_key") or "") != dedupe:
                        continue
                    item["updated_at"] = _iso(now)
                    if error:
                        item["last_error"] = str(error)[:800]
                    self._save_unlocked()
                    return deepcopy(item)

            attempts_limit = max_attempts
            if attempts_limit is None:
                attempts_limit = int(self.max_attempts_by_type.get(qtype, 3))
            attempts_limit = max(1, int(attempts_limit))

            created = _iso(now)
            item = {
                "id": uuid.uuid4().hex[:16],
                "queue_type": qtype,
                "action": str(action or "").strip() or "unknown",
                "payload": deepcopy(payload) if isinstance(payload, dict) else {},
                "run_id": str(run_id or "").strip(),
                "attempt": 0,
                "max_attempts": attempts_limit,
                "status": "pending",
                "created_at": created,
                "updated_at": created,
                "next_run_at": created,
                "last_error": str(error or "").strip()[:800],
                "last_result": "",
                "dedupe_key": dedupe,
            }
            self._items.append(item)
            self._stats["enqueued"] = int(self._stats.get("enqueued", 0)) + 1
            self._save_unlocked()
            return deepcopy(item)

    def pop_due(self, limit: int) -> list[dict[str, Any]]:
        size = max(1, int(limit))
        now = _utc_now()
        with self._lock:
            due: list[dict[str, Any]] = []
            for item in self._items:
                if item.get("status") != "pending":
                    continue
                next_run_at = _parse_iso(item.get("next_run_at"))
                if next_run_at is None or next_run_at <= now:
                    due.append(item)

            due.sort(
                key=lambda x: (
                    _parse_iso(x.get("next_run_at")) or now,
                    _parse_iso(x.get("created_at")) or now,
                )
            )
            picked = due[:size]
            for item in picked:
                item["status"] = "running"
                item["updated_at"] = _iso(now)
            if picked:
                self._save_unlocked()
            return [deepcopy(item) for item in picked]

    def mark_success(self, item_id: str, *, result: str = "") -> None:
        now = _utc_now()
        with self._lock:
            item = self._find_item_unlocked(item_id)
            if item is None:
                return
            item["status"] = "done"
            item["updated_at"] = _iso(now)
            item["last_result"] = str(result or "").strip()[:800]
            self._stats["succeeded"] = int(self._stats.get("succeeded", 0)) + 1
            self._save_unlocked()

    def mark_retry(self, item_id: str, *, error: str = "") -> None:
        now = _utc_now()
        with self._lock:
            item = self._find_item_unlocked(item_id)
            if item is None:
                return

            attempt = int(item.get("attempt", 0)) + 1
            item["attempt"] = attempt
            item["updated_at"] = _iso(now)
            item["last_error"] = str(error or "").strip()[:800]

            max_attempts = max(1, int(item.get("max_attempts", 3)))
            if attempt >= max_attempts:
                item["status"] = "dropped"
                item["next_run_at"] = ""
                self._stats["dropped"] = int(self._stats.get("dropped", 0)) + 1
                self._save_unlocked()
                return

            delay = min(self.max_backoff_seconds, self.base_backoff_seconds * (2 ** (attempt - 1)))
            item["status"] = "pending"
            item["next_run_at"] = _iso(now + timedelta(seconds=delay))
            self._stats["retried"] = int(self._stats.get("retried", 0)) + 1
            self._save_unlocked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            pending = {"fetch": 0, "llm_timeout": 0, "email": 0}
            running = {"fetch": 0, "llm_timeout": 0, "email": 0}
            for item in self._items:
                qtype = str(item.get("queue_type") or "")
                if qtype not in pending:
                    continue
                status = str(item.get("status") or "")
                if status == "pending":
                    pending[qtype] += 1
                elif status == "running":
                    running[qtype] += 1
            return {
                "pending": pending,
                "running": running,
                "stats": dict(self._stats),
                "total_items": len(self._items),
            }

    def _find_item_unlocked(self, item_id: str) -> dict[str, Any] | None:
        target = str(item_id or "").strip()
        if not target:
            return None
        for item in self._items:
            if str(item.get("id") or "") == target:
                return item
        return None

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not isinstance(payload, dict):
            return
        items = payload.get("items")
        if isinstance(items, list):
            safe_items: list[dict[str, Any]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                qtype = str(item.get("queue_type") or "").strip().lower()
                if qtype not in self.QUEUE_TYPES:
                    continue
                status = str(item.get("status") or "").strip().lower() or "pending"
                if status == "running":
                    status = "pending"
                row = {
                    "id": str(item.get("id") or uuid.uuid4().hex[:16]),
                    "queue_type": qtype,
                    "action": str(item.get("action") or "unknown"),
                    "payload": deepcopy(item.get("payload")) if isinstance(item.get("payload"), dict) else {},
                    "run_id": str(item.get("run_id") or ""),
                    "attempt": max(0, int(item.get("attempt") or 0)),
                    "max_attempts": max(
                        1,
                        int(item.get("max_attempts") or self.max_attempts_by_type.get(qtype, 3)),
                    ),
                    "status": status,
                    "created_at": str(item.get("created_at") or _iso(_utc_now())),
                    "updated_at": str(item.get("updated_at") or _iso(_utc_now())),
                    "next_run_at": str(item.get("next_run_at") or _iso(_utc_now())),
                    "last_error": str(item.get("last_error") or ""),
                    "last_result": str(item.get("last_result") or ""),
                    "dedupe_key": str(item.get("dedupe_key") or ""),
                }
                safe_items.append(row)
            self._items = safe_items

        stats = payload.get("stats")
        if isinstance(stats, dict):
            merged = dict(self._stats)
            for key in merged.keys():
                merged[key] = max(0, int(stats.get(key) or 0))
            self._stats = merged

    def _save_unlocked(self) -> None:
        payload = {
            "updated_at": _iso(_utc_now()),
            "items": self._items,
            "stats": self._stats,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

