"""
Bulk historical backfill from the OpenAQ S3 data archive.

The live API (backend/openaq_client.py) only gives "latest" — no history.
For model training we need months of past readings, and paging through the
v3 API for that would be slow and rate-limited. OpenAQ instead publishes a
full historical archive on S3 (AWS Open Data, public/anonymous, one gzipped
CSV per station per day):

    s3://openaq-data-archive/records/csv.gz/locationid={id}/year={y}/month={m}/location-{id}-{yyyymmdd}.csv.gz

This script:
  1. Reads the Paris station ids from the existing SQLite DB (backend/paris_air.db)
     — same 28 stations the live pipeline already ingests.
  2. Lists and downloads every daily file in the given date range, in parallel
     (anonymous S3, no credentials needed).
  3. Concatenates into a single Parquet file, one row per (station, sensor, hour).

Usage:
    python backfill_openaq.py --days 365
    python backfill_openaq.py --start 2025-01-01 --end 2025-12-31
    python backfill_openaq.py --days 365 --workers 16
"""
import argparse
import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import boto3
import pandas as pd
from botocore import UNSIGNED
from botocore.config import Config

BUCKET = "openaq-data-archive"
BACKEND_DB = Path(__file__).parent.parent / "backend" / "paris_air.db"
OUT_DIR = Path(__file__).parent.parent / "data"

_s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))


def get_paris_location_ids() -> list[int]:
    """Reuse the stations the live pipeline already discovered and stored."""
    if not BACKEND_DB.exists():
        raise FileNotFoundError(
            f"{BACKEND_DB} not found. Run the backend at least once "
            "(POST /admin/refresh) so locations are populated."
        )
    conn = sqlite3.connect(BACKEND_DB)
    ids = [r[0] for r in conn.execute("SELECT id FROM locations ORDER BY id")]
    conn.close()
    return ids


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _key(location_id: int, day: date) -> str:
    return (
        f"records/csv.gz/locationid={location_id}/"
        f"year={day:%Y}/month={day:%m}/"
        f"location-{location_id}-{day:%Y%m%d}.csv.gz"
    )


def _fetch_one(location_id: int, day: date) -> pd.DataFrame | None:
    key = _key(location_id, day)
    try:
        obj = _s3.get_object(Bucket=BUCKET, Key=key)
        raw = obj["Body"].read()
    except _s3.exceptions.NoSuchKey:
        return None
    except Exception as e:  # noqa: BLE001 — one bad day/station shouldn't kill the run
        print(f"  ! {key} failed: {e}")
        return None

    df = pd.read_csv(io.BytesIO(raw), compression="gzip")
    if df.empty:
        return None
    return df


def backfill(start: date, end: date, workers: int) -> Path:
    location_ids = get_paris_location_ids()
    days = list(daterange(start, end))
    tasks = [(loc, d) for loc in location_ids for d in days]

    print(
        f"Backfilling {len(location_ids)} stations x {len(days)} days "
        f"= {len(tasks)} daily files ({start} -> {end})"
    )

    frames: list[pd.DataFrame] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch_one, loc, d): (loc, d) for loc, d in tasks}
        for fut in as_completed(futures):
            done += 1
            df = fut.result()
            if df is not None:
                frames.append(df)
            if done % 500 == 0 or done == len(tasks):
                print(f"  {done}/{len(tasks)} files checked, {len(frames)} non-empty")

    if not frames:
        raise RuntimeError("No data found for any station/day in range — check the DB has stations.")

    full = pd.concat(frames, ignore_index=True)
    full["datetime"] = pd.to_datetime(full["datetime"], utc=True)
    full = full.sort_values(["location_id", "sensors_id", "datetime"]).drop_duplicates(
        subset=["sensors_id", "datetime"]
    )

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"openaq_history_{start:%Y%m%d}_{end:%Y%m%d}.parquet"
    full.to_parquet(out_path, index=False)

    print(f"\nWrote {len(full):,} rows -> {out_path}")
    print(f"Stations covered: {full['location_id'].nunique()} / {len(location_ids)}")
    print(f"Date range in data: {full['datetime'].min()} -> {full['datetime'].max()}")
    print("Rows per parameter:")
    print(full["parameter"].value_counts().to_string())

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill OpenAQ history from S3 archive")
    parser.add_argument("--days", type=int, default=365, help="How many days back from --end (default 365)")
    parser.add_argument("--start", type=str, help="Start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--end", type=str, help="End date YYYY-MM-DD (default: today minus lag)")
    parser.add_argument("--workers", type=int, default=24, help="Parallel download threads")
    # The archive is not real-time: newest files observed to lag ~3-4 days
    # behind today. Default --end accounts for that so a plain run doesn't
    # waste requests on days that don't exist yet.
    parser.add_argument("--lag-days", type=int, default=5, help="Assumed archive publish lag")
    args = parser.parse_args()

    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=args.lag_days)
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=args.days - 1)

    backfill(start, end, args.workers)


if __name__ == "__main__":
    main()
