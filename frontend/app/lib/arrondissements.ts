import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";
import { AirReading, AQI_BANDS } from "../types";
import { groupStations } from "./stations";

// Paris OpenData — the real 20 arrondissements (1 polygon each).
// Bundled in /public to avoid a cross-origin fetch (opendata.paris.fr sends
// no CORS headers, so a browser fetch would be blocked). Boundaries are static.
export const ARROND_GEOJSON_URL = "/arrondissements.geojson";

// Source fields: c_ar (number), l_aroff (name), geom_x_y ([lat, lon] centroid).
interface RawArrondProps {
  c_ar?: number;
  l_aroff?: string;
  geom_x_y?: [number, number];
}

export interface ArrondProperties {
  nom: string;
  code: string;
  sub_index: number | null;
  category_label: string | null;
  color_hex: string | null;
  dominant_parameter: string | null; // from the nearest station
  dominant_value: number | null;
  source_count: number; // sensors used in the interpolation
}

export type ArrondFeature = Feature<Polygon | MultiPolygon, ArrondProperties>;
export type ArrondCollection = FeatureCollection<Polygon | MultiPolygon, ArrondProperties>;

function subIndexToBand(v: number): { label: string; color: string } {
  const idx = Math.min(Math.floor((v / 100) * AQI_BANDS.length), AQI_BANDS.length - 1);
  return AQI_BANDS[idx];
}

const DEG2RAD = Math.PI / 180;

/**
 * Colour each arrondissement by interpolating the real sensors via IDW
 * (inverse-distance weighting): nearby sensors count more than far ones.
 *
 * This is what gives the map real intra-Paris variation — the CAMS model is
 * 11 km, too coarse to differentiate arrondissements (they all come out equal).
 * Every centroid gets a value because every sensor contributes (weighted), so
 * there are no holes either.
 */
export function enrichWithReadings(
  geojson: FeatureCollection,
  readings: AirReading[],
): ArrondCollection {
  // One representative point per station = its worst pollutant.
  const stations = groupStations(readings).filter((s) => s.dominant.sub_index !== null);

  const features = geojson.features.map((feature) => {
    const raw = (feature.properties ?? {}) as RawArrondProps;
    const num = raw.c_ar;
    const nom = num
      ? `${num}${num === 1 ? "er" : "e"} — ${raw.l_aroff ?? ""}`.trim()
      : raw.l_aroff ?? "";

    const centroid = raw.geom_x_y; // [lat, lon]

    let sub_index: number | null = null;
    let dominant_parameter: string | null = null;
    let dominant_value: number | null = null;

    if (centroid && stations.length > 0) {
      const [cLat, cLon] = centroid;
      const lonScale = Math.cos(cLat * DEG2RAD);

      let weightedSum = 0;
      let weightTotal = 0;
      let nearest = stations[0];
      let nearestD2 = Infinity;

      for (const s of stations) {
        const dLat = cLat - s.latitude;
        const dLon = (cLon - s.longitude) * lonScale;
        const d2 = dLat * dLat + dLon * dLon;
        if (d2 < nearestD2) {
          nearestD2 = d2;
          nearest = s;
        }
        const w = 1 / (d2 + 1e-9); // IDW power 2
        weightedSum += w * (s.dominant.sub_index ?? 0);
        weightTotal += w;
      }

      sub_index = weightTotal > 0 ? weightedSum / weightTotal : null;
      dominant_parameter = nearest.dominant.parameter;
      dominant_value = nearest.dominant.value;
    }

    const band = sub_index !== null ? subIndexToBand(sub_index) : null;

    return {
      ...feature,
      properties: {
        nom,
        code: num ? String(num) : "",
        sub_index,
        category_label: band?.label ?? null,
        color_hex: band?.color ?? null,
        dominant_parameter,
        dominant_value,
        source_count: stations.length,
      },
    } as ArrondFeature;
  });

  return { type: "FeatureCollection", features };
}
