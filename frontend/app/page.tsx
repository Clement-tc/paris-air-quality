"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { AirReading, AirResponse, DataLayer, Weather, WeatherResponse } from "./types";
import AqiLegend from "./components/AqiLegend";
import TempLegend from "./components/TempLegend";
import ParameterSelector from "./components/ParameterSelector";
import LayerToggle from "./components/LayerToggle";
import StatsBar from "./components/StatsBar";

// deck.gl / maplibre must only render client-side
const AirMap = dynamic(() => import("./components/AirMap"), { ssr: false });

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const REFRESH_INTERVAL_MS = 5 * 60 * 1000; // re-fetch every 5 min

export default function Home() {
  const [readings, setReadings] = useState<AirReading[]>([]);
  const [weather, setWeather] = useState<Weather[]>([]);
  const [parameter, setParameter] = useState<string>("");
  const [dataLayer, setDataLayer] = useState<DataLayer>("aqi");
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (param: string) => {
    setLoading(true);
    setError(null);
    try {
      const url = `${API_BASE}/api/air${param ? `?parameter=${param}` : ""}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error(`API error ${res.status}`);
      const data: AirResponse = await res.json();
      // Keep all readings — AirMap groups them per station so one marker can
      // list every pollutant measured there.
      setReadings(data.readings);
      setLastUpdated(new Date().toISOString());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Weather is city-wide, independent of the selected pollutant.
  const fetchWeather = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/weather`);
      if (!res.ok) throw new Error(`Weather API error ${res.status}`);
      const data: WeatherResponse = await res.json();
      setWeather(data.weather);
    } catch (e) {
      console.error("Failed to fetch weather", e);
    }
  }, []);

  useEffect(() => {
    fetchData(parameter);
    const id = setInterval(() => fetchData(parameter), REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [parameter, fetchData]);

  useEffect(() => {
    fetchWeather();
    const id = setInterval(fetchWeather, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchWeather]);

  return (
    <div className="relative w-screen h-screen bg-black overflow-hidden">
      {/* Full-screen map */}
      <div className="absolute inset-0">
        <AirMap readings={readings} weather={weather} dataLayer={dataLayer} />
      </div>

      {/* Subtle radial vignette */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.55) 100%)",
        }}
      />

      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 p-4 flex flex-col gap-3 z-10">
        {/* Title + stats */}
        <div className="flex flex-wrap items-start gap-3">
          {/* Animated gradient title */}
          <div className="rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 px-5 py-3 shadow-xl">
            <h1
              className="text-xl font-bold tracking-tight"
              style={{
                background:
                  "linear-gradient(90deg, #50F0E6, #50CCAA, #F0E641, #FF5050)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                backgroundSize: "300% 100%",
                animation: "gradientShift 6s linear infinite",
              }}
            >
              Paris Air Quality
            </h1>
            <p className="text-white/40 text-xs mt-0.5">
            {dataLayer === "aqi" ? "Live · EEA Index" : "Live · Météo"}
          </p>
          </div>

          <div className="flex-1 min-w-0">
            <StatsBar
              readings={readings}
              weather={weather}
              dataLayer={dataLayer}
              lastUpdated={lastUpdated}
              loading={loading}
            />
          </div>

          {/* Refresh button */}
          <button
            onClick={() => {
              fetchData(parameter);
              fetchWeather();
            }}
            disabled={loading}
            className="rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 px-4 py-3 text-white/60 hover:text-white hover:bg-white/10 transition-all text-sm shadow-xl disabled:opacity-40 cursor-pointer"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                  <circle
                    className="opacity-25"
                    cx="12" cy="12" r="10"
                    stroke="currentColor" strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v8z"
                  />
                </svg>
                <span>Fetching</span>
              </span>
            ) : (
              "↻ Refresh"
            )}
          </button>
        </div>

        {/* Parameter selector (air quality only) + layer toggle */}
        <div className="flex flex-wrap gap-3">
          {dataLayer === "aqi" && (
            <ParameterSelector value={parameter} onChange={setParameter} />
          )}
          <LayerToggle value={dataLayer} onChange={setDataLayer} />
        </div>
      </div>

      {/* Bottom-right legend */}
      <div className="absolute bottom-6 right-4 z-10">
        {dataLayer === "aqi" ? <AqiLegend /> : <TempLegend />}
      </div>

      {/* Error toast */}
      {error && (
        <div className="absolute bottom-6 left-4 z-10 rounded-xl bg-red-900/80 backdrop-blur border border-red-500/30 px-4 py-3 text-red-200 text-sm shadow-xl max-w-xs">
          <span className="font-semibold">Error: </span>{error}
        </div>
      )}

      {/* Gradient shift keyframes */}
      <style>{`
        @keyframes gradientShift {
          0%   { background-position: 0% 50%; }
          100% { background-position: 300% 50%; }
        }
      `}</style>
    </div>
  );
}
