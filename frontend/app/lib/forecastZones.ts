import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";
import { RISK_BANDS, riskColor } from "../types";
import type { Station } from "./stations";

interface RawArrondProps {
  c_ar?: number;
  l_aroff?: string;
  geom_x_y?: [number, number]; // [lat, lon]
}

export interface ForecastZoneProperties {
  nom: string;
  code: string;
  risk_24h: number | null; // IDW-interpolated from nearby stations
  risk_label: string | null;
  color_hex: string | null;
  nearest_station_id: number | null;
  nearest_station_risk: number | null;
  source_count: number; // stations with a real forecast, used in the interpolation
}

export type ForecastZoneFeature = Feature<Polygon | MultiPolygon, ForecastZoneProperties>;
export type ForecastZoneCollection = FeatureCollection<Polygon | MultiPolygon, ForecastZoneProperties>;

const DEG2RAD = Math.PI / 180;

function riskLabel(risk: number): string {
  return RISK_BANDS.find((b) => risk < b.max)?.label ?? "Élevé";
}

/**
 * Same IDW approach as the AQI/weather zones (lib/arrondissements.ts): nearby
 * stations count more than far ones, so every arrondissement gets a value
 * from the real per-station predictions even though the model itself only
 * scores individual stations, not zones.
 */
export function enrichWithForecasts(
  geojson: FeatureCollection,
  stations: Station[],
): ForecastZoneCollection {
  const scored = stations.filter((s) => s.risk_24h != null);

  const features = geojson.features.map((feature) => {
    const raw = (feature.properties ?? {}) as RawArrondProps;
    const num = raw.c_ar;
    const nom = num
      ? `${num}${num === 1 ? "er" : "e"} — ${raw.l_aroff ?? ""}`.trim()
      : raw.l_aroff ?? "";

    const centroid = raw.geom_x_y;

    let risk_24h: number | null = null;
    let nearest_station_id: number | null = null;
    let nearest_station_risk: number | null = null;

    if (centroid && scored.length > 0) {
      const [cLat, cLon] = centroid;
      const lonScale = Math.cos(cLat * DEG2RAD);

      let weightedSum = 0;
      let weightTotal = 0;
      let nearest = scored[0];
      let nearestD2 = Infinity;

      for (const s of scored) {
        const dLat = cLat - s.latitude;
        const dLon = (cLon - s.longitude) * lonScale;
        const d2 = dLat * dLat + dLon * dLon;
        if (d2 < nearestD2) {
          nearestD2 = d2;
          nearest = s;
        }
        const w = 1 / (d2 + 1e-9);
        weightedSum += w * (s.risk_24h ?? 0);
        weightTotal += w;
      }

      risk_24h = weightTotal > 0 ? weightedSum / weightTotal : null;
      nearest_station_id = nearest.location_id;
      nearest_station_risk = nearest.risk_24h ?? null;
    }

    return {
      ...feature,
      properties: {
        nom,
        code: num ? String(num) : "",
        risk_24h,
        risk_label: risk_24h !== null ? riskLabel(risk_24h) : null,
        color_hex: risk_24h !== null ? riskColor(risk_24h) : null,
        nearest_station_id,
        nearest_station_risk,
        source_count: scored.length,
      },
    } as ForecastZoneFeature;
  });

  return { type: "FeatureCollection", features };
}
