"use client";
import { AirReading, DataLayer, Forecast, Weather } from "../types";

interface Props {
  readings: AirReading[];
  weather: Weather[];
  forecasts: Forecast[];
  dataLayer: DataLayer;
  lastUpdated: string | null;
  loading: boolean;
}

export default function StatsBar({
  readings,
  weather,
  forecasts,
  dataLayer,
  lastUpdated,
  loading,
}: Props) {
  const categorised = readings.filter((r) => r.category_index !== null);
  const worst = categorised.reduce<AirReading | null>((acc, r) => {
    if (!acc || (r.category_index ?? 0) > (acc.category_index ?? 0)) return r;
    return acc;
  }, null);

  const avgIndex =
    categorised.length > 0
      ? categorised.reduce((s, r) => s + (r.sub_index ?? 0), 0) / categorised.length
      : null;

  const temps = weather
    .map((w) => w.temperature)
    .filter((t): t is number => t !== null);
  const avgTemp =
    temps.length > 0 ? temps.reduce((s, t) => s + t, 0) / temps.length : null;
  const avgWind =
    weather.length > 0
      ? weather
          .map((w) => w.wind_speed)
          .filter((v): v is number => v !== null)
          .reduce((s, v, _, arr) => s + v / arr.length, 0)
      : null;

  const scoredForecasts = forecasts.filter(
    (f): f is Forecast & { risk_24h: number } => f.risk_24h !== null,
  );
  const avgRisk =
    scoredForecasts.length > 0
      ? scoredForecasts.reduce((s, f) => s + f.risk_24h, 0) / scoredForecasts.length
      : null;
  const highestRisk = scoredForecasts.reduce<Forecast | null>((acc, f) => {
    if (!acc || (f.risk_24h ?? 0) > (acc.risk_24h ?? 0)) return f;
    return acc;
  }, null);

  const title =
    dataLayer === "aqi" ? "Paris Air Quality"
    : dataLayer === "temperature" ? "Paris Météo"
    : "Paris Prédiction";

  return (
    <div className="flex flex-wrap items-center gap-3 px-5 py-3 rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 text-white shadow-xl">
      <span className="font-bold text-base tracking-tight">{title}</span>

      <div className="w-px h-4 bg-white/20 hidden sm:block" />

      {loading ? (
        <span className="text-white/40 text-sm animate-pulse">Fetching data…</span>
      ) : dataLayer === "aqi" ? (
        <>
          <Stat label="Sensors" value={readings.length.toString()} />

          {avgIndex !== null && (
            <Stat label="Avg index" value={`${avgIndex.toFixed(1)} / 100`} />
          )}

          {worst && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-white/40 text-xs">Worst</span>
              <span
                className="px-2 py-0.5 rounded-full text-xs font-medium"
                style={{
                  backgroundColor: worst.color_hex + "33",
                  color: worst.color_hex ?? "white",
                  border: `1px solid ${worst.color_hex}66`,
                  textShadow: `0 0 8px ${worst.color_hex}`,
                }}
              >
                {worst.category_label} · {worst.parameter.toUpperCase()}
              </span>
            </div>
          )}
        </>
      ) : dataLayer === "temperature" ? (
        <>
          {avgTemp !== null && (
            <Stat label="Temp. moy." value={`${avgTemp.toFixed(1)}°C`} />
          )}
          {avgWind !== null && (
            <Stat label="Vent moy." value={`${avgWind.toFixed(0)} km/h`} />
          )}
          <Stat label="Zones" value={weather.length.toString()} />
        </>
      ) : (
        <>
          <Stat
            label="Stations prévues"
            value={`${scoredForecasts.length} / ${forecasts.length}`}
          />
          {avgRisk !== null && (
            <Stat label="Risque moy." value={`${(avgRisk * 100).toFixed(0)}%`} />
          )}
          {highestRisk && highestRisk.risk_24h !== null && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-white/40 text-xs">Max</span>
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-white/10">
                Station #{highestRisk.location_id} · {(highestRisk.risk_24h * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </>
      )}

      {!loading && lastUpdated && (
        <span className="text-white/30 text-xs ml-auto">
          {new Date(lastUpdated).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className="text-[10px] text-white/40 uppercase tracking-widest">{label}</span>
      <span className="text-sm font-semibold tabular-nums">{value}</span>
    </div>
  );
}
