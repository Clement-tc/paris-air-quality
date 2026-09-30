import { useMemo } from "react";
import { ArrondCollection, enrichWithReadings } from "../lib/arrondissements";
import { AirReading } from "../types";
import { useArrondGeojson } from "./useArrondGeojson";

export function useArrondissements(readings: AirReading[]): ArrondCollection | null {
  const base = useArrondGeojson();

  // Recompute only when polygons or readings change — not on hover renders.
  return useMemo(() => {
    if (!base) return null;
    return enrichWithReadings(base, readings);
  }, [base, readings]);
}
