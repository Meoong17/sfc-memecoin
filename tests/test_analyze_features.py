"""Test feature-analysis helpers (scripts/analyze_features.py)."""
import pytest

from scripts.analyze_features import parse_note, pearson, spearman, pearson_ci, split_corr


def test_parse_note_types():
    note = "a=1; b=2.5; c=True; d=False; e=None; f=0; name=abc; g=;"
    out = parse_note(note)
    assert out["a"] == 1.0
    assert out["b"] == 2.5
    assert out["c"] == 1.0
    assert out["d"] == 0.0
    assert out["e"] == 0.0
    assert out["f"] == 0.0
    # non-numeric dropped; empty value -> 0.0 (consistent with None/blank)
    assert "name" not in out
    assert out["g"] == 0.0


def test_parse_note_empty():
    assert parse_note("") == {}
    assert parse_note(None) == {}


def test_pearson_perfect_positive():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [2.0, 4.0, 6.0, 8.0, 10.0]
    assert pearson(xs, ys) == pytest.approx(1.0)


def test_pearson_negative():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [5.0, 4.0, 3.0, 2.0, 1.0]
    assert pearson(xs, ys) == pytest.approx(-1.0)


def test_pearson_short():
    assert pearson([1.0], [2.0]) == 0.0


def test_spearman_matches_pearson_on_monotonic():
    # monotonic but non-linear: rank correlation == 1
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    ys = [1.0, 4.0, 9.0, 16.0, 25.0]  # squared
    assert spearman(xs, ys) == pytest.approx(1.0)


def test_spearman_outlier_suppression():
    # a single extreme outlier inflates Pearson but not Spearman
    xs = [1.0, 2.0, 3.0, 4.0, 1000.0]
    ys = [2.0, 4.0, 6.0, 8.0, 2000000.0]
    assert pearson(xs, ys) > 0.9          # Pearson pulled by outlier
    assert spearman(xs, ys) == pytest.approx(1.0)  # rank unaffected


def test_pearson_ci_includes_zero_when_noisy():
    import random
    random.seed(42)
    xs = [random.gauss(0, 1) for _ in range(60)]
    ys = [random.gauss(0, 1) for _ in range(60)]
    c, lo, hi = pearson_ci(xs, ys, n_boot=300, seed=0)
    assert lo <= c <= hi
    # 60 iid gaussians: true corr ~0, so CI should straddle 0
    assert lo < 0 < hi


def test_split_corr_contiguous():
    # correlated first chunk, anti-correlated second -> both returned
    xs = [1.0, 2.0, 3.0, 4.0, 5.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    ys = [1.0, 2.0, 3.0, 4.0, 5.0, 5.0, 4.0, 3.0, 2.0, 1.0]
    chunks = split_corr(xs, ys, n_split=2, seed=0)
    assert len(chunks) == 2
    assert chunks[0] == pytest.approx(1.0)
    assert chunks[1] == pytest.approx(1.0)


def test_split_corr_short_segments_dropped():
    xs = [1.0, 2.0]
    ys = [1.0, 2.0]
    # each of 5 chunks has <3 points -> all dropped
    assert split_corr(xs, ys, n_split=5, seed=0) == []
