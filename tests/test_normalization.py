"""Test normalization modes (v5 Measurement Contract consistency)."""
import math
import pytest

from evidence.normalization import (
    NormalizationError,
    bounded,
    cluster,
    minmax,
    normalize,
    normalize_series,
    zscore,
)


def test_zscore_basic():
    assert math.isclose(zscore(10, mean=5, std=5), 1.0)
    assert math.isclose(zscore(0, mean=5, std=5), -1.0)


def test_zscore_zero_std_returns_zero():
    assert zscore(7, mean=7, std=0) == 0.0


def test_minmax():
    assert minmax(5, lo=0, hi=10) == 0.5
    assert minmax(10, lo=0, hi=10) == 1.0
    assert minmax(0, lo=0, hi=10) == 0.0


def test_minmax_degenerate():
    assert minmax(5, lo=5, hi=5) == 0.0


def test_bounded_clips():
    assert bounded(-0.5) == 0.0
    assert bounded(0.5) == 0.5
    assert bounded(1.5) == 1.0


def test_cluster_matches_bounded():
    assert cluster(2.0) == 1.0
    assert cluster(0.3) == 0.3


def test_normalize_dispatch():
    assert math.isclose(normalize(10, "zscore", mean=5, std=5), 1.0)
    assert math.isclose(normalize(5, "minmax", lo=0, hi=10), 0.5)
    assert normalize(1.5, "bounded") == 1.0
    assert normalize(2.0, "cluster") == 1.0


def test_normalize_unknown_mode_raises():
    with pytest.raises(NormalizationError):
        normalize(1.0, "bogus")


def test_normalize_series_zscore():
    res = normalize_series([1.0, 2.0, 3.0], "zscore")
    assert len(res) == 3
    assert math.isclose(sum(res), 0.0, abs_tol=1e-9)  # centered


def test_normalize_series_minmax():
    res = normalize_series([10, 20, 30], "minmax")
    assert res == [0.0, 0.5, 1.0]


def test_normalize_series_bounded():
    res = normalize_series([-1.0, 0.5, 2.0], "bounded")
    assert res == [0.0, 0.5, 1.0]


def test_normalize_series_empty():
    assert normalize_series([], "zscore") == []


def test_normalize_series_unknown_raises():
    with pytest.raises(NormalizationError):
        normalize_series([1, 2], "bogus")
