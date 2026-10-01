export interface AirReading {
  location_id: number;
  sensors_id: number;
  parameter: string;
  value: number;
  units: string;
  latitude: number;
  longitude: number;
  datetime_utc: string;
  category_index: number | null;
  category_label: string | null;
  color_hex: string | null;
  sub_index: number | null;
}

export interface AirResponse {
  count: number;
  readings: AirReading[];
}

// Current weather per arrondissement (from /api/weather).
export interface Weather {
  code: number; // arrondissement number
  name: string;
  temperature: number | null;
  apparent_temperature: number | null;
  humidity: number | null;
  wind_speed: number | null;
  weather_code: number | null;
}

export interface WeatherResponse {
  count: number;
  weather: Weather[];
}

// NO2 exceedance risk per station (from /api/forecast). null risk_24h means
// the station doesn't have enough accumulated history yet to forecast.
export interface Forecast {
  location_id: number;
  risk_24h: number | null;
  reason?: string;
  as_of?: string;
}

export interface ForecastResponse {
  count: number;
  forecasts: Forecast[];
}

export const PARAMETERS = [
  { value: "", label: "Général" },
  { value: "pm25", label: "PM2.5" },
  { value: "pm10", label: "PM10" },
  { value: "no2", label: "NO₂" },
  { value: "o3", label: "O₃" },
  { value: "so2", label: "SO₂" },
  { value: "co", label: "CO" },
] as const;

// Which data layer the map shows.
export type DataLayer = "aqi" | "temperature" | "forecast";

export const DATA_LAYERS: { value: DataLayer; label: string; available: boolean }[] = [
  { value: "aqi",         label: "Air Quality",  available: true },
  { value: "temperature", label: "Temperature",  available: true },
  { value: "forecast",    label: "Prediction NO₂", available: true },
];

// Risk colour bands for the NO2 exceedance forecast (+24h), low -> high.
// Deliberately an indigo -> violet -> magenta ramp, NOT green/yellow/red --
// reusing AQI's colours here would make people read "red zone" as "bad air
// right now" when it actually means "high PROBABILITY of crossing a
// threshold", a different thing from the current pollution level.
export const RISK_BANDS = [
  { max: 0.15, label: "Faible",  color: "#6C7AE0" },
  { max: 0.35, label: "Modéré",  color: "#9D5CE0" },
  { max: 1.01, label: "Élevé",   color: "#D6368F" },
] as const;

export function riskColor(risk: number): string {
  return RISK_BANDS.find((b) => risk < b.max)?.color ?? "#FF5050";
}

// Temperature colour ramp (°C thresholds → colour), cold blue → hot red.
export const TEMP_STOPS = [
  { t: 0,  color: "#4A6FE3" },
  { t: 10, color: "#4FB6E6" },
  { t: 18, color: "#50CCAA" },
  { t: 24, color: "#F0E641" },
  { t: 30, color: "#FF9130" },
  { t: 36, color: "#FF5050" },
] as const;

export const AQI_BANDS = [
  { label: "Good", color: "#50F0E6" },
  { label: "Fair", color: "#50CCAA" },
  { label: "Moderate", color: "#F0E641" },
  { label: "Poor", color: "#FF5050" },
  { label: "Very poor", color: "#960032" },
  { label: "Extremely poor", color: "#7D2181" },
] as const;
