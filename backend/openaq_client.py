"""
Thin async client over the OpenAQ v3 REST API.

Only two calls are needed for ingestion:
  1. GET /locations?bbox=...      -> stations in Paris + their sensors
  2. GET /locations/{id}/latest   -> latest value per sensor at a station

Everything authenticates with the X-API-Key header. A missing/!invalid key
returns 401, which we surface clearly instead of pretending we got no data.
"""
import httpx

from config import settings


class OpenAQError(RuntimeError):
    pass


def _headers() -> dict[str, str]:
    if not settings.openaq_api_key:
        raise OpenAQError(
            "OPENAQ_API_KEY is not set. Sign up at https://explore.openaq.org "
            "and put the key in your .env file."
        )
    return {"X-API-Key": settings.openaq_api_key}


async def _get(client: httpx.AsyncClient, path: str, params: dict | None = None) -> dict:
    url = f"{settings.openaq_base_url}{path}"
    resp = await client.get(url, params=params, headers=_headers())
    if resp.status_code == 401:
        raise OpenAQError("OpenAQ rejected the API key (401). Check OPENAQ_API_KEY.")
    if resp.status_code == 410:
        raise OpenAQError("Got HTTP 410 Gone — you're hitting a dead v1/v2 endpoint. Use v3.")
    if resp.status_code == 429:
        raise OpenAQError("Rate limited by OpenAQ (429). Slow down or wait for reset.")
    resp.raise_for_status()
    return resp.json()


async def fetch_locations() -> list[dict]:
    """All monitoring locations within the Paris bbox (paginated)."""
    bbox = ",".join(str(x) for x in settings.bbox_tuple)
    results: list[dict] = []
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        page = 1
        while True:
            data = await _get(client, "/locations", {"bbox": bbox, "limit": 100, "page": page})
            batch = data.get("results", [])
            results.extend(batch)
            if len(batch) < 100 or len(results) >= settings.max_locations:
                break
            page += 1
    return results[: settings.max_locations]


async def fetch_latest(location_ids: list[int]) -> dict[int, list[dict]]:
    """Latest measurements for each location id. Returns {location_id: [latest,...]}."""
    out: dict[int, list[dict]] = {}
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        for loc_id in location_ids:
            try:
                data = await _get(client, f"/locations/{loc_id}/latest", {"limit": 100})
                out[loc_id] = data.get("results", [])
            except httpx.HTTPStatusError:
                out[loc_id] = []  # one bad station shouldn't sink the whole refresh
    return out


async def fetch_sensor_hours(sensors_id: int, datetime_from: str, datetime_to: str) -> list[dict]:
    """
    Real recent hourly aggregates for one sensor, straight from OpenAQ's live
    measurement pipeline (NOT the S3 archive export, which lags ~4-5 days).
    Used to backfill a freshly (re)deployed instance's history in one shot
    with genuine past readings, instead of waiting hours for /admin/refresh
    (which only ever captures a single "latest" snapshot per call) to build
    up the same depth naturally.
    """
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        try:
            data = await _get(client, f"/sensors/{sensors_id}/hours", {
                "datetime_from": datetime_from,
                "datetime_to": datetime_to,
                "limit": 100,
            })
        except httpx.HTTPStatusError:
            return []
    return data.get("results", [])
