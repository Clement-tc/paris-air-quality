"use client";
import { DATA_LAYERS, DataLayer } from "../types";

interface Props {
  value: DataLayer;
  onChange: (v: DataLayer) => void;
}

export default function LayerToggle({ value, onChange }: Props) {
  return (
    <div className="rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 p-1.5 flex gap-1 shadow-xl">
      {DATA_LAYERS.map((l) => {
        const active = value === l.value;
        return (
          <button
            key={l.value}
            onClick={() => l.available && onChange(l.value)}
            disabled={!l.available}
            title={!l.available ? "Coming soon — needs weather API" : undefined}
            className={`relative px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 cursor-pointer ${
              !l.available
                ? "text-white/20 cursor-not-allowed"
                : active
                ? "bg-white text-black shadow-lg scale-105"
                : "text-white/60 hover:text-white hover:bg-white/10"
            }`}
          >
            {l.label}
            {!l.available && (
              <span className="ml-1.5 text-[9px] font-normal opacity-50">soon</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
