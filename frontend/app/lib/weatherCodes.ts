// WMO weather interpretation codes → short French label.
// https://open-meteo.com/en/docs (WMO Weather interpretation codes)
const CODES: Record<number, string> = {
  0: "Ciel clair",
  1: "Peu nuageux",
  2: "Partiellement nuageux",
  3: "Couvert",
  45: "Brouillard",
  48: "Brouillard givrant",
  51: "Bruine légère",
  53: "Bruine",
  55: "Bruine dense",
  61: "Pluie légère",
  63: "Pluie",
  65: "Pluie forte",
  71: "Neige légère",
  73: "Neige",
  75: "Neige forte",
  80: "Averses légères",
  81: "Averses",
  82: "Averses violentes",
  95: "Orage",
  96: "Orage + grêle",
  99: "Orage violent + grêle",
};

export function weatherLabel(code: number | null): string {
  if (code === null) return "—";
  return CODES[code] ?? "—";
}
