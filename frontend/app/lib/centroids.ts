import type { FeatureCollection } from "geojson";

export interface Centroid {
  code: number;
  name: string;
  lat: number;
  lon: number;
}

interface RawProps {
  c_ar?: number;
  l_aroff?: string;
  geom_x_y?: [number, number]; // [lat, lon]
}

/** Pull the 20 arrondissement centroids out of the already-loaded polygons. */
export function extractCentroids(geojson: FeatureCollection): Centroid[] {
  const out: Centroid[] = [];
  for (const feature of geojson.features) {
    const p = (feature.properties ?? {}) as RawProps;
    if (p.c_ar && p.geom_x_y) {
      const [lat, lon] = p.geom_x_y;
      out.push({ code: p.c_ar, name: p.l_aroff ?? "", lat, lon });
    }
  }
  return out.sort((a, b) => a.code - b.code);
}
