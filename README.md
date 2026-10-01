# Paris Air Quality

[![CI](https://github.com/Clement-tc/paris-air-quality/actions/workflows/ci.yml/badge.svg)](https://github.com/Clement-tc/paris-air-quality/actions/workflows/ci.yml)

**Live demo:** [paris-air-quality-two.vercel.app](https://paris-air-quality-two.vercel.app)
**API:** [paris-air-quality-api.onrender.com/docs](https://paris-air-quality-api.onrender.com/docs)

A full pipeline from raw sensor data to a deployed prediction: real-time air
quality ingestion from [OpenAQ](https://openaq.org), a 3D interactive map
(deck.gl), and a scikit-learn model predicting whether NO2 will cross into
degraded air quality in the next 24h — all served live.

## What's actually here

- **ETL pipeline** (FastAPI + Postgres) — pulls Paris sensor readings from the
  OpenAQ v3 API, validates them (Pydantic), classifies severity against the
  EEA European Air Quality Index, and stores history idempotently.
- **3D map** (Next.js + deck.gl + MapLibre) — three modes: Air Quality,
  Temperature, and Prediction NO2. Arrondissement zones are colour-coded by
  **interpolating real sensors (IDW)**, not a coarse regional model — see
  [Honest caveats](#honest-caveats-and-decisions-worth-defending) for why.
- **NO2 exceedance forecast** — a `HistGradientBoostingClassifier` predicts
  the probability that NO2 crosses 40 µg/m³ (the EEA Good→Fair boundary) in
  the next 24h, per station, served live via `/api/forecast`. See
  [ml/train_no2_exceedance.py](ml/train_no2_exceedance.py) for the full
  methodology, validation, and the honest results.

## Architecture

```
OpenAQ v3 API ──┐                          ┌─▶ Postgres (Neon)
                ├─▶ backend (FastAPI) ──────┤
Open-Meteo ─────┘        │                  └─▶ scikit-learn model (joblib)
                         │
                         ▼
              frontend (Next.js/Vercel) ──▶ deck.gl 3D map
```

- **Backend** → Render (`backend/`)
- **Frontend** → Vercel (`frontend/`)
- **Database** → Neon Postgres (persistent — see caveats below on why this
  matters more than it sounds)
- **ML training** → offline, local (`ml/`), artifact committed to
  `backend/models/`
- **CI** → GitHub Actions on every push: backend tests (pytest + an offline
  pipeline test) and frontend (typecheck, lint, build)

## Run it locally

**Backend:**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# paste your OpenAQ key (free: https://explore.openaq.org)
# DATABASE_URL defaults to local SQLite if you don't set one

uvicorn main:app --reload
```

```powershell
# prove the ETL works without the network first
python test_offline.py
pytest

curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/admin/refresh
curl "http://127.0.0.1:8000/api/air?parameter=no2"
curl http://127.0.0.1:8000/api/forecast
```

Interactive API docs: http://127.0.0.1:8000/docs

**Frontend:**
```powershell
cd frontend
npm install
npm run dev
# http://localhost:3000, reading from NEXT_PUBLIC_API_URL (defaults to localhost:8000)
```

## How ingestion works

OpenAQ v3 splits what you need across two calls, and the join between them is
the heart of the pipeline:

1. `GET /locations?bbox=<paris>` — stations + their **sensors**. The only
   place that says *sensor 11002 measures NO2 in µg/m³*.
2. `GET /locations/{id}/latest` — latest values, but each row is just a
   `value` + a `sensorsId`. No pollutant name.

`pipeline.transform()` builds a `sensorsId → parameter/units` map from (1),
joins the latest values from (2) onto it, enriches with severity
(`aqi.classify`), and pushes through a quality gate before storage.

```
fetch ─▶ validate (Pydantic) ─▶ join + enrich ─▶ quality gate ─▶ store (idempotent)
```

A one-shot backfill (`POST /admin/backfill_history`) pulls real recent hours
from OpenAQ's live measurement API (not the S3 archive export, which lags
~4-5 days) — used to seed a freshly deployed instance's history immediately
instead of waiting ~25h for the forecast to have enough data.

## The ML: predicting NO2 exceedance

Full writeup and code: [ml/train_no2_exceedance.py](ml/train_no2_exceedance.py).
Short version, because the reasoning matters more than the score:

- **Target**: not the official EEA "Poor" band (>120 µg/m³) — it occurs 19
  times in a full year across all Paris stations (0.01%), too rare to learn
  from. Recalibrated to the Good→Fair boundary (>40 µg/m³, ~14% positive
  rate), which is still a real, meaningful degradation signal and
  statistically workable.
- **Validation**: walk-forward (`TimeSeriesSplit`), never a random split —
  caught a real bug where sorting by `(station, time)` instead of time alone
  made "temporal" folds actually slice by station.
- **Honest finding**: the model (ROC-AUC ~0.85) doesn't clearly beat a naive
  persistence baseline ("NO2 is doing X now, assume it still is in 24h") on
  F1. NO2 has strong short-term autocorrelation — a legitimate, useful result
  to know, not a failure to hide. The app exposes the raw probability rather
  than forcing an unstable decision threshold.
- **Features**: NO2 lags (1h/3h/6h/24h) + rolling mean, calendar (local Paris
  time, French holidays), weather (temperature, humidity, wind — encoded as
  sin/cos for circularity, pressure, precipitation, cloud cover), station
  identity.

## Honest caveats and decisions worth defending

- **CAMS (11km model) vs real sensors (IDW)**: the map originally coloured
  arrondissements using Open-Meteo's CAMS air-quality model. It's too coarse
  for a city the size of Paris — 18/20 arrondissements came out with
  near-identical values (spread of 0.67/100). Switched to inverse-distance-
  weighted interpolation of the real sensors, which gives a spread of 24.5 —
  this is why the map shows real intra-city variation.
- **Render's free-tier disk is ephemeral** — it resets on every redeploy.
  Fixed properly by moving to persistent Postgres (Neon), not by working
  around it. The backfill endpoint exists for the very first deploy, not as
  an ongoing crutch.
- **N+1 query bug**: `/api/air` took 5-6s after the Postgres switch because a
  lazy-loaded relationship fired one query per row (60-80 extra round trips
  to Neon). Invisible on local SQLite (near-zero per-query latency). Fixed
  with `selectinload`; verified 5.1s → 0.3s against the real database before
  deploying.
- **Open-Meteo rate limits Render's shared IP** independently of this app's
  own traffic (a free-tier-hosting-platform problem, not ours specifically).
  The frontend fetches weather directly from the browser where it can
  (bypassing the shared IP entirely); the backend's forecast endpoint
  degrades gracefully to missing-weather rather than failing outright.
- **GitHub Actions `schedule` triggers are best-effort** — observed one run
  in 5 hours instead of 5. Not relied on for anything the app's correctness
  depends on.
- EEA bands in `aqi.py` are the published European AQI thresholds. They live
  in one table — swap for US EPA AQI if needed.

## Project structure

| Path | Role |
|---|---|
| `backend/main.py` | FastAPI surface: `/api/air`, `/api/weather`, `/api/forecast`, `/admin/*` |
| `backend/pipeline.py` | ETL: transform (pure), quality gate, idempotent ingest |
| `backend/forecast.py` | Live feature computation + model inference for `/api/forecast` |
| `backend/aqi.py` | EEA index bands → category + colour + 0-100 `sub_index` |
| `backend/openaq_client.py` / `openmeteo_client.py` | API clients |
| `backend/test_*.py` | pytest suite + offline pipeline test |
| `ml/train_no2_exceedance.py` | Model training, validation, methodology notes |
| `ml/backfill_openaq.py` / `backfill_weather.py` | Historical data backfill for training |
| `frontend/app/components/AirMap.tsx` | The deck.gl map, all three modes |
| `frontend/app/lib/arrondissements.ts` / `forecastZones.ts` | IDW interpolation onto zones |
| `.github/workflows/` | CI (tests/build) + hourly data refresh cron |
