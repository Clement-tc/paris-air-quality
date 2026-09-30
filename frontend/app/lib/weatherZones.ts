import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";
import { Weather, TEMP_STOPS } from "../types";

interface RawArrondProps {
  c_ar?: number;
  l_aroff?: string;
}

export interface WeatherZoneProperties {
  nom: string;
  code: string;
  temperature: number | null;
  apparent_temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  weather_code: number | null;
  color_hex: string | null;
}

export type WeatherFeature = Feature<Polygon | MultiPolygon, WeatherZoneProperties>;
export type WeatherCollection = FeatureCollection<Polygon | MultiPolygon, WeatherZoneProperties>;

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

/** Continuous colour for a temperature, interpolated across TEMP_STOPS. */
export function tempToColor(t: number): string {
  const stops = TEMP_STOPS;
  if (t <= stops[0].t) return stops[0].color;
  if (t >= stops[stops.length - 1].t) return stops[stops.length - 1].color;
  for (let i = 0; i < stops.length - 1; i++) {
    const lo = stops[i];
    const hi = stops[i + 1];
    if (t >= lo.t && t <= hi.t) {
      const f = (t - lo.t) / (hi.t - lo.t);
      const [r1, g1, b1] = hexToRgb(lo.color);
      const [r2, g2, b2] = hexToRgb(hi.color);
      const r = lerp(r1, r2, f);
      const g = lerp(g1, g2, f);
      const b = lerp(b1, b2, f);
      return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
    }
  }
  return stops[stops.length - 1].color;
}

/** Join weather onto arrondissement polygons by arrondissement number. */
export function enrichWithWeather(
  geojson: FeatureCollection,
  weather: Weather[],
): WeatherCollection {
  const byCode = new Map<number, Weather>(weather.map((w) => [w.code, w]));

  const features = geojson.features.map((feature) => {
    const raw = (feature.properties ?? {}) as RawArrondProps;
    const num = raw.c_ar;
    const nom = num
      ? `${num}${num === 1 ? "er" : "e"} — ${raw.l_aroff ?? ""}`.trim()
      : raw.l_aroff ?? "";

    const w = num ? byCode.get(num) : undefined;
    const temperature = w?.temperature ?? null;

    return {
      ...feature,
      properties: {
        nom,
        code: num ? String(num) : "",
        temperature,
        apparent_temperature: w?.apparent_temperature ?? null,
        humidity: w?.humidity ?? null,
        wind_speed: w?.wind_speed ?? null,
        weather_code: w?.weather_code ?? null,
        color_hex: temperature !== null ? tempToColor(temperature) : null,
      },
    } as WeatherFeature;
  });

  return { type: "FeatureCollection", features };
}
