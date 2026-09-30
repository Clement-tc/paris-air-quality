"""
Automated data refresh scheduler.

Runs as a standalone process alongside the FastAPI server.
POSTs to /admin/refresh on a configurable interval (default: every hour).

Usage:
    python scheduler.py              # refresh every 60 min
    python scheduler.py --interval 30   # every 30 min
    python scheduler.py --once          # single run then exit
"""
import argparse
import logging
import sys
import time
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/scheduler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("scheduler")

API_BASE = "http://localhost:8000"


def refresh() -> None:
    log.info("Triggering data refresh…")
    try:
        r = httpx.post(f"{API_BASE}/admin/refresh", timeout=120)
        r.raise_for_status()
        data = r.json()
        stats = data.get("stats", {})
        log.info(
            "Refresh complete — fetched=%s stored=%s skipped=%s errors=%s",
            stats.get("fetched", "?"),
            stats.get("stored", "?"),
            stats.get("skipped_quality", "?"),
            stats.get("errors", "?"),
        )
    except httpx.HTTPStatusError as e:
        log.error("API returned %s: %s", e.response.status_code, e.response.text[:300])
    except httpx.RequestError as e:
        log.error("Could not reach API: %s", e)


def main() -> None:
    parser = argparse.ArgumentParser(description="Paris AQ refresh scheduler")
    parser.add_argument(
        "--interval", type=int, default=60, metavar="MIN",
        help="Refresh interval in minutes (default: 60)",
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run one refresh immediately then exit",
    )
    args = parser.parse_args()

    if args.once:
        refresh()
        return

    log.info("Scheduler starting — refresh every %d min", args.interval)
    refresh()  # run immediately on startup

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        refresh,
        trigger=IntervalTrigger(minutes=args.interval),
        id="air_refresh",
        name="Paris AQ refresh",
        misfire_grace_time=120,
    )
    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
