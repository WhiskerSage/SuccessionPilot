from __future__ import annotations

import argparse
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .config import load_settings
from .logging_setup import setup_logging
from .pipeline import AutoSuccessorPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SuccessionPilot runtime")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config yaml")
    parser.add_argument("--run-once", action="store_true", help="Run one cycle and exit")
    parser.add_argument("--daemon", action="store_true", help="Run in loop mode")
    parser.add_argument("--mode", choices=["auto", "agent", "smart"], default=None, help="Run mode: auto or agent")
    parser.add_argument("--interval-minutes", type=int, default=None, help="Override loop interval")
    parser.add_argument(
        "--send-latest",
        nargs="?",
        const=5,
        type=int,
        default=None,
        help="Send latest stored summaries immediately (default 5)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings(args.config)
    logger = setup_logging(settings.app.log_level)
    pipeline = AutoSuccessorPipeline(settings, logger)
    tz = ZoneInfo(settings.app.timezone)
    mode = (args.mode or settings.agent.mode or "auto").strip().lower()
    if mode == "smart":
        mode = "agent"
    if mode not in {"auto", "agent"}:
        mode = "auto"

    interval = args.interval_minutes or settings.app.interval_minutes

    if args.send_latest is not None:
        run_id = datetime.now(tz).strftime("%Y%m%d-%H%M%S")
        pipeline.send_latest_stored(run_id=run_id, limit=max(1, int(args.send_latest)))
        return

    run_loop = args.daemon or not args.run_once

    if not run_loop:
        run_id = datetime.now(tz).strftime("%Y%m%d-%H%M%S")
        pipeline.run_once(run_id=run_id, mode=mode)
        return

    logger.info("start daemon loop, interval=%s minutes, mode=%s", interval, mode)
    while True:
        run_id = datetime.now(tz).strftime("%Y%m%d-%H%M%S")
        try:
            pipeline.run_once(run_id=run_id, mode=mode)
        except Exception as exc:
            logger.exception("run failed: %s", exc)
        time.sleep(max(interval, 1) * 60)


if __name__ == "__main__":
    main()
