import { Weather } from "../types";
import { Centroid } from "./centroids";

// Called directly from the browser (not through our backend). Open-Meteo is
// a keyless public API with open CORS (access-control-allow-origin: *), and
// calling it from each visitor's own IP avoids the shared-IP rate limiting
// that free hosting platforms (Render, etc.) run into on high-traffic public
// APIs — see backend/main.py's _cached() comment for the backend-side story.
const WEATHER_URL = "https://api.open-meteo.com/v1/forecast";
const CURRENT_VARS =
  "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code";

interface OpenMeteoCurrent {
  temperature_2m?: number;
  apparent_temperature?: number;
  relative_humidity_2m?: number;
  wind_speed_10m?: number;
  weather_code?: number;
}

interface OpenMeteoResult {
  current?: OpenMeteoCurrent;
}

export async function fetchWeatherDirect(points: Centroid[]): Promise<Weather[]> {
  if (points.length === 0) return [];

  const latitude = points.map((p) => p.lat.toFixed(5)).join(",");
  const longitude = points.map((p) => p.lon.toFixed(5)).join(",");
  const url = `${WEATHER_URL}?latitude=${latitude}&longitude=${longitude}&current=${CURRENT_VARS}`;

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Open-Meteo error ${res.status}`);
  }
  const data = await res.json();
  const results: OpenMeteoResult[] = Array.isArray(data) ? data : [data];

  return points.map((p, i) => {
    const c = results[i]?.current ?? {};
    return {
      code: p.code,
      name: p.name,
      temperature: c.temperature_2m ?? null,
      apparent_temperature: c.apparent_temperature ?? null,
      humidity: c.relative_humidity_2m ?? null,
      wind_speed: c.wind_speed_10m ?? null,
      weather_code: c.weather_code ?? null,
    };
  });
}
