import { useMemo } from "react";
import { WeatherCollection, enrichWithWeather } from "../lib/weatherZones";
import { Weather } from "../types";
import { useArrondGeojson } from "./useArrondGeojson";

export function useWeatherZones(weather: Weather[]): WeatherCollection | null {
  const base = useArrondGeojson();

  return useMemo(() => {
    if (!base) return null;
    return enrichWithWeather(base, weather);
  }, [base, weather]);
}
