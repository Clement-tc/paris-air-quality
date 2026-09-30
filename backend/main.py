"""
FastAPI surface.

  GET  /health         liveness + whether an API key is configured
  POST /admin/refresh  run the ETL now, return ingestion stats
  GET  /admin/stats    counts + freshness, for a quality dashboard
  GET  /api/air        map-ready readings (latest per sensor) for the frontend
"""
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

import httpx
from fastapi import FastAPI, Depends, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import aqi
import pipeline
from config import settings
from database import init_db, get_session, SessionLocal, Location, Reading
from openaq_client import OpenAQError
from openmeteo_client import fetch_air_quality, fetch_weather, OpenMeteoError

# Arrondissement centroids (code, name, lat, lon) for the CAMS zone lookup.
_ARRONDISSEMENTS = json.loads(
    (Path(__file__).parent / "arrondissements.json").read_text(encoding="utf-8")
)

# --- Tiny in-memory TTL cache for upstream Open-Meteo calls ---
#
# Render's free-tier outbound IP is shared across many hobby projects hitting
# the same free Open-Meteo API, which gets rate-limited (HTTP 429) even at
# low request volume from us. Every page load + 5-min poll from every visitor
# was triggering its own upstream call — wasteful and exactly the pattern
# that trips shared-IP rate limits. Caching collapses that to one upstream
# call per TTL window, and serves the last good value on a failed refresh
# (e.g. transient 429) instead of surfacing an error to every visitor.
T = TypeVar("T")
_cache: dict[str, tuple[float, object]] = {}


async def _cached(key: str, ttl_seconds: float, fetch: Callable[[], Awaitable[T]]) -> T:
    now = time.monotonic()
    entry = _cache.get(key)
    if entry is not None and now - entry[0] < ttl_seconds:
        return entry[1]  # type: ignore[return-value]
    try:
        value = await fetch()
    except Exception:
        if entry is not None:
            return entry[1]  # type: ignore[return-value]  # serve stale on error
        raise
    _cache[key] = (now, value)
    return value


WEATHER_CACHE_TTL_SECONDS = 600  # 10 min — weather barely changes faster than this
ZONES_CACHE_TTL_SECONDS = 600


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # auto-create SQLite tables on startup
    # On platforms with an ephemeral disk (e.g. Render free tier), the SQLite
    # file is wiped on every redeploy/restart. Auto-refresh once at boot so
    # the map isn't empty after a cold start — best-effort, never blocks boot.
    if settings.openaq_api_key:
        try:
            with SessionLocal() as db:
                await pipeline.run_refresh(db)
        except Exception as e:  # noqa: BLE001
            print(f"Startup refresh skipped: {e}")
    yield


app = FastAPI(title="Paris Air Quality API", version="0.1.0", lifespan=lifespan)

# Frontend (Vercel) will call this from the browser, so allow cross-origin.
# Set FRONTEND_ORIGINS env var in production to your Vercel domain(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "openaq_key_configured": bool(settings.openaq_api_key),
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/admin/refresh")
async def refresh(db: Session = Depends(get_session)):
    try:
        stats = await pipeline.run_refresh(db)
    except OpenAQError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True, "stats": stats.__dict__}


@app.get("/admin/stats")
def stats(db: Session = Depends(get_session)):
    total = db.scalar(select(func.count()).select_from(Reading)) or 0
    locations = db.scalar(select(func.count()).select_from(Location)) or 0
    latest_ts = db.scalar(select(func.max(Reading.datetime_utc)))
    by_param = dict(
        db.execute(select(Reading.parameter, func.count()).group_by(Reading.parameter)).all()
    )
    by_category = dict(
        db.execute(
            select(Reading.category_label, func.count())
            .group_by(Reading.category_label)
        ).all()
    )
    return {
        "total_readings": total,
        "locations": locations,
        "latest_reading_utc": latest_ts.isoformat() if latest_ts else None,
        "readings_by_parameter": by_param,
        "readings_by_category": by_category,
    }


@app.get("/api/air")
def air(
    parameter: str | None = Query(None, description="e.g. pm25, no2"),
    db: Session = Depends(get_session),
):
    """
    Latest reading per (sensor) — map-ready. Each row already carries lat/lon,
    sub_index (column height) and color_hex/category (colour).
    """
    # newest datetime per sensor
    newest = (
        select(Reading.sensors_id, func.max(Reading.datetime_utc).label("mx"))
        .group_by(Reading.sensors_id)
        .subquery()
    )
    q = (
        select(Reading)
        .join(newest, (Reading.sensors_id == newest.c.sensors_id)
              & (Reading.datetime_utc == newest.c.mx))
    )
    if parameter:
        q = q.where(Reading.parameter == parameter.lower())

    rows = db.scalars(q).all()
    return {
        "count": len(rows),
        "readings": [
            {
                "location_id": r.location_id,
                "sensors_id": r.sensors_id,
                "parameter": r.parameter,
                "value": r.value,
                "units": r.units,
                "latitude": r.location.latitude,
                "longitude": r.location.longitude,
                "datetime_utc": r.datetime_utc.isoformat(),
                "category_index": r.category_index,
                "category_label": r.category_label,
                "color_hex": r.color_hex,
                "sub_index": r.sub_index,
            }
            for r in rows
        ],
    }


@app.get("/api/zones")
async def zones():
    """
    Per-arrondissement air quality from the CAMS European model (Open-Meteo).

    Unlike /api/air (sparse sensors), this covers EVERY arrondissement. Each
    pollutant is classified with the same EEA bands as the sensors (aqi.py),
    and the zone takes its WORST pollutant — the "general pollution" of the area.
    """
    points = [(a["lat"], a["lon"]) for a in _ARRONDISSEMENTS]
    try:
        concentrations = await _cached(
            "zones_concentrations", ZONES_CACHE_TTL_SECONDS,
            lambda: fetch_air_quality(points),
        )
    except OpenMeteoError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo request failed: {e}")

    zones_out = []
    for arr, conc in zip(_ARRONDISSEMENTS, concentrations):
        # classify every pollutant, keep the most severe one
        worst_param = None
        worst = aqi.Severity(None, None, None, None)
        for param, value in conc.items():
            sev = aqi.classify(param, value, "µg/m³")
            if sev.sub_index is not None and (
                worst.sub_index is None or sev.sub_index > worst.sub_index
            ):
                worst, worst_param = sev, param

        zones_out.append({
            "code": arr["code"],
            "name": arr["name"],
            "category_index": worst.category_index,
            "category_label": worst.category_label,
            "color_hex": worst.color_hex,
            "sub_index": worst.sub_index,
            "dominant_parameter": worst_param,
            "concentrations": conc,
        })

    return {"count": len(zones_out), "zones": zones_out}


@app.get("/api/weather")
async def weather():
    """
    Current weather per arrondissement (Open-Meteo forecast model).

    Temperature is near-uniform across a city, so values are close between
    arrondissements — that's physically expected, unlike air quality.
    """
    points = [(a["lat"], a["lon"]) for a in _ARRONDISSEMENTS]
    try:
        results = await _cached(
            "weather", WEATHER_CACHE_TTL_SECONDS,
            lambda: fetch_weather(points),
        )
    except OpenMeteoError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Open-Meteo request failed: {e}")

    weather_out = [
        {
            "code": arr["code"],
            "name": arr["name"],
            **w,
        }
        for arr, w in zip(_ARRONDISSEMENTS, results)
    ]
    return {"count": len(weather_out), "weather": weather_out}
