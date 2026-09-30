"""
Offline pipeline test. Proves the transform + quality gate + storage all work
WITHOUT any network or API key, by feeding the captured sample payloads through
the same code path /admin/refresh uses.

Run:  python test_offline.py
"""
import json
import os
import tempfile

# point the DB at a throwaway file BEFORE importing modules that read settings
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from database import init_db, SessionLocal, Reading, Location  # noqa: E402
import pipeline  # noqa: E402

HERE = os.path.dirname(__file__)


def main() -> None:
    init_db()
    with open(os.path.join(HERE, "sample_data/locations_sample.json")) as f:
        locations = json.load(f)["results"]
    with open(os.path.join(HERE, "sample_data/latest_sample.json")) as f:
        latest = {int(k): v for k, v in json.load(f).items()}

    stats = pipeline.RefreshStats()
    readings = pipeline.transform(locations, latest, stats)

    db = SessionLocal()
    pipeline.ingest(readings, db, stats)

    print("=== transform + ingest stats ===")
    for k, v in stats.__dict__.items():
        print(f"  {k}: {v}")

    print("\n=== enriched rows in SQLite ===")
    for r in db.query(Reading).order_by(Reading.parameter).all():
        print(f"  {r.parameter:5s} {r.value:6.1f} {str(r.units):6s} "
              f"-> {str(r.category_label):14s} sub_index={r.sub_index} {r.color_hex}")

    # ---- assertions: the bits an interviewer would poke at ----
    assert stats.locations_seen == 2
    assert stats.latest_values_seen == 5
    # the -4.0 NO2 reading must be rejected as negative
    assert stats.rejections.get("negative_value") == 1, stats.rejections
    assert stats.readings_inserted == 4
    # re-ingest is idempotent: no new rows, all duplicates
    stats2 = pipeline.RefreshStats()
    pipeline.ingest(readings, db, stats2)
    assert stats2.readings_inserted == 0 and stats2.readings_duplicate == 4, stats2.__dict__
    # severity sanity: NO2 95 µg/m³ is EEA band 3 "Moderate"
    no2 = db.query(Reading).filter_by(parameter="no2").one()
    assert no2.category_label == "Moderate", no2.category_label

    print("\nAll assertions passed ✅  (idempotent re-ingest verified)")
    db.close()
    os.unlink(_tmp.name)


if __name__ == "__main__":
    main()
