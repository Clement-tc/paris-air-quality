"""
The ETL itself. Fetch -> validate -> transform/enrich -> quality-gate -> store.

The interesting bit is `transform`: the /latest payload only carries a
`sensorsId` and a number, so we first build a sensorsId -> (parameter, units,
location) map from the /locations payload, then join the latest values onto it.
Without that join every reading would be an anonymous float.

`transform` is deliberately pure (payloads in, CleanReadings out) so it can be
unit-tested offline with no network — see test_offline.py.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

import aqi
from config import settings
from models import RawLocation, RawLatest, CleanReading
from database import Location, Reading


@dataclass
class RefreshStats:
    locations_seen: int = 0
    latest_values_seen: int = 0
    readings_valid: int = 0
    readings_rejected: int = 0
    rejections: dict[str, int] = field(default_factory=dict)
    readings_inserted: int = 0
    readings_duplicate: int = 0

    def reject(self, reason: str) -> None:
        self.readings_rejected += 1
        self.rejections[reason] = self.rejections.get(reason, 0) + 1


# ---------- quality gate ----------

def _quality_check(r: CleanReading, stats: RefreshStats) -> bool:
    """Reject physically-impossible or out-of-scope readings. Returns True if OK."""
    min_lon, min_lat, max_lon, max_lat = settings.bbox_tuple

    if r.value is None:
        stats.reject("null_value"); return False
    if r.value < 0:
        stats.reject("negative_value"); return False
    if r.value > 10000:  # nothing in µg/m³ is sanely this high
        stats.reject("implausibly_high"); return False
    if not (min_lat <= r.latitude <= max_lat and min_lon <= r.longitude <= max_lon):
        stats.reject("outside_paris_bbox"); return False
    if r.datetime_utc > datetime.now(timezone.utc).replace(tzinfo=None) + _future_grace():
        stats.reject("future_timestamp"); return False
    if r.parameter not in settings.target_parameter_set:
        stats.reject("untracked_parameter"); return False
    return True


def _future_grace():
    from datetime import timedelta
    return timedelta(hours=2)  # allow minor clock skew


# ---------- transform (pure) ----------

def transform(locations_payload: list[dict], latest_by_loc: dict[int, list[dict]],
              stats: RefreshStats) -> list[CleanReading]:
    # 1. validate locations against the contract + build the sensor lookup
    sensor_index: dict[int, dict] = {}   # sensors_id -> {param, units, loc}
    for raw in locations_payload:
        loc = RawLocation.model_validate(raw)
        stats.locations_seen += 1
        for s in loc.sensors:
            sensor_index[s.id] = {
                "parameter": s.parameter.name,
                "units": s.parameter.units,
                "location": loc,
            }

    # 2. join latest values onto sensor metadata + enrich with severity
    readings: list[CleanReading] = []
    for loc_id, latest_list in latest_by_loc.items():
        for raw_latest in latest_list:
            stats.latest_values_seen += 1
            lv = RawLatest.model_validate(raw_latest)
            meta = sensor_index.get(lv.sensorsId)
            if meta is None:
                stats.reject("no_sensor_metadata"); continue

            loc: RawLocation = meta["location"]
            lat = lv.coordinates.latitude or loc.coordinates.latitude
            lon = lv.coordinates.longitude or loc.coordinates.longitude
            if lat is None or lon is None or lv.value is None:
                stats.reject("missing_coords_or_value"); continue

            sev = aqi.classify(meta["parameter"], lv.value, meta["units"])
            readings.append(CleanReading(
                location_id=loc.id,
                location_name=loc.name,
                sensors_id=lv.sensorsId,
                parameter=meta["parameter"],
                value=lv.value,
                units=meta["units"],
                latitude=lat,
                longitude=lon,
                datetime_utc=lv.datetime.utc.replace(tzinfo=None),
                datetime_local=lv.datetime.local,
                category_index=sev.category_index,
                category_label=sev.category_label,
                color_hex=sev.color_hex,
                sub_index=sev.sub_index,
            ))
    return readings


# ---------- load ----------

def ingest(readings: list[CleanReading], db: Session, stats: RefreshStats) -> None:
    # upsert locations first (so the FK is satisfied)
    seen_locs: dict[int, CleanReading] = {}
    for r in readings:
        seen_locs.setdefault(r.location_id, r)
    for loc_id, r in seen_locs.items():
        if db.get(Location, loc_id) is None:
            db.add(Location(id=loc_id, name=r.location_name,
                            latitude=r.latitude, longitude=r.longitude))
    db.flush()

    # insert readings; ON CONFLICT DO NOTHING gives idempotent re-refresh
    for r in readings:
        if not _quality_check(r, stats):
            continue
        stats.readings_valid += 1
        stmt = pg_insert(Reading).values(
            location_id=r.location_id, sensors_id=r.sensors_id, parameter=r.parameter,
            value=r.value, units=r.units, datetime_utc=r.datetime_utc,
            datetime_local=r.datetime_local, category_index=r.category_index,
            category_label=r.category_label, color_hex=r.color_hex, sub_index=r.sub_index,
        ).on_conflict_do_nothing(index_elements=["sensors_id", "datetime_utc"])
        result = db.execute(stmt)
        if result.rowcount:
            stats.readings_inserted += 1
        else:
            stats.readings_duplicate += 1
    db.commit()


# ---------- orchestration ----------

async def run_refresh(db: Session) -> RefreshStats:
    """Full live refresh: hit OpenAQ, transform, quality-gate, store."""
    import openaq_client  # imported here so offline tests don't need the network
    stats = RefreshStats()
    locations = await openaq_client.fetch_locations()
    loc_ids = [l["id"] for l in locations]
    latest = await openaq_client.fetch_latest(loc_ids)
    readings = transform(locations, latest, stats)
    ingest(readings, db, stats)
    return stats
