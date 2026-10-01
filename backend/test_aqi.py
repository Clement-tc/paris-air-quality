"""
Unit tests for aqi.classify -- the EEA severity mapping every reading and
every forecast risk colour depends on. Pure function, no DB/network needed.

Run: pytest test_aqi.py
"""
import aqi


def test_good_band_no2():
    sev = aqi.classify("no2", 20.0, "µg/m³")
    assert sev.category_index == 1
    assert sev.category_label == "Good"


def test_band_boundary_is_inclusive():
    # 40 is the EEA Good/Fair boundary -- aqi.py's loop uses `<=`, so the
    # boundary value itself belongs to the lower (better) band.
    sev = aqi.classify("no2", 40.0, "µg/m³")
    assert sev.category_label == "Good"
    sev_just_over = aqi.classify("no2", 40.1, "µg/m³")
    assert sev_just_over.category_label == "Fair"


def test_above_top_ceiling_clamps_to_worst_band():
    sev = aqi.classify("no2", 5000.0, "µg/m³")
    assert sev.category_index == 6
    assert sev.category_label == "Extremely poor"
    assert sev.sub_index == 100.0


def test_negative_value_is_not_categorised():
    sev = aqi.classify("no2", -4.0, "µg/m³")
    assert sev.category_index is None
    assert sev.sub_index is None


def test_unknown_parameter_is_not_categorised():
    # co isn't in the EEA index (see aqi.py docstring) -- stored but uncategorised.
    sev = aqi.classify("co", 500.0, "µg/m³")
    assert sev.category_index is None


def test_wrong_units_are_not_categorised():
    # ppm isn't comparable to the EEA µg/m3 bands -- must not silently miscategorise.
    sev = aqi.classify("no2", 20.0, "ppm")
    assert sev.category_index is None


def test_micro_sign_variants_are_both_accepted():
    # µg/m³ (U+00B5) and μg/m³ (U+03BC) look identical but are different
    # unicode code points -- real-world payloads use both.
    sev_micro = aqi.classify("no2", 20.0, "µg/m³")
    sev_mu = aqi.classify("no2", 20.0, "μg/m³")
    assert sev_micro.category_label == sev_mu.category_label == "Good"


def test_sub_index_increases_monotonically_within_paris_range():
    # sub_index drives column height / marker intensity -- a higher reading
    # must never produce a lower score, across the full observed range.
    values = [5, 15, 25, 35, 50, 70, 100, 150, 250, 400]
    scores = [aqi.classify("no2", v, "µg/m³").sub_index for v in values]
    assert scores == sorted(scores)
