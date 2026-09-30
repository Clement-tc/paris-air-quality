"""
Thin async client over the Open-Meteo Air Quality API (CAMS European model).

Unlike OpenAQ (sparse physical sensors), this is a continuous model: it returns
a value for ANY coordinate, so every arrondissement gets data and the map has
no holes. No API key required.

We query one batched request for all arrondissement centroids — Open-Meteo
accepts comma-separated latitude/longitude and returns one result object per
point, in the same order.

Docs: https://open-meteo.com/en/docs/air-quality-api
"""
import httpx

BASE_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo variable name -> our internal parameter name (matches aqi.py).
PARAM_MAP = {
    "pm2_5": "pm25",
    "pm10": "pm10",
    "nitrogen_dioxide": "no2",
    "ozone": "o3",
    "sulphur_dioxide": "so2",
    "carbon_monoxide": "co",
}
_VARS = ",".join(PARAM_MAP.keys())


class OpenMeteoError(RuntimeError):
    pass


async def fetch_air_quality(
    points: list[tuple[float, float]],
    timeout: float = 30.0,
) -> list[dict[str, float]]:
    """
    Fetch current pollutant concentrations (µg/m³) for a list of (lat, lon).

    Returns a list aligned with `points`; each item maps our parameter name
    (pm25, no2, ...) -> concentration. Missing values are omitted.
    """
    if not points:
        return []

    lats = ",".join(f"{lat:.5f}" for lat, _ in points)
    lons = ",".join(f"{lon:.5f}" for _, lon in points)
    params = {
        "latitude": lats,
        "longitude": lons,
        "current": _VARS,
        "domains": "cams_europe",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(BASE_URL, params=params)
        if resp.status_code == 429:
            raise OpenMeteoError("Rate limited by Open-Meteo (429). Slow down.")
        resp.raise_for_status()
        data = resp.json()

    # A single point returns an object; multiple points return a list.
    results = data if isinstance(data, list) else [data]

    out: list[dict[str, float]] = []
    for item in results:
        current = item.get("current", {})
        concentrations: dict[str, float] = {}
        for om_name, our_name in PARAM_MAP.items():
            val = current.get(om_name)
            if val is not None:
                concentrations[our_name] = float(val)
        out.append(concentrations)
    return out


# Current weather variables we surface (Open-Meteo name kept as-is).
_WEATHER_VARS = (
    "temperature_2m,apparent_temperature,relative_humidity_2m,"
    "wind_speed_10m,weather_code"
)


async def fetch_weather(
    points: list[tuple[float, float]],
    timeout: float = 30.0,
) -> list[dict[str, float | int | None]]:
    """
    Fetch current weather for a list of (lat, lon).

    Returns a list aligned with `points`; each item has temperature (°C),
    apparent_temperature (°C), humidity (%), wind_speed (km/h), weather_code.
    """
    if not points:
        return []

    lats = ",".join(f"{lat:.5f}" for lat, _ in points)
    lons = ",".join(f"{lon:.5f}" for _, lon in points)
    params = {
        "latitude": lats,
        "longitude": lons,
        "current": _WEATHER_VARS,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(WEATHER_URL, params=params)
        if resp.status_code == 429:
            raise OpenMeteoError("Rate limited by Open-Meteo (429). Slow down.")
        resp.raise_for_status()
        data = resp.json()

    results = data if isinstance(data, list) else [data]

    out: list[dict[str, float | int | None]] = []
    for item in results:
        c = item.get("current", {})
        out.append({
            "temperature": c.get("temperature_2m"),
            "apparent_temperature": c.get("apparent_temperature"),
            "humidity": c.get("relative_humidity_2m"),
            "wind_speed": c.get("wind_speed_10m"),
            "weather_code": c.get("weather_code"),
        })
    return out
