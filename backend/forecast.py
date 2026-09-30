"""
Live NO2 exceedance forecast, served by /api/forecast.

Loads the model trained offline (ml/train_no2_exceedance.py) and reproduces,
from live data, the exact same features it was trained on:
  - lags/rolling mean of NO2 from this station's own stored history (DB)
  - current weather at the station's coordinates (Open-Meteo)
  - calendar features (Europe/Paris local time) + French holidays
  - station identity (location_id, categorical)

No custom decision threshold is applied here -- see train_no2_exceedance.py's
final section: threshold tuning proved unstable between CV and test, so we
serve the model's raw probability ("risk of exceeding 40 ug/m3 in 24h") and
let the UI show it as a graded risk rather than a fragile yes/no.
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays
import joblib
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import Location, Reading
from openmeteo_client import fetch_weather

MODEL_PATH = Path(__file__).parent / "models" / "no2_exceedance.joblib"
FR_HOLIDAYS = holidays.France(years=range(2024, 2030))
PARIS_TZ = ZoneInfo("Europe/Paris")

# Needs at least a 24h-old reading for the lag24h/rolling24h features to
# exist at all; without it we'd be guessing rather than predicting.
MIN_HISTORY_HOURS = 25
HISTORY_WINDOW_HOURS = 30  # a little slack around MIN_HISTORY_HOURS for gaps

_artifact = None


def _load_artifact() -> dict:
    global _artifact
    if _artifact is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"{MODEL_PATH} not found. Run ml/train_no2_exceedance.py to produce it."
            )
        _artifact = joblib.load(MODEL_PATH)
    return _artifact


def _nearest_value(rows: list[Reading], target_time: datetime, tolerance_minutes: int = 30) -> float | None:
    """The reading whose timestamp is closest to target_time, within tolerance."""
    best, best_diff = None, timedelta(minutes=tolerance_minutes)
    for r in rows:
        diff = abs(r.datetime_utc - target_time)
        if diff <= best_diff:
            best, best_diff = r.value, diff
    return best


def _station_features(rows: list[Reading], now: datetime) -> dict | None:
    """Build the lag/rolling NO2 features for one station from its recent readings."""
    if not rows:
        return None
    latest = max(rows, key=lambda r: r.datetime_utc)
    if now - latest.datetime_utc > timedelta(hours=2):
        return None  # station has gone stale/silent -- don't pretend to forecast it
    if latest.datetime_utc - min(r.datetime_utc for r in rows) < timedelta(hours=MIN_HISTORY_HOURS):
        return None  # not enough accumulated history yet for lag24h

    t = latest.datetime_utc
    window_start = t - timedelta(hours=24)
    past_24h = [r.value for r in rows if window_start <= r.datetime_utc < t]

    return {
        "no2_lag1h": _nearest_value(rows, t - timedelta(hours=1)),
        "no2_lag3h": _nearest_value(rows, t - timedelta(hours=3)),
        "no2_lag6h": _nearest_value(rows, t - timedelta(hours=6)),
        "no2_lag24h": _nearest_value(rows, t - timedelta(hours=24)),
        "no2_roll24h_mean": (sum(past_24h) / len(past_24h)) if len(past_24h) >= 6 else None,
        "as_of": t,
    }


def _sin_deg(deg: float | None) -> float | None:
    return None if deg is None else math.sin(math.radians(deg))


def _cos_deg(deg: float | None) -> float | None:
    return None if deg is None else math.cos(math.radians(deg))


async def compute_forecasts(db: Session) -> list[dict]:
    artifact = _load_artifact()
    station_ids: list[int] = artifact["known_station_ids"]
    feature_cols: list[str] = artifact["feature_cols"]
    model = artifact["model"]

    # DB datetimes are naive-but-UTC by this codebase's convention (see
    # pipeline.py: datetime_utc=lv.datetime.utc.replace(tzinfo=None)) --
    # match it here so comparisons don't raise on naive/aware mixing.
    now_utc_aware = datetime.now(timezone.utc)
    now = now_utc_aware.replace(tzinfo=None)
    since = now - timedelta(hours=HISTORY_WINDOW_HOURS)

    rows = db.scalars(
        select(Reading).where(
            Reading.location_id.in_(station_ids),
            Reading.parameter == "no2",
            Reading.datetime_utc >= since,
        )
    ).all()
    by_station: dict[int, list[Reading]] = {sid: [] for sid in station_ids}
    for r in rows:
        by_station[r.location_id].append(r)

    locations = {
        loc.id: loc for loc in db.scalars(select(Location).where(Location.id.in_(station_ids)))
    }

    station_feats = {
        sid: _station_features(by_station[sid], now)
        for sid in station_ids
        if sid in locations
    }
    forecastable = {sid: f for sid, f in station_feats.items() if f is not None}

    if not forecastable:
        return [
            {"location_id": sid, "risk_24h": None, "reason": "insufficient_history"}
            for sid in station_ids
        ]

    # One batched weather call for every forecastable station's own coordinates.
    ordered_ids = list(forecastable.keys())
    points = [(locations[sid].latitude, locations[sid].longitude) for sid in ordered_ids]
    weather = await fetch_weather(points)

    local_now = now_utc_aware.astimezone(PARIS_TZ)
    calendar = {
        "hour": local_now.hour,
        "dayofweek": local_now.weekday(),
        "month": local_now.month,
        "is_weekend": int(local_now.weekday() >= 5),
        "is_holiday": int(local_now.date() in FR_HOLIDAYS),
    }

    feature_rows = []
    for sid, w in zip(ordered_ids, weather):
        feats = forecastable[sid]
        wind_dir = w.get("wind_direction")
        feature_rows.append({
            **calendar,
            "no2_lag1h": feats["no2_lag1h"],
            "no2_lag3h": feats["no2_lag3h"],
            "no2_lag6h": feats["no2_lag6h"],
            "no2_lag24h": feats["no2_lag24h"],
            "no2_roll24h_mean": feats["no2_roll24h_mean"],
            "temperature_2m": w.get("temperature"),
            "relative_humidity_2m": w.get("humidity"),
            "wind_speed_10m": w.get("wind_speed"),
            "wind_dir_sin": _sin_deg(wind_dir),
            "wind_dir_cos": _cos_deg(wind_dir),
            "precipitation": w.get("precipitation"),
            "surface_pressure": w.get("surface_pressure"),
            "cloud_cover": w.get("cloud_cover"),
            "location_id": sid,
        })

    X = pd.DataFrame(feature_rows, columns=feature_cols)
    X["location_id"] = X["location_id"].astype("category")
    probs = model.predict_proba(X)[:, 1]

    results = [
        {
            "location_id": sid,
            "risk_24h": round(float(p), 3),
            "as_of": forecastable[sid]["as_of"].isoformat(),
        }
        for sid, p in zip(ordered_ids, probs)
    ]

    missing = set(station_ids) - set(ordered_ids)
    results += [
        {"location_id": sid, "risk_24h": None, "reason": "insufficient_history"}
        for sid in missing
    ]
    return results
