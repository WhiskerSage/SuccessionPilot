from __future__ import annotations

import argparse
import json
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .dashboard_fastapi_server import (
    import_error_message,
    is_fastapi_available,
    run_fastapi_dashboard,
)
from .dashboard_legacy_server import run_legacy_dashboard


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SuccessionPilot dashboard server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=8787, help="Bind port")
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "fastapi", "legacy"],
        help="Dashboard backend engine",
    )
    return parser.parse_args()


def _safe_int(value: object) -> int:
    try:
        return int(str(value or "").strip())
    except Exception:
        return 0


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _dashboard_lock_path(workspace: Path, host: str, port: int) -> Path:
    safe_host = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(host or "127.0.0.1"))
    return workspace / "data" / f".dashboard-{safe_host}-{int(port)}.lock"


def _read_lock_payload(lock_path: Path) -> dict[str, object]:
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


@contextmanager
def dashboard_instance_lock(workspace: Path, host: str, port: int):
    lock_path = _dashboard_lock_path(workspace=workspace, host=host, port=port)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "host": str(host),
        "port": int(port),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False))
            break
        except FileExistsError:
            existing = _read_lock_payload(lock_path)
            owner_pid = _safe_int(existing.get("pid"))
            if owner_pid and _is_pid_running(owner_pid):
                started_at = str(existing.get("started_at") or "-")
                raise RuntimeError(
                    f"Dashboard already running on http://{host}:{port} "
                    f"(pid={owner_pid}, started_at={started_at})."
                )
            try:
                lock_path.unlink()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise RuntimeError(f"Failed to clear stale dashboard lock: {lock_path} ({exc})") from exc

    try:
        yield
    finally:
        try:
            existing = _read_lock_payload(lock_path)
            owner_pid = _safe_int(existing.get("pid"))
            if owner_pid == 0 or owner_pid == os.getpid():
                lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass


def main() -> None:
    args = parse_args()
    workspace = Path.cwd()
    engine = (args.engine or "auto").strip().lower()

    with dashboard_instance_lock(workspace=workspace, host=args.host, port=args.port):
        if engine == "legacy":
            run_legacy_dashboard(host=args.host, port=args.port, workspace=workspace)
            return

        if engine == "fastapi":
            if not is_fastapi_available():
                raise RuntimeError(
                    "FastAPI backend unavailable. Install fastapi + uvicorn first.\n"
                    f"Import error: {import_error_message()}"
                )
            run_fastapi_dashboard(host=args.host, port=args.port, workspace=workspace)
            return

        # auto mode
        if is_fastapi_available():
            run_fastapi_dashboard(host=args.host, port=args.port, workspace=workspace)
            return

        print("FastAPI not available, fallback to legacy dashboard server.")
        run_legacy_dashboard(host=args.host, port=args.port, workspace=workspace)


if __name__ == "__main__":
    main()
