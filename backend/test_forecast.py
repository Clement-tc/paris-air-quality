"""
Unit tests for forecast.py's feature-building logic -- specifically the
staleness/depth checks, which caused two real bugs discovered the hard way
while verifying this in production (see commit history):
  1. naive vs timezone-aware datetime mixing (TypeError on subtraction)
  2. a 2h staleness threshold that was tighter than OpenAQ's own real
     reporting lag (~2h45 observed), flagging perfectly good stations as
     stale

No DB/network needed -- Reading is faked with a lightweight stand-in that
only needs the two attributes _station_features actually reads.

Run: pytest test_forecast.py
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

import forecast


@dataclass
class FakeReading:
    datetime_utc: datetime
    value: float


def hours_ago(now: datetime, h: float) -> datetime:
    return now - timedelta(hours=h)


def test_no_rows_reports_no_rows_error():
    result = forecast._station_features([], now=datetime(2026, 1, 1, 12, 0))
    assert result == {"_error": "no_rows"}


def test_stale_station_is_rejected():
    # Latest reading is older than STALE_AFTER_HOURS -- this is the exact
    # scenario that broke with a too-tight 2h threshold in production.
    now = datetime(2026, 1, 2, 0, 0)
    # push every reading further back than the allowed staleness window
    rows = [FakeReading(hours_ago(now, h + 10), 20.0) for h in range(30, 0, -1)]
    result = forecast._station_features(rows, now=now)
    assert result["_error"] == "stale"


def test_fresh_but_shallow_history_is_insufficient():
    # Fresh (not stale) but spans less than MIN_HISTORY_HOURS -- no reliable
    # lag24h/rolling24h feature can exist yet.
    now = datetime(2026, 1, 1, 12, 0)
    rows = [FakeReading(hours_ago(now, h), 20.0) for h in range(10, 0, -1)]
    result = forecast._station_features(rows, now=now)
    assert result["_error"] == "insufficient_depth"


def test_sufficient_fresh_history_produces_real_features():
    now = datetime(2026, 1, 2, 0, 0)
    # one reading per hour for the last 30h, value = hours-ago (so lag1h=1, lag3h=3, ...)
    rows = [FakeReading(hours_ago(now, h), float(h)) for h in range(30, -1, -1)]
    result = forecast._station_features(rows, now=now)
    assert "_error" not in result
    assert result["no2_lag1h"] == 1.0
    assert result["no2_lag3h"] == 3.0
    assert result["no2_lag6h"] == 6.0
    assert result["no2_lag24h"] == 24.0
    assert result["no2_roll24h_mean"] is not None


def test_naive_datetimes_throughout_do_not_raise():
    # This codebase stores naive-but-UTC datetimes everywhere (see
    # pipeline.py). Mixing a timezone-aware `now` in here was the exact bug
    # that crashed compute_forecasts the first time it ran against real data.
    now = datetime(2026, 1, 2, 0, 0)  # naive, matches production convention
    rows = [FakeReading(hours_ago(now, h), 20.0) for h in range(30, 0, -1)]
    result = forecast._station_features(rows, now=now)  # must not raise
    assert "_error" not in result


def test_nearest_value_within_tolerance():
    base = datetime(2026, 1, 1, 12, 0)
    rows = [FakeReading(base, 42.0)]
    assert forecast._nearest_value(rows, base + timedelta(minutes=10)) == 42.0


def test_nearest_value_outside_tolerance_returns_none():
    base = datetime(2026, 1, 1, 12, 0)
    rows = [FakeReading(base, 42.0)]
    assert forecast._nearest_value(rows, base + timedelta(hours=5)) is None
