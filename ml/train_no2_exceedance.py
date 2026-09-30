"""
First draft: predict whether NO2 will cross into "degraded" air quality
(> 40 ug/m3, the EEA Good/Fair boundary) 24h from now, per Paris station.

WHY THIS TARGET (not the official "Poor" EEA band):
Empirically, "Poor" (>120 ug/m3) occurs only 19 times in a full year across
all stations (0.01%) -- far too rare to learn from. ">40 ug/m3" occurs ~14%
of the time (17.7k rows), which is a workable class balance. See conversation
notes / README for the full reasoning.

WHY WEATHER IS A FEATURE, NOT THE TARGET:
Wind disperses pollutants, temperature/sunlight drive ozone chemistry,
pressure and humidity affect dispersion. The target is pollution; weather is
an explanatory input.

Run: .venv-wsl/bin/python ml/train_no2_exceedance.py
"""
from pathlib import Path

import holidays
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report, f1_score, precision_recall_curve,
    precision_score, recall_score, roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

N_CV_FOLDS = 5
MODEL_OUT_PATH = Path(__file__).parent.parent / "backend" / "models" / "no2_exceedance.joblib"


def balanced_sample_weight(y: pd.Series) -> np.ndarray:
    """Same formula as sklearn's class_weight='balanced', as sample_weight --
    HistGradientBoostingClassifier has no class_weight param, unlike
    LogisticRegression, so this is how we get equivalent imbalance handling."""
    counts = y.value_counts()
    n_samples, n_classes = len(y), len(counts)
    weight_per_class = n_samples / (n_classes * counts)
    return y.map(weight_per_class).to_numpy()

# ---------------------------------------------------------------------------
# Config -- the decisions we made together
# ---------------------------------------------------------------------------
THRESHOLD_UG_M3 = 40.0   # NO2 "Good -> Fair or worse" boundary (EEA band)
HORIZON_HOURS = 24       # predict this far ahead
TEST_DAYS = 60           # most recent N days held out, strictly after train

OPENAQ_PATH = "data/openaq_history_20250627_20260626.parquet"
WEATHER_PATH = "data/weather_history_20250627_20260626.parquet"


# ---------------------------------------------------------------------------
# 1. Load NO2 and put it on a continuous hourly grid per station.
#
# Why resample instead of using raw rows: real sensors have gaps (outages,
# maintenance). If we just shifted rows by 24 positions, a gap would silently
# pair a reading with something that isn't actually 24h later. Resampling to
# an explicit hourly index makes "shift by 24" mean "24 hours later", with
# real gaps becoming NaN instead of silently wrong alignment.
# ---------------------------------------------------------------------------
def load_no2() -> pd.DataFrame:
    df = pd.read_parquet(OPENAQ_PATH)
    no2 = df[df["parameter"] == "no2"].copy()
    no2["datetime"] = pd.to_datetime(no2["datetime"], utc=True)
    # a station could in theory have >1 NO2 sensor; average if so
    no2 = no2.groupby(["location_id", "datetime"], as_index=False)["value"].mean()

    grids = []
    for loc_id, g in no2.groupby("location_id"):
        g = g.set_index("datetime").sort_index()
        full_index = pd.date_range(g.index.min(), g.index.max(), freq="h", tz="UTC")
        g = g.reindex(full_index)
        g["location_id"] = loc_id
        g.index.name = "datetime"
        grids.append(g)
    out = pd.concat(grids).reset_index().rename(columns={"value": "no2"})
    return out


# ---------------------------------------------------------------------------
# 2. Join weather (already hourly, one row per station per hour).
# ---------------------------------------------------------------------------
def load_weather() -> pd.DataFrame:
    w = pd.read_parquet(WEATHER_PATH)
    w["location_id"] = w["location_id"].astype(int)
    w["datetime"] = pd.to_datetime(w["datetime"], utc=True)
    return w


# ---------------------------------------------------------------------------
# 3. Feature engineering.
#
# Calendar features use LOCAL time (Europe/Paris), not UTC: NO2 has strong
# rush-hour patterns tied to when people actually commute, which is a local-
# clock phenomenon, not a UTC one.
# ---------------------------------------------------------------------------
FR_HOLIDAYS = holidays.France(years=range(2024, 2028))


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["location_id", "datetime"]).copy()

    local = df["datetime"].dt.tz_convert("Europe/Paris")
    df["hour"] = local.dt.hour
    df["dayofweek"] = local.dt.dayofweek
    df["month"] = local.dt.month
    df["is_weekend"] = (local.dt.dayofweek >= 5).astype(int)
    # Traffic (a major NO2 driver) drops on public holidays regardless of
    # weekday -- a Tuesday that's a bank holiday behaves like a Sunday.
    df["is_holiday"] = local.dt.date.map(lambda d: d in FR_HOLIDAYS).astype(int)

    # Wind direction is a compass angle (0-360 deg): 359 deg and 1 deg are
    # nearly the same direction but far apart as raw numbers. sin/cos gives
    # the model a representation where "close in angle" means "close in value".
    wind_rad = np.deg2rad(df["wind_direction_10m"])
    df["wind_dir_sin"] = np.sin(wind_rad)
    df["wind_dir_cos"] = np.cos(wind_rad)

    g = df.groupby("location_id")["no2"]
    df["no2_lag1h"] = g.shift(1)
    df["no2_lag3h"] = g.shift(3)
    df["no2_lag6h"] = g.shift(6)
    df["no2_lag24h"] = g.shift(24)
    df["no2_roll24h_mean"] = g.transform(lambda s: s.shift(1).rolling(24, min_periods=6).mean())

    # target: NO2 24h from now, at THIS station's own future row
    df["no2_future"] = g.shift(-HORIZON_HOURS)
    df["target"] = (df["no2_future"] > THRESHOLD_UG_M3).astype("Int64")
    # if the future value itself is missing (gap or end of series), we can't
    # know the true label -- drop those rows rather than guessing
    df.loc[df["no2_future"].isna(), "target"] = pd.NA

    return df


def main() -> None:
    print("Loading NO2 (resampled to continuous hourly grid per station)...")
    no2 = load_no2()
    print(f"  {len(no2):,} station-hours, {no2['location_id'].nunique()} stations")

    print("Loading weather...")
    weather = load_weather()

    print("Joining...")
    df = no2.merge(weather, on=["location_id", "datetime"], how="left")

    print("Building features + target...")
    df = build_features(df)

    before = len(df)
    df = df.dropna(subset=["target"])
    print(f"  dropped {before - len(df):,} rows with no valid target (dataset edges)")
    df["target"] = df["target"].astype(int)

    # build_features sorted by (location_id, datetime) so the per-station lag
    # shifts were correct -- but that leaves rows grouped by STATION, not by
    # time. TimeSeriesSplit assumes chronological order across the whole
    # array, so we must re-sort globally by datetime now that the lag/target
    # columns are already safely computed. Skipping this makes each CV "fold"
    # a slice of stations, not a slice of time -- a walk-forward split that
    # doesn't actually walk forward.
    df = df.sort_values("datetime").reset_index(drop=True)

    print(f"\nFinal dataset: {len(df):,} rows, {df['location_id'].nunique()} stations")
    print(f"Positive rate (NO2 > {THRESHOLD_UG_M3} in {HORIZON_HOURS}h): {df['target'].mean():.1%}")

    # location_id joins in as a station identity feature -- a roadside
    # station near the peripherique runs structurally hotter than a quiet
    # residential one, and the model should know which station it's looking
    # at. Cast globally (before the split) so train/test share the same
    # category codes.
    df["location_id"] = df["location_id"].astype("category")

    # -----------------------------------------------------------------
    # Strict temporal split: test = last TEST_DAYS, train = everything
    # before that. No shuffling -- the model must never see the future.
    # -----------------------------------------------------------------
    cutoff = df["datetime"].max() - pd.Timedelta(days=TEST_DAYS)
    train = df[df["datetime"] < cutoff]
    test = df[df["datetime"] >= cutoff]
    print(f"\nTrain: {len(train):,} rows (< {cutoff.date()})")
    print(f"Test:  {len(test):,} rows (>= {cutoff.date()})")
    print(f"Train positive rate: {train['target'].mean():.1%}  |  Test positive rate: {test['target'].mean():.1%}")

    numeric_cols = [
        "hour", "dayofweek", "month", "is_weekend", "is_holiday",
        "no2_lag1h", "no2_lag3h", "no2_lag6h", "no2_lag24h", "no2_roll24h_mean",
        "temperature_2m", "relative_humidity_2m", "wind_speed_10m",
        "wind_dir_sin", "wind_dir_cos", "precipitation", "surface_pressure", "cloud_cover",
    ]
    feature_cols = numeric_cols + ["location_id"]
    X_train, y_train = train[feature_cols].reset_index(drop=True), train["target"].reset_index(drop=True)
    X_test, y_test = test[feature_cols], test["target"]

    # -----------------------------------------------------------------
    # TimeSeriesSplit over TRAIN only: walk-forward folds, each trained on
    # the past and validated on the slice right after it. This does two
    # things at once:
    #   1. Surfaces whether performance drifts across the year (season) --
    #      a single train/test cut can't tell real drift from a fluke split.
    #   2. Produces out-of-fold probabilities we can use to pick a decision
    #      threshold WITHOUT ever looking at the real test set.
    # -----------------------------------------------------------------
    print(f"\n--- {N_CV_FOLDS}-fold walk-forward cross-validation on TRAIN ---")
    tscv = TimeSeriesSplit(n_splits=N_CV_FOLDS)
    oof_proba = np.full(len(X_train), np.nan)
    for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train), start=1):
        # Tried sample_weight="balanced"-equivalent here too: it hurt F1
        # (0.42 vs 0.45) by over-correcting on top of the threshold tuning
        # below -- the two techniques compete rather than stack. Dropped it.
        model = HistGradientBoostingClassifier(random_state=42, categorical_features=["location_id"])
        model.fit(X_train.iloc[tr_idx], y_train.iloc[tr_idx])
        proba = model.predict_proba(X_train.iloc[val_idx])[:, 1]
        oof_proba[val_idx] = proba
        auc = roc_auc_score(y_train.iloc[val_idx], proba)
        pos_rate = y_train.iloc[val_idx].mean()
        val_dates = train["datetime"].reset_index(drop=True).iloc[val_idx]
        print(
            f"  fold {fold}: {val_dates.min().date()} -> {val_dates.max().date()}  "
            f"n={len(val_idx):,}  positive_rate={pos_rate:.1%}  AUC={auc:.3f}"
        )

    # -----------------------------------------------------------------
    # Pick the decision threshold that maximises F1 on out-of-fold
    # predictions (fold 1's training slice has no OOF prediction -- drop it).
    # -----------------------------------------------------------------
    valid = ~np.isnan(oof_proba)
    precisions, recalls, thresholds = precision_recall_curve(y_train[valid], oof_proba[valid])
    f1s = 2 * precisions * recalls / (precisions + recalls + 1e-9)
    best_i = np.nanargmax(f1s[:-1])  # thresholds has len(precisions)-1 entries
    best_threshold = thresholds[best_i]
    print(f"\nTuned threshold (max F1 on OOF train predictions): {best_threshold:.3f}")
    print(f"  (default would be 0.5; OOF F1 at tuned threshold: {f1s[best_i]:.3f})")

    # -----------------------------------------------------------------
    # Refit on the FULL train set, evaluate once on the true held-out test.
    # -----------------------------------------------------------------
    results, probas = {}, {}

    results["Persistence (naive)"] = (test["no2"] > THRESHOLD_UG_M3).astype(int)

    logreg = Pipeline([
        ("prep", ColumnTransformer([
            ("num", Pipeline([
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
            ]), numeric_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["location_id"]),
        ])),
        ("clf", LogisticRegression(max_iter=1000, class_weight="balanced")),
    ])
    logreg.fit(X_train, y_train)
    probas["Logistic Regression"] = logreg.predict_proba(X_test)[:, 1]
    results["Logistic Regression"] = logreg.predict(X_test)

    hgb = HistGradientBoostingClassifier(random_state=42, categorical_features=["location_id"])
    hgb.fit(X_train, y_train)
    probas["HistGradientBoosting"] = hgb.predict_proba(X_test)[:, 1]
    results["HistGradientBoosting"] = hgb.predict(X_test)  # default 0.5 threshold
    results["HistGradientBoosting (tuned threshold)"] = (probas["HistGradientBoosting"] >= best_threshold).astype(int)

    # -------------------- Compare --------------------
    print("\n" + "=" * 78)
    print(f"{'Model':<38} {'Precision':>10} {'Recall':>10} {'F1':>10} {'ROC-AUC':>8}")
    print("=" * 78)
    for name, pred in results.items():
        p = precision_score(y_test, pred, zero_division=0)
        r = recall_score(y_test, pred, zero_division=0)
        f1 = f1_score(y_test, pred, zero_division=0)
        auc_key = name.replace(" (tuned threshold)", "")
        auc = roc_auc_score(y_test, probas[auc_key]) if auc_key in probas else float("nan")
        auc_str = f"{auc:.3f}" if not np.isnan(auc) else "n/a"
        print(f"{name:<38} {p:>10.3f} {r:>10.3f} {f1:>10.3f} {auc_str:>8}")
    print("=" * 78)

    print("\nHistGradientBoosting (tuned threshold) full report:")
    print(classification_report(
        y_test, results["HistGradientBoosting (tuned threshold)"],
        target_names=["OK", "Exceeds 40ug/m3"],
    ))

    # -----------------------------------------------------------------
    # Final production model: refit on ALL available data (train+test).
    # The held-out test set already did its job above (honest evaluation);
    # withholding it from the deployed model would just throw away signal.
    # No custom threshold is baked in -- the app serves predict_proba
    # directly (see conversation: threshold tuning proved unstable between
    # CV and test, so we expose a calibrated-ish risk % instead of a
    # fragile hard cutoff).
    # -----------------------------------------------------------------
    final_model = HistGradientBoostingClassifier(random_state=42, categorical_features=["location_id"])
    final_model.fit(df[feature_cols], df["target"])

    MODEL_OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "model": final_model,
        "numeric_cols": numeric_cols,
        "feature_cols": feature_cols,
        "threshold_ug_m3": THRESHOLD_UG_M3,
        "horizon_hours": HORIZON_HOURS,
        "known_station_ids": sorted(int(c) for c in df["location_id"].cat.categories),
    }, MODEL_OUT_PATH)
    print(f"\nSaved production model -> {MODEL_OUT_PATH}")


if __name__ == "__main__":
    main()
