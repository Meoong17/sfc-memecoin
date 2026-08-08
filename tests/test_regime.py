"""Test Regime Detection Engine (Phase 4)."""
import pytest

from engines.regime import (
    SeriesInput, RegimeEngine, detect_change_point, ewma, rolling_z,
)


eng = RegimeEngine()


def test_rolling_z_centers_last_point():
    series = [10.0] * 20 + [15.0]  # last point above baseline
    z = rolling_z(series, window=20)[-1]
    assert z > 0


def test_rolling_z_degenerate_returns_zero():
    assert rolling_z([5.0, 5.0, 5.0])[-1] == 0.0


def test_ewma_smooths():
    out = ewma([1.0, 2.0, 3.0, 4.0], alpha=0.5)
    assert len(out) == 4
    assert out[0] == pytest.approx(1.0)
    assert out[-1] > 1.0


def test_change_point_detection_true():
    series = [1.0] * 20 + [5.0] * 10
    assert detect_change_point(series, window=10, thresh=2.0)


def test_change_point_no_shift():
    series = [1.0] * 30
    assert not detect_change_point(series, window=10)


def test_change_point_too_short():
    assert not detect_change_point([1.0, 2.0, 3.0], window=10)


def test_breakout_regime():
    # steady rise then acceleration -> high z -> BREAKOUT/EXPANSION
    series = list(range(0, 60))
    r = eng.analyze("TOK", [SeriesInput("price", series, high_is_bullish=True)])
    assert r.regime in ("BREAKOUT", "EXPANSION", "EUPHORIA")
    assert r.composite_z > 0


def test_collapse_regime_inverted_risk_dimension():
    # liquidity stress rising sharply is bearish; high_is_bullish=False inverts
    stress = [0.1] * 30 + [round(0.1 + 0.04 * i, 2) for i in range(20)]  # rising ramp
    r = eng.analyze("TOK", [SeriesInput("liq_stress", stress, high_is_bullish=False)])
    assert r.regime in ("DISTRIBUTION", "COLLAPSE")
    assert r.composite_z < 0


def test_multivariate_aggregation():
    r = eng.analyze("TOK", [
        SeriesInput("price", list(range(30, 90)), high_is_bullish=True),
        SeriesInput("volume", list(range(40, 100)), high_is_bullish=True),
    ])
    assert "price" in r.per_dimension and "volume" in r.per_dimension


def test_summary_shape():
    r = eng.analyze("TOK", [SeriesInput("price", list(range(20)) )])
    s = r.summary()
    for k in ["token", "regime", "composite_z", "change_point", "per_dimension"]:
        assert k in s
