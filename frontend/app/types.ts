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

export const PARAMETERS = [
  { value: "", label: "Général" },
  { value: "pm25", label: "PM2.5" },
  { value: "pm10", label: "PM10" },
  { value: "no2", label: "NO₂" },
  { value: "o3", label: "O₃" },
  { value: "so2", label: "SO₂" },
  { value: "co", label: "CO" },
] as const;

// Which data layer the zone choropleth shows.
export type DataLayer = "aqi" | "temperature";

export const DATA_LAYERS: { value: DataLayer; label: string; available: boolean }[] = [
  { value: "aqi",         label: "Air Quality", available: true },
  { value: "temperature", label: "Temperature", available: true },
];

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
