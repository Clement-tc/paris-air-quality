"""
Bulk historical weather backfill from the Open-Meteo Historical Weather API
(ERA5 reanalysis, no API key, free, goes back to 1940).

This is the weather-as-feature counterpart to backfill_openaq.py: pollutant
concentrations are driven heavily by wind, temperature, humidity, pressure,
and precipitation, so a forecasting model needs these joined in.

We query one station's coordinates per point but batch ALL 28 Paris stations
into a single request per date range (the API accepts comma-separated lat/lon
and returns one hourly series per point, aligned by index) — far fewer HTTP
calls than one request per station.

Usage:
    python backfill_weather.py --days 365
    python backfill_weather.py --start 2025-01-01 --end 2025-12-31
"""
import argparse
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

BACKEND_DB = Path(__file__).parent.parent / "backend" / "paris_air.db"
OUT_DIR = Path(__file__).parent.parent / "data"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

HOURLY_VARS = (
    "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,"
    "precipitation,surface_pressure,cloud_cover"
)

# The archive API rejects overly long [start,end] x many-points requests, and
# large windows are slow to generate server-side — chunk by month.
CHUNK_DAYS = 31


def get_paris_stations() -> pd.DataFrame:
    if not BACKEND_DB.exists():
        raise FileNotFoundError(
            f"{BACKEND_DB} not found. Run the backend at least once "
            "(POST /admin/refresh) so locations are populated."
        )
    conn = sqlite3.connect(BACKEND_DB)
    df = pd.read_sql("SELECT id AS location_id, latitude, longitude FROM locations ORDER BY id", conn)
    conn.close()
    return df


def _chunks(start: date, end: date, size: int):
    d = start
    while d <= end:
        chunk_end = min(d + timedelta(days=size - 1), end)
        yield d, chunk_end
        d = chunk_end + timedelta(days=1)


def fetch_chunk(stations: pd.DataFrame, start: date, end: date, client: httpx.Client) -> pd.DataFrame:
    lats = ",".join(f"{lat:.5f}" for lat in stations["latitude"])
    lons = ",".join(f"{lon:.5f}" for lon in stations["longitude"])
    params = {
        "latitude": lats,
        "longitude": lons,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": HOURLY_VARS,
        "timezone": "UTC",
    }
    resp = client.get(ARCHIVE_URL, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    results = data if isinstance(data, list) else [data]

    frames = []
    for (_, station), item in zip(stations.iterrows(), results):
        hourly = item.get("hourly", {})
        df = pd.DataFrame(hourly)
        if df.empty:
            continue
        df["location_id"] = station["location_id"]
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def backfill(start: date, end: date) -> Path:
    stations = get_paris_stations()
    print(f"Backfilling weather for {len(stations)} stations, {start} -> {end}")

    frames: list[pd.DataFrame] = []
    with httpx.Client() as client:
        for c_start, c_end in _chunks(start, end, CHUNK_DAYS):
            print(f"  fetching {c_start} -> {c_end} ...")
            try:
                df = fetch_chunk(stations, c_start, c_end, client)
                frames.append(df)
            except httpx.HTTPStatusError as e:
                print(f"  ! chunk {c_start}->{c_end} failed: {e}")
            time.sleep(0.5)  # be polite, free tier

    full = pd.concat(frames, ignore_index=True)
    full = full.rename(columns={"time": "datetime"})
    full["datetime"] = pd.to_datetime(full["datetime"], utc=True)

    OUT_DIR.mkdir(exist_ok=True)
    out_path = OUT_DIR / f"weather_history_{start:%Y%m%d}_{end:%Y%m%d}.parquet"
    full.to_parquet(out_path, index=False)

    print(f"\nWrote {len(full):,} rows -> {out_path}")
    print(f"Stations covered: {full['location_id'].nunique()} / {len(stations)}")
    print(f"Date range in data: {full['datetime'].min()} -> {full['datetime'].max()}")

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Open-Meteo historical weather")
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--start", type=str)
    parser.add_argument("--end", type=str, help="Default: today minus 3 days (ERA5 has a short publish lag)")
    args = parser.parse_args()

    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=3)
    start = date.fromisoformat(args.start) if args.start else end - timedelta(days=args.days - 1)

    backfill(start, end)


if __name__ == "__main__":
    main()
