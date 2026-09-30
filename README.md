# Paris Air Quality — Backend (ingestion pipeline)

Live ETL that pulls Paris air-quality readings from the **OpenAQ v3 API**,
validates and quality-gates them, enriches each reading with a European Air
Quality Index (EEA) severity, and stores history in SQLite — shaped so a 3D map,
a time slider, and arrondissement aggregation can all read from it directly.

## Run it (Windows / PowerShell)

```powershell
cd C:\Users\delga\code\paris-air-quality\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# open .env and paste your OpenAQ key (free: https://explore.openaq.org)

uvicorn main:app --reload
```

Then, in another terminal (or the browser):

```powershell
# prove the wiring without the network first:
python test_offline.py

# liveness
curl http://127.0.0.1:8000/health

# fetch real Paris data into SQLite
curl -X POST http://127.0.0.1:8000/admin/refresh

# see what landed
curl http://127.0.0.1:8000/admin/stats
curl "http://127.0.0.1:8000/api/air?parameter=no2"
```

Interactive docs: http://127.0.0.1:8000/docs

## How ingestion works (the important part)

OpenAQ v3 splits the data you need across two calls, and the join between them
is the heart of the pipeline:

1. `GET /locations?bbox=<paris>` — stations + their **sensors**. This is the
   only place that says *sensor 11002 measures NO2 in µg/m³*.
2. `GET /locations/{id}/latest` — latest values, but each row is just a
   `value` + a `sensorsId`. No pollutant name.

So `pipeline.transform()` builds a `sensorsId → parameter/units` map from (1),
then joins the latest values from (2) onto it. Then every reading is enriched
with severity (`aqi.classify`) and pushed through a quality gate before storage.

```
fetch ─▶ validate (Pydantic) ─▶ join + enrich ─▶ quality gate ─▶ store (idempotent)
```

## Files

| File | Role |
|------|------|
| `config.py` | typed settings (API key, bbox, db url) from `.env` |
| `openaq_client.py` | async httpx client for the two v3 calls |
| `models.py` | Pydantic: raw v3 contract + our clean `CleanReading` |
| `aqi.py` | EEA index bands → category + colour + 0–100 `sub_index` |
| `pipeline.py` | transform (pure), quality gate, idempotent ingest, refresh |
| `database.py` | SQLAlchemy ORM (`Location`, `Reading`) + session |
| `main.py` | FastAPI: `/health`, `/admin/refresh`, `/admin/stats`, `/api/air` |
| `test_offline.py` | runs the full pipeline on sample data, no network |

## Schema, and why it's shaped this way

- **`Reading`** carries `latitude/longitude`, `sub_index` (column height),
  `color_hex`/`category_index` (colour) — so `/api/air` is map-ready with no
  frontend math.
- Every reading is **timestamped** and history is kept → time slider later.
- `UniqueConstraint(sensors_id, datetime_utc)` makes re-refreshing **idempotent**
  (verified by the test).
- `Location.arrondissement` exists but is null for now — Phase C fills it with a
  point-in-polygon lookup against the 20-arrondissement GeoJSON.

## Notes / honest caveats

- EEA bands in `aqi.py` are the published European AQI thresholds (µg/m³). They
  live in one table — audit/swap them for US EPA AQI if you prefer.
- OpenAQ "latest" can lag and isn't strictly the newest ingested value (their
  docs note out-of-order ingestion); fine for a live dashboard, worth a footnote.
- v1/v2 endpoints are dead (HTTP 410). This is v3-only.
```
