import { useMemo } from "react";
import { ForecastZoneCollection, enrichWithForecasts } from "../lib/forecastZones";
import type { Station } from "../lib/stations";
import { useArrondGeojson } from "./useArrondGeojson";

export function useForecastZones(stations: Station[]): ForecastZoneCollection | null {
  const base = useArrondGeojson();

  return useMemo(() => {
    if (!base) return null;
    return enrichWithForecasts(base, stations);
  }, [base, stations]);
}
