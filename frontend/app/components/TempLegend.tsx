"use client";
import { TEMP_STOPS } from "../types";

export default function TempLegend() {
  const gradient = `linear-gradient(to right, ${TEMP_STOPS.map(
    (s) => s.color,
  ).join(", ")})`;

  return (
    <div className="rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 p-4 text-white shadow-xl min-w-[180px]">
      <p className="font-semibold text-sm mb-3 tracking-tight">Température</p>
      <div
        className="h-2.5 rounded-full mb-1.5"
        style={{ background: gradient }}
      />
      <div className="flex justify-between text-[10px] text-white/60">
        <span>{TEMP_STOPS[0].t}°</span>
        <span>{TEMP_STOPS[Math.floor(TEMP_STOPS.length / 2)].t}°</span>
        <span>{TEMP_STOPS[TEMP_STOPS.length - 1].t}°+</span>
      </div>
      <p className="mt-3 text-white/30 text-[10px] leading-snug">
        Modèle Open-Meteo · temp. 2 m
      </p>
    </div>
  );
}
