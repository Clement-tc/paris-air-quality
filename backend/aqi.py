"""
The transform that makes the data meaningful for the map.

A raw concentration (e.g. "42 µg/m³ NO2") means nothing to a viewer and can't
drive a colour ramp on its own, because each pollutant lives on a different
scale. So for every reading we compute:

  - category_index   1..6   (which EEA band it falls in)
  - category_label   "Good" .. "Extremely poor"
  - color_hex        the official EEA colour for that band
  - sub_index        a continuous 0..100 severity score (band position +
                     linear interpolation within the band)

The 3D map then uses `sub_index` for column HEIGHT (consistent across
pollutants) and `color_hex`/`category_index` for COLOUR.

Bands are the European Environment Agency (EEA) European Air Quality Index,
in µg/m³. They are kept as a single editable table so they're easy to audit
or swap for US EPA AQI later. Hourly basis for NO2/O3/SO2, 24h for PM.
CO is not part of the EEA index, so it stores a raw value with no category.
"""
from dataclasses import dataclass

# (label, color) per band index 1..6
_BANDS = [
    ("Good", "#50F0E6"),
    ("Fair", "#50CCAA"),
    ("Moderate", "#F0E641"),
    ("Poor", "#FF5050"),
    ("Very poor", "#960032"),
    ("Extremely poor", "#7D2181"),
]

# Upper bound (inclusive) of each band, in µg/m³, per pollutant.
# Index i in the list is the ceiling of band (i+1). Anything above the last
# listed ceiling is clamped into the top band.
_BREAKPOINTS: dict[str, list[float]] = {
    "pm25": [10, 20, 25, 50, 75, 800],
    "pm10": [20, 40, 50, 100, 150, 1200],
    "no2":  [40, 90, 120, 230, 340, 1000],
    "o3":   [50, 100, 130, 240, 380, 800],
    "so2":  [100, 200, 350, 500, 750, 1250],
}


@dataclass
class Severity:
    category_index: int | None      # 1..6, or None if not categorisable
    category_label: str | None
    color_hex: str | None
    sub_index: float | None         # 0..100 continuous, or None


def classify(parameter: str, value: float, units: str | None) -> Severity:
    """Map a (parameter, value) pair onto the EEA index."""
    param = parameter.lower()

    # Only µg/m³ readings are comparable to the EEA bands. If a provider reports
    # something else (e.g. ppm), we keep the value but skip categorisation
    # rather than silently mis-classify it.
    units_ok = units is None or units.replace("μ", "µ").lower() in {"µg/m³", "ug/m3", "µg/m3"}

    if param not in _BREAKPOINTS or not units_ok or value is None or value < 0:
        return Severity(None, None, None, None)

    ceilings = _BREAKPOINTS[param]
    floor = 0.0
    for i, ceil in enumerate(ceilings):
        if value <= ceil:
            label, color = _BANDS[i]
            # position within this band, 0..1
            span = ceil - floor or 1.0
            frac = min(max((value - floor) / span, 0.0), 1.0)
            # continuous score: each of the 6 bands occupies ~16.67 points
            sub_index = round((i + frac) / 6 * 100, 2)
            return Severity(i + 1, label, color, sub_index)
        floor = ceil

    # above the top ceiling -> clamp to worst band
    label, color = _BANDS[-1]
    return Severity(6, label, color, 100.0)
