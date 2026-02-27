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
    DEAD_LETTER_STATUS = "dead_letter"

    def __init__(
        self,
        path: str,
        *,
        base_backoff_seconds: int = 20,
        max_backoff_seconds: int = 1200,
        running_ttl_seconds: int = 300,
        max_attempts_by_type: dict[str, int] | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.base_backoff_seconds = max(1, int(base_backoff_seconds))
        self.max_backoff_seconds = max(self.base_backoff_seconds, int(max_backoff_seconds))
        self.running_ttl_seconds = max(30, int(running_ttl_seconds))
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
        self._dead_letters: list[dict[str, Any]] = []
        self._idempotency_done: dict[str, dict[str, str]] = {}
        self._stats: dict[str, int] = {
            "enqueued": 0,
            "retried": 0,
            "succeeded": 0,
            "dropped": 0,
            "dead_lettered": 0,
            "dequeued": 0,
            "processing_success": 0,
            "processing_failed": 0,
            "total_duration_ms": 0,
            "max_duration_ms": 0,
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
        idempotency_key: str = "",
    ) -> dict[str, Any]:
        qtype = str(queue_type or "").strip().lower()
        if qtype not in self.QUEUE_TYPES:
            raise ValueError(f"unsupported queue type: {queue_type}")

        now = _utc_now()
        with self._lock:
            idem = self._normalize_idempotency_key(qtype=qtype, key=idempotency_key)
            if idem and idem in self._idempotency_done:
                existing_id = str(self._idempotency_done.get(idem, {}).get("item_id") or "")
                existing = self._find_item_unlocked(existing_id) if existing_id else None
                if existing is not None:
                    existing["updated_at"] = _iso(now)
                    self._save_unlocked()
                    return deepcopy(existing)

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
                "lease_until": "",
                "last_error": str(error or "").strip()[:800],
                "last_error_code": "",
                "last_result": "",
                "last_duration_ms": 0,
                "last_trace_id": "",
                "dedupe_key": dedupe,
                "idempotency_key": idem,
            }
            self._items.append(item)
            self._stats["enqueued"] = int(self._stats.get("enqueued", 0)) + 1
            self._save_unlocked()
            return deepcopy(item)

    def pop_due(self, limit: int) -> list[dict[str, Any]]:
        size = max(1, int(limit))
        now = _utc_now()
        with self._lock:
            # Recover stale running tasks back to pending.
            for item in self._items:
                if str(item.get("status") or "").strip().lower() != "running":
                    continue
                lease_until = _parse_iso(item.get("lease_until"))
                if lease_until is None or lease_until <= now:
                    item["status"] = "pending"
                    item["updated_at"] = _iso(now)
                    item["lease_until"] = ""

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
                item["lease_until"] = _iso(now + timedelta(seconds=self.running_ttl_seconds))
            if picked:
                self._stats["dequeued"] = int(self._stats.get("dequeued", 0)) + len(picked)
            if picked:
                self._save_unlocked()
            return [deepcopy(item) for item in picked]

    def mark_success(
        self,
        item_id: str,
        *,
        result: str = "",
        duration_ms: int = 0,
        trace_id: str = "",
    ) -> None:
        now = _utc_now()
        with self._lock:
            item = self._find_item_unlocked(item_id)
            if item is None:
                return
            item["status"] = "done"
            item["updated_at"] = _iso(now)
            item["last_result"] = str(result or "").strip()[:800]
            item["lease_until"] = ""
            item["last_trace_id"] = str(trace_id or "").strip()[:80]
            item["last_duration_ms"] = max(0, int(duration_ms or 0))
            self._stats["succeeded"] = int(self._stats.get("succeeded", 0)) + 1
            self._stats["processing_success"] = int(self._stats.get("processing_success", 0)) + 1
            self._merge_duration_unlocked(item["last_duration_ms"])
            idem = str(item.get("idempotency_key") or "").strip()
            if idem:
                self._idempotency_done[idem] = {
                    "item_id": str(item.get("id") or ""),
                    "updated_at": _iso(now),
                }
            self._save_unlocked()

    def mark_retry(
        self,
        item_id: str,
        *,
        error: str = "",
        duration_ms: int = 0,
        trace_id: str = "",
        error_code: str = "",
    ) -> None:
        now = _utc_now()
        with self._lock:
            item = self._find_item_unlocked(item_id)
            if item is None:
                return

            attempt = int(item.get("attempt", 0)) + 1
            item["attempt"] = attempt
            item["updated_at"] = _iso(now)
            item["last_error"] = str(error or "").strip()[:800]
            item["last_error_code"] = str(error_code or "").strip().lower()[:80]
            item["last_trace_id"] = str(trace_id or "").strip()[:80]
            item["last_duration_ms"] = max(0, int(duration_ms or 0))
            item["lease_until"] = ""
            self._stats["processing_failed"] = int(self._stats.get("processing_failed", 0)) + 1
            self._merge_duration_unlocked(item["last_duration_ms"])

            max_attempts = max(1, int(item.get("max_attempts", 3)))
            if attempt >= max_attempts:
                item["status"] = self.DEAD_LETTER_STATUS
                item["next_run_at"] = ""
                self._append_dead_letter_unlocked(item=item, reason=item["last_error"])
                self._stats["dropped"] = int(self._stats.get("dropped", 0)) + 1
                self._stats["dead_lettered"] = int(self._stats.get("dead_lettered", 0)) + 1
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
            dead_letter = {"fetch": 0, "llm_timeout": 0, "email": 0}
            for item in self._items:
                qtype = str(item.get("queue_type") or "")
                if qtype not in pending:
                    continue
                status = str(item.get("status") or "")
                if status == "pending":
                    pending[qtype] += 1
                elif status == "running":
                    running[qtype] += 1
                elif status == self.DEAD_LETTER_STATUS:
                    dead_letter[qtype] += 1
            return {
                "pending": pending,
                "running": running,
                "dead_letter": dead_letter,
                "stats": dict(self._stats),
                "total_items": len(self._items),
                "dead_letters_total": len(self._dead_letters),
                "idempotency_total": len(self._idempotency_done),
            }

    def list_items(
        self,
        *,
        status: str = "all",
        queue_type: str = "all",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        status_filter = str(status or "all").strip().lower() or "all"
        type_filter = str(queue_type or "all").strip().lower() or "all"
        size = max(1, int(limit))
        with self._lock:
            rows = []
            for item in self._items:
                qtype = str(item.get("queue_type") or "").strip().lower()
                s = str(item.get("status") or "").strip().lower()
                if type_filter != "all" and qtype != type_filter:
                    continue
                if status_filter != "all" and s != status_filter:
                    continue
                rows.append(deepcopy(item))

            rows.sort(
                key=lambda x: (
                    _parse_iso(x.get("updated_at")) or _utc_now(),
                    _parse_iso(x.get("created_at")) or _utc_now(),
                ),
                reverse=True,
            )
            return rows[:size]

    def list_dead_letters(self, *, queue_type: str = "all", limit: int = 120) -> list[dict[str, Any]]:
        type_filter = str(queue_type or "all").strip().lower() or "all"
        size = max(1, int(limit))
        with self._lock:
            rows = []
            for item in self._dead_letters:
                qtype = str(item.get("queue_type") or "").strip().lower()
                if type_filter != "all" and qtype != type_filter:
                    continue
                rows.append(deepcopy(item))
            rows.sort(
                key=lambda x: (
                    _parse_iso(x.get("dead_lettered_at")) or _utc_now(),
                    _parse_iso(x.get("updated_at")) or _utc_now(),
                ),
                reverse=True,
            )
            return rows[:size]

    def has_completed_idempotency(self, *, queue_type: str, idempotency_key: str) -> bool:
        qtype = str(queue_type or "").strip().lower()
        key = self._normalize_idempotency_key(qtype=qtype, key=idempotency_key)
        if not key:
            return False
        with self._lock:
            return key in self._idempotency_done

    def requeue(self, item_id: str) -> dict[str, Any] | None:
        now = _utc_now()
        with self._lock:
            item = self._find_item_unlocked(item_id)
            if item is None:
                return None
            if str(item.get("status") or "").strip().lower() == "running":
                return None
            item["status"] = "pending"
            item["attempt"] = 0
            item["next_run_at"] = _iso(now)
            item["updated_at"] = _iso(now)
            item["lease_until"] = ""
            self._save_unlocked()
            return deepcopy(item)

    def kick(self, item_id: str) -> dict[str, Any] | None:
        now = _utc_now()
        with self._lock:
            item = self._find_item_unlocked(item_id)
            if item is None:
                return None
            status = str(item.get("status") or "").strip().lower()
            if status == "running":
                return None
            # Bring it forward without resetting attempt counters.
            item["status"] = "pending"
            item["next_run_at"] = _iso(now)
            item["updated_at"] = _iso(now)
            item["lease_until"] = ""
            self._save_unlocked()
            return deepcopy(item)

    def drop(self, item_id: str, *, reason: str = "") -> dict[str, Any] | None:
        now = _utc_now()
        with self._lock:
            item = self._find_item_unlocked(item_id)
            if item is None:
                return None
            previous = str(item.get("status") or "").strip().lower()
            item["status"] = "dropped"
            item["next_run_at"] = ""
            item["lease_until"] = ""
            item["updated_at"] = _iso(now)
            if reason:
                item["last_error"] = str(reason)[:800]
            self._append_dead_letter_unlocked(item=item, reason=str(reason or "dropped_by_user").strip())
            if previous != "dropped":
                self._stats["dropped"] = int(self._stats.get("dropped", 0)) + 1
            self._save_unlocked()
            return deepcopy(item)

    @staticmethod
    def _normalize_idempotency_key(*, qtype: str, key: str) -> str:
        raw = str(key or "").strip()
        if not raw:
            return ""
        return f"{qtype}:{raw}" if ":" not in raw else raw

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
                    "lease_until": str(item.get("lease_until") or ""),
                    "last_error": str(item.get("last_error") or ""),
                    "last_error_code": str(item.get("last_error_code") or ""),
                    "last_result": str(item.get("last_result") or ""),
                    "last_duration_ms": max(0, int(item.get("last_duration_ms") or 0)),
                    "last_trace_id": str(item.get("last_trace_id") or ""),
                    "dedupe_key": str(item.get("dedupe_key") or ""),
                    "idempotency_key": str(item.get("idempotency_key") or ""),
                }
                safe_items.append(row)
            self._items = safe_items

        dead_letters = payload.get("dead_letters")
        if isinstance(dead_letters, list):
            safe_dead: list[dict[str, Any]] = []
            for item in dead_letters:
                if not isinstance(item, dict):
                    continue
                qtype = str(item.get("queue_type") or "").strip().lower()
                if qtype not in self.QUEUE_TYPES:
                    continue
                safe_dead.append(
                    {
                        "id": str(item.get("id") or uuid.uuid4().hex[:16]),
                        "queue_type": qtype,
                        "action": str(item.get("action") or "unknown"),
                        "run_id": str(item.get("run_id") or ""),
                        "attempt": max(0, int(item.get("attempt") or 0)),
                        "max_attempts": max(1, int(item.get("max_attempts") or self.max_attempts_by_type.get(qtype, 3))),
                        "dead_lettered_at": str(item.get("dead_lettered_at") or _iso(_utc_now())),
                        "created_at": str(item.get("created_at") or _iso(_utc_now())),
                        "updated_at": str(item.get("updated_at") or _iso(_utc_now())),
                        "reason": str(item.get("reason") or ""),
                        "error_code": str(item.get("error_code") or ""),
                        "dedupe_key": str(item.get("dedupe_key") or ""),
                        "idempotency_key": str(item.get("idempotency_key") or ""),
                    }
                )
            self._dead_letters = safe_dead

        idempotency_done = payload.get("idempotency_done")
        if isinstance(idempotency_done, dict):
            safe_done: dict[str, dict[str, str]] = {}
            for key, value in idempotency_done.items():
                idem_key = str(key or "").strip()
                if not idem_key:
                    continue
                if not isinstance(value, dict):
                    continue
                safe_done[idem_key] = {
                    "item_id": str(value.get("item_id") or ""),
                    "updated_at": str(value.get("updated_at") or _iso(_utc_now())),
                }
            self._idempotency_done = safe_done

        stats = payload.get("stats")
        if isinstance(stats, dict):
            merged = dict(self._stats)
            for key in merged.keys():
                merged[key] = max(0, int(stats.get(key) or 0))
            self._stats = merged

    def _merge_duration_unlocked(self, duration_ms: int) -> None:
        value = max(0, int(duration_ms or 0))
        self._stats["total_duration_ms"] = int(self._stats.get("total_duration_ms", 0)) + value
        self._stats["max_duration_ms"] = max(
            int(self._stats.get("max_duration_ms", 0)),
            value,
        )

    def _append_dead_letter_unlocked(self, *, item: dict[str, Any], reason: str) -> None:
        self._dead_letters.append(
            {
                "id": str(item.get("id") or ""),
                "queue_type": str(item.get("queue_type") or ""),
                "action": str(item.get("action") or ""),
                "run_id": str(item.get("run_id") or ""),
                "attempt": max(0, int(item.get("attempt") or 0)),
                "max_attempts": max(1, int(item.get("max_attempts") or 1)),
                "dead_lettered_at": _iso(_utc_now()),
                "created_at": str(item.get("created_at") or ""),
                "updated_at": str(item.get("updated_at") or ""),
                "reason": str(reason or item.get("last_error") or "")[:800],
                "error_code": str(item.get("last_error_code") or "")[:80],
                "dedupe_key": str(item.get("dedupe_key") or ""),
                "idempotency_key": str(item.get("idempotency_key") or ""),
            }
        )

    def _save_unlocked(self) -> None:
        payload = {
            "updated_at": _iso(_utc_now()),
            "items": self._items,
            "dead_letters": self._dead_letters,
            "idempotency_done": self._idempotency_done,
            "stats": self._stats,
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
