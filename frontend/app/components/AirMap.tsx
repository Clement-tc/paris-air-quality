"use client";

import { useState, useCallback, useMemo } from "react";
import type { MapViewState, ViewStateChangeParameters } from "@deck.gl/core";
import Map from "react-map-gl/maplibre";
import { DeckGL } from "@deck.gl/react";
import type { ComponentProps } from "react";
import { IconLayer, GeoJsonLayer } from "@deck.gl/layers";
import type { PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";
import { AirReading, DataLayer, Forecast, Weather, riskColor } from "../types";
import { DETECTOR_ICON } from "../lib/detectorIcon";
import { groupStations, attachForecasts, type Station } from "../lib/stations";
import { useArrondissements } from "../hooks/useArrondissements";
import { useWeatherZones } from "../hooks/useWeatherZones";
import type { ArrondProperties } from "../lib/arrondissements";
import type { WeatherZoneProperties } from "../lib/weatherZones";
import { weatherLabel } from "../lib/weatherCodes";

const PARIS_BOUNDS: [[number, number], [number, number]] = [
  [2.20, 48.80],
  [2.50, 48.92],
];

const INITIAL_VIEW: MapViewState = {
  longitude: 2.347,
  latitude: 48.859,
  zoom: 11.8,
  pitch: 30,
  bearing: -10,
  minZoom: 10.5,
  maxZoom: 16,
};

// Keep the camera centre inside Paris. We clamp in deck.gl (the single camera
// authority) instead of using maplibre's maxBounds — mixing the two desyncs
// deck.gl from the basemap, which made the overlay "slide" while dragging.
function clampViewState(vs: MapViewState): MapViewState {
  return {
    ...vs,
    longitude: Math.min(Math.max(vs.longitude, PARIS_BOUNDS[0][0]), PARIS_BOUNDS[1][0]),
    latitude: Math.min(Math.max(vs.latitude, PARIS_BOUNDS[0][1]), PARIS_BOUNDS[1][1]),
  };
}

const MAP_STYLE =
  "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ];
}

interface StationTooltip {
  kind: "station";
  x: number;
  y: number;
  station: Station;
}
interface ZoneTooltip {
  kind: "zone";
  x: number;
  y: number;
  props: ArrondProperties;
}
interface WeatherTooltip {
  kind: "weather";
  x: number;
  y: number;
  props: WeatherZoneProperties;
}
type TooltipInfo = StationTooltip | ZoneTooltip | WeatherTooltip;

interface Props {
  readings: AirReading[];
  weather: Weather[];
  forecasts: Forecast[];
  dataLayer: DataLayer;
}

export default function AirMap({ readings, weather, forecasts, dataLayer }: Props) {
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);
  const [viewState, setViewState] = useState<MapViewState>(INITIAL_VIEW);

  // Group readings into stations (one marker per location, all pollutants kept),
  // then merge in the NO2 exceedance risk for each station if available.
  const stations = useMemo(
    () => attachForecasts(groupStations(readings), forecasts),
    [readings, forecasts],
  );
  // AQ zones: interpolate the real sensors (IDW) onto each arrondissement.
  const arrondissements = useArrondissements(readings);
  // Weather zones: join Open-Meteo weather onto each arrondissement by number.
  const weatherZones = useWeatherZones(weather);

  const onViewStateChange = useCallback(
    (params: ViewStateChangeParameters<MapViewState>) => {
      setViewState(clampViewState(params.viewState));
    },
    [],
  );

  const onHoverZone = useCallback((info: PickingInfo) => {
    if (info.object) {
      setTooltip({
        kind: "zone",
        x: info.x,
        y: info.y,
        props: (info.object as { properties: ArrondProperties }).properties,
      });
    } else {
      setTooltip(null);
    }
  }, []);

  const onHoverDetector = useCallback((info: PickingInfo) => {
    if (info.object) {
      setTooltip({
        kind: "station",
        x: info.x,
        y: info.y,
        station: info.object as Station,
      });
    } else {
      setTooltip((prev) => (prev?.kind === "station" ? null : prev));
    }
  }, []);

  const onHoverWeather = useCallback((info: PickingInfo) => {
    if (info.object) {
      setTooltip({
        kind: "weather",
        x: info.x,
        y: info.y,
        props: (info.object as { properties: WeatherZoneProperties }).properties,
      });
    } else {
      setTooltip(null);
    }
  }, []);

  // Arrondissement zone choropleth
  const zoneLayer =
    arrondissements &&
    new GeoJsonLayer({
      id: "arrond-zones",
      data: arrondissements,
      pickable: true,
      stroked: true,
      filled: true,
      getFillColor: (f) => {
        const hex = (f as { properties: ArrondProperties }).properties.color_hex;
        if (!hex) return [40, 40, 40, 60];
        const [r, g, b] = hexToRgb(hex);
        return [r, g, b, 70];
      },
      getLineColor: (f) => {
        const hex = (f as { properties: ArrondProperties }).properties.color_hex;
        if (!hex) return [80, 80, 80, 120];
        const [r, g, b] = hexToRgb(hex);
        return [r, g, b, 200];
      },
      lineWidthMinPixels: 1.5,
      onHover: onHoverZone,
      updateTriggers: {
        getFillColor: readings.map((r) => r.sub_index),
        getLineColor: readings.map((r) => r.sub_index),
      },
    });

  // Detector markers — show where the data comes from. Fixed red so they pop
  // against any zone colour (a severity-tinted marker blends into a same-
  // coloured zone and the rings become unreadable).
  const detectorLayer = new IconLayer<Station>({
    id: "detector-markers",
    data: stations,
    pickable: true,
    getIcon: () => DETECTOR_ICON,
    getPosition: (d) => [d.longitude, d.latitude],
    getSize: 30,
    sizeUnits: "pixels",
    getColor: (d) => {
      if (dataLayer !== "forecast") return [255, 45, 45, 255];
      // Prediction mode: colour by risk so a glance shows which stations are
      // elevated — grey means no forecast yet (not enough accumulated history).
      if (d.risk_24h == null) return [120, 120, 120, 180];
      const [r, g, b] = hexToRgb(riskColor(d.risk_24h));
      return [r, g, b, 255];
    },
    onHover: onHoverDetector,
    // Always draw markers on top — without this the tilted (3D) zone polygon
    // sits at the same depth and clips/masks the icon.
    parameters: { depthCompare: "always" },
    updateTriggers: {
      getColor: [dataLayer, stations.map((s) => s.risk_24h)],
    },
  });

  // Temperature choropleth (only in weather mode).
  const weatherLayer =
    weatherZones &&
    new GeoJsonLayer({
      id: "weather-zones",
      data: weatherZones,
      pickable: true,
      stroked: true,
      filled: true,
      getFillColor: (f) => {
        const hex = (f as { properties: WeatherZoneProperties }).properties.color_hex;
        if (!hex) return [40, 40, 40, 60];
        const [r, g, b] = hexToRgb(hex);
        return [r, g, b, 110];
      },
      getLineColor: (f) => {
        const hex = (f as { properties: WeatherZoneProperties }).properties.color_hex;
        if (!hex) return [80, 80, 80, 120];
        const [r, g, b] = hexToRgb(hex);
        return [r, g, b, 220];
      },
      lineWidthMinPixels: 1.5,
      onHover: onHoverWeather,
      updateTriggers: {
        getFillColor: weather.map((w) => w.temperature),
        getLineColor: weather.map((w) => w.temperature),
      },
    });

  // AQ mode: sensor zones + detector markers. Weather mode: temperature
  // zones only. Prediction mode: just the risk-coloured markers -- the
  // forecast is per-station, not per-arrondissement, so a zone layer here
  // would misleadingly imply a resolution the model doesn't have.
  const layers =
    dataLayer === "aqi"
      ? [...(zoneLayer ? [zoneLayer] : []), detectorLayer]
      : dataLayer === "forecast"
      ? [detectorLayer]
      : [...(weatherLayer ? [weatherLayer] : [])];

  return (
    <div className="relative w-full h-full">
      <DeckGL
        viewState={viewState}
        onViewStateChange={
          onViewStateChange as ComponentProps<typeof DeckGL>["onViewStateChange"]
        }
        controller={{ dragRotate: true, touchRotate: true }}
        layers={layers}
        style={{ position: "absolute", inset: "0" }}
      >
        <Map reuseMaps mapStyle={MAP_STYLE} />
      </DeckGL>

      {tooltip?.kind === "zone" && (
        <ZoneTooltipCard x={tooltip.x} y={tooltip.y} props={tooltip.props} />
      )}
      {tooltip?.kind === "station" && (
        <StationTooltipCard x={tooltip.x} y={tooltip.y} station={tooltip.station} />
      )}
      {tooltip?.kind === "weather" && (
        <WeatherTooltipCard x={tooltip.x} y={tooltip.y} props={tooltip.props} />
      )}
    </div>
  );
}

function WeatherTooltipCard({
  x,
  y,
  props,
}: {
  x: number;
  y: number;
  props: WeatherZoneProperties;
}) {
  const hasData = props.temperature !== null;
  return (
    <div
      className="pointer-events-none absolute z-50"
      style={{ left: x + 14, top: y - 10 }}
    >
      <div className="bg-black/85 backdrop-blur border border-white/10 rounded-xl px-4 py-3.5 text-white shadow-2xl min-w-[200px]">
        <div className="text-[11px] uppercase tracking-widest text-white/40 mb-1">
          {props.nom}
        </div>

        {hasData ? (
          <>
            <div className="flex items-baseline gap-2 mb-3">
              <span
                className="font-bold text-2xl tracking-tight"
                style={{ color: props.color_hex ?? "white" }}
              >
                {props.temperature!.toFixed(1)}°
              </span>
              <span className="text-xs text-white/50">
                {weatherLabel(props.weather_code)}
              </span>
            </div>

            <div className="space-y-1.5 text-xs">
              {props.apparent_temperature !== null && (
                <Row
                  label="Ressenti"
                  value={`${props.apparent_temperature.toFixed(1)}°C`}
                />
              )}
              {props.humidity !== null && (
                <Row label="Humidité" value={`${props.humidity}%`} />
              )}
              {props.wind_speed !== null && (
                <Row label="Vent" value={`${props.wind_speed.toFixed(0)} km/h`} />
              )}
            </div>

            <div className="mt-3 pt-2 border-t border-white/10 text-[10px] text-white/30">
              Open-Meteo · temp. 2 m
            </div>
          </>
        ) : (
          <div className="text-xs text-white/40 py-1">Données indisponibles</div>
        )}
      </div>
    </div>
  );
}

function ZoneTooltipCard({
  x,
  y,
  props,
}: {
  x: number;
  y: number;
  props: ArrondProperties;
}) {
  const hasData = props.sub_index !== null;
  return (
    <div
      className="pointer-events-none absolute z-50"
      style={{ left: x + 14, top: y - 10 }}
    >
      <div className="bg-black/85 backdrop-blur border border-white/10 rounded-xl px-4 py-3.5 text-white shadow-2xl min-w-[200px]">
        {/* Arrondissement name */}
        <div className="text-[11px] uppercase tracking-widest text-white/40 mb-1">
          {props.nom}
        </div>

        {hasData ? (
          <>
            {/* Headline: category as a coloured badge */}
            <div className="flex items-center gap-2 mb-3">
              <span
                className="inline-block w-3 h-3 rounded-full flex-shrink-0"
                style={{
                  backgroundColor: props.color_hex ?? "#888",
                  boxShadow: `0 0 10px ${props.color_hex ?? "#888"}`,
                }}
              />
              <span
                className="font-bold text-base tracking-tight"
                style={{ color: props.color_hex ?? "white" }}
              >
                {props.category_label}
              </span>
            </div>

            <div className="space-y-1.5 text-xs">
              <Row
                label="Indice global"
                value={`${props.sub_index!.toFixed(0)} / 100`}
              />
              {props.dominant_parameter && (
                <Row
                  label="Polluant dominant"
                  value={
                    props.dominant_value !== null
                      ? `${props.dominant_parameter.toUpperCase()} · ${props.dominant_value.toFixed(0)} µg/m³`
                      : props.dominant_parameter.toUpperCase()
                  }
                />
              )}
            </div>

            <div className="mt-3 pt-2 border-t border-white/10 text-[10px] text-white/30">
              Interpolé depuis {props.source_count} capteurs
            </div>
          </>
        ) : (
          <div className="text-xs text-white/40 py-1">Données indisponibles</div>
        )}
      </div>
    </div>
  );
}

function StationTooltipCard({
  x,
  y,
  station,
}: {
  x: number;
  y: number;
  station: Station;
}) {
  const count = station.readings.length;
  return (
    <div
      className="pointer-events-none absolute z-50"
      style={{ left: x + 14, top: y - 10 }}
    >
      <div className="bg-black/85 backdrop-blur border border-white/10 rounded-xl px-4 py-3.5 text-white shadow-2xl min-w-[210px]">
        <div className="flex items-center justify-between gap-3 mb-3">
          <span className="font-semibold text-sm tracking-tight">
            Station #{station.location_id}
          </span>
          <span className="text-[10px] text-white/40 uppercase tracking-widest">
            {count} polluant{count > 1 ? "s" : ""}
          </span>
        </div>

        <div className="space-y-2">
          {station.readings.map((r) => (
            <div
              key={r.sensors_id}
              className="flex items-center justify-between gap-3 text-xs"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{
                    backgroundColor: r.color_hex ?? "#666",
                    boxShadow: r.color_hex ? `0 0 6px ${r.color_hex}` : undefined,
                  }}
                />
                <span className="font-medium">{r.parameter.toUpperCase()}</span>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-white/90 tabular-nums">
                  {r.value.toFixed(1)} {r.units}
                </span>
                <span
                  className="text-[10px] w-16 text-right"
                  style={{ color: r.color_hex ?? "rgba(255,255,255,0.4)" }}
                >
                  {r.category_label ?? "—"}
                </span>
              </div>
            </div>
          ))}
        </div>

        {station.risk_24h != null && (
          <div className="mt-3 pt-3 border-t border-white/10">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] text-white/40 uppercase tracking-widest">
                Risque NO₂ (+24h)
              </span>
              <span
                className="text-xs font-semibold tabular-nums"
                style={{ color: riskColor(station.risk_24h) }}
              >
                {(station.risk_24h * 100).toFixed(0)}%
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({
  label,
  value,
  valueStyle,
}: {
  label: string;
  value: string;
  valueStyle?: React.CSSProperties;
}) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-white/40">{label}</span>
      <span className="text-white/90" style={valueStyle}>
        {value}
      </span>
    </div>
  );
}
