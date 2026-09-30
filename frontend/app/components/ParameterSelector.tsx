"use client";
import { PARAMETERS } from "../types";

interface Props {
  value: string;
  onChange: (v: string) => void;
}

export default function ParameterSelector({ value, onChange }: Props) {
  return (
    <div className="rounded-2xl bg-white/5 backdrop-blur-md border border-white/10 p-2 flex flex-wrap gap-1.5 shadow-xl">
      {PARAMETERS.map((p) => {
        const active = value === p.value;
        return (
          <button
            key={p.value}
            onClick={() => onChange(p.value)}
            className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition-all duration-200 cursor-pointer ${
              active
                ? "bg-white text-black shadow-lg scale-105"
                : "text-white/60 hover:text-white hover:bg-white/10"
            }`}
          >
            {p.label}
          </button>
        );
      })}
    </div>
  );
}
