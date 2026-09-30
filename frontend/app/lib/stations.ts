import { AirReading } from "../types";

/**
 * A monitoring station = one physical location that may carry several sensors
 * (one per pollutant). We group readings by location so a single marker can
 * show ALL pollutants measured there, instead of just one.
 */
export interface Station {
  location_id: number;
  latitude: number;
  longitude: number;
  readings: AirReading[]; // every pollutant measured at this location
  dominant: AirReading;   // worst pollutant (highest sub_index) — drives zones
}

export function groupStations(readings: AirReading[]): Station[] {
  const byLocation = new Map<number, AirReading[]>();
  for (const r of readings) {
    const list = byLocation.get(r.location_id);
    if (list) list.push(r);
    else byLocation.set(r.location_id, [r]);
  }

  const stations: Station[] = [];
  for (const list of byLocation.values()) {
    // sort pollutants worst-first for a tidy tooltip
    const sorted = [...list].sort(
      (a, b) => (b.sub_index ?? -1) - (a.sub_index ?? -1),
    );
    const first = sorted[0];
    stations.push({
      location_id: first.location_id,
      latitude: first.latitude,
      longitude: first.longitude,
      readings: sorted,
      dominant: first,
    });
  }
  return stations;
}
