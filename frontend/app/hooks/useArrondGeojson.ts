import { useEffect, useState } from "react";
import type { FeatureCollection } from "geojson";
import { ARROND_GEOJSON_URL } from "../lib/arrondissements";

// Shared, cached loader for the arrondissement polygons. Loaded once and
// reused by both the air-quality and weather choropleths.
let cachedGeojson: FeatureCollection | null = null;

export function useArrondGeojson(): FeatureCollection | null {
  const [base, setBase] = useState<FeatureCollection | null>(cachedGeojson);

  useEffect(() => {
    if (cachedGeojson) return;
    fetch(ARROND_GEOJSON_URL)
      .then((r) => r.json())
      .then((data: FeatureCollection) => {
        cachedGeojson = data;
        setBase(data);
      })
      .catch((e) => console.error("Failed to load arrondissements GeoJSON", e));
  }, []);

  return base;
}
