"use client";
import { AQI_BANDS } from "../types";

export default function AqiLegend() {
  return (
    <div className="rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 p-4 text-white shadow-xl min-w-[160px]">
      <p className="font-semibold text-sm mb-3 tracking-tight">EEA Index</p>
      <div className="flex flex-col gap-2">
        {AQI_BANDS.map((band) => (
          <div key={band.label} className="flex items-center gap-2.5">
            <span
              className="inline-block w-2.5 h-2.5 rounded-sm flex-shrink-0"
              style={{
                backgroundColor: band.color,
                boxShadow: `0 0 6px ${band.color}`,
              }}
            />
            <span className="text-xs text-white/80">{band.label}</span>
          </div>
        ))}
      </div>
      <p className="mt-3 text-white/30 text-[10px] leading-snug">
        Couleur de zone = niveau de pollution
      </p>
    </div>
  );
}
