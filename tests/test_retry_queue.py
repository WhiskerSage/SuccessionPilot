from __future__ import annotations

from pathlib import Path

from auto_successor.retry_queue import RetryQueue


def test_retry_queue_enqueue_and_success(tmp_path: Path) -> None:
    queue = RetryQueue(path=str(tmp_path / "retry.json"))
    item = queue.enqueue(queue_type="fetch", action="search_notes", payload={"keyword": "继任"}, run_id="r1", error="")
    assert item["queue_type"] == "fetch"
    due = queue.pop_due(limit=5)
    assert len(due) == 1
    queue.mark_success(due[0]["id"], result="ok")
    snap = queue.snapshot()
    assert snap["pending"]["fetch"] == 0
    assert snap["stats"]["succeeded"] >= 1


def test_retry_queue_retry_then_drop(tmp_path: Path) -> None:
    queue = RetryQueue(
        path=str(tmp_path / "retry.json"),
        base_backoff_seconds=1,
        max_backoff_seconds=3,
        max_attempts_by_type={"email": 2},
    )
    item = queue.enqueue(queue_type="email", action="dispatch_digest", payload={"subject": "s", "body": "b"}, run_id="r2", error="")
    due = queue.pop_due(limit=1)
    assert len(due) == 1
    queue.mark_retry(due[0]["id"], error="smtp timeout")
    queue.mark_retry(due[0]["id"], error="smtp timeout again")
    snap = queue.snapshot()
    assert snap["stats"]["retried"] >= 1
    assert snap["stats"]["dropped"] >= 1


def test_retry_queue_dedupe_key(tmp_path: Path) -> None:
    queue = RetryQueue(path=str(tmp_path / "retry.json"))
    first = queue.enqueue(
        queue_type="llm_timeout",
        action="probe",
        payload={"error_code": "read_timeout"},
        run_id="r3",
        error="timeout",
        dedupe_key="llm:r3:read_timeout",
    )
    second = queue.enqueue(
        queue_type="llm_timeout",
        action="probe",
        payload={"error_code": "read_timeout"},
        run_id="r3",
        error="timeout",
        dedupe_key="llm:r3:read_timeout",
    )
    assert first["id"] == second["id"]
