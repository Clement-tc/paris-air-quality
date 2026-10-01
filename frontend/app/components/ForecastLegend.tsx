"use client";
import { RISK_BANDS } from "../types";

export default function ForecastLegend() {
  return (
    <div className="rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 p-4 text-white shadow-xl min-w-[180px]">
      <p className="font-semibold text-sm tracking-tight">Probabilité de dépassement</p>
      <p className="text-[10px] text-white/40 mb-3 leading-snug">
        NO₂ uniquement · seuil 40 µg/m³ · +24h
      </p>
      <div className="flex flex-col gap-2">
        {RISK_BANDS.map((band) => (
          <div key={band.label} className="flex items-center gap-2.5">
            <span
              className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
              style={{
                backgroundColor: band.color,
                boxShadow: `0 0 6px ${band.color}`,
              }}
            />
            <span className="text-xs text-white/80">{band.label}</span>
          </div>
        ))}
        <div className="flex items-center gap-2.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0 bg-white/20" />
          <span className="text-xs text-white/50">Pas de donnée</span>
        </div>
      </div>
      <p className="mt-3 pt-2 border-t border-white/10 text-white/30 text-[10px] leading-snug">
        "Élevé" = forte chance de dégradation, pas forcément un air déjà mauvais aujourd'hui.
      </p>
    </div>
  );
}
