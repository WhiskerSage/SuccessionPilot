from __future__ import annotations

import argparse
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


def main() -> None:
    args = parse_args()
    workspace = Path.cwd()
    engine = (args.engine or "auto").strip().lower()

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
