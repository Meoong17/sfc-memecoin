"""Test backtest labeler + walk-forward skeleton."""
from datetime import datetime, timedelta

import pytest

from backtest.labeler import (
    LabeledDataset,
    LabeledToken,
    Outcome,
    classify_outcome,
)
from backtest.walk_forward import walk_forward


def _tok(token, outcome, launch, **kw):
    return LabeledToken(token=token, chain="solana", launch_ts=launch,
                        outcome=outcome, **kw)


def _t0(i):
    return datetime(2026, 1, 1) + timedelta(days=i)


def test_classify_rugged_on_lp_removal():
    assert classify_outcome(lp_removed=True, max_drawdown_pct=-10.0,
                            peak_return_pct=500.0, days_observed=20) == Outcome.RUGGED


def test_classify_rugged_on_deep_drawdown():
    assert classify_outcome(lp_removed=False, max_drawdown_pct=-70.0,
                            peak_return_pct=400.0, days_observed=20) == Outcome.RUGGED


def test_classify_pumped_sustained():
    assert classify_outcome(lp_removed=False, max_drawdown_pct=-20.0,
                            peak_return_pct=400.0, days_observed=14) == Outcome.PUMPED


def test_classify_survived_default():
    assert classify_outcome(lp_removed=False, max_drawdown_pct=-20.0,
                            peak_return_pct=50.0, days_observed=20) == Outcome.SURVIVED


def test_classify_pump_not_sustained_is_not_pumped():
    # peak high but observed only 2 days -> not "pumped", fall through to survived
    assert classify_outcome(lp_removed=False, max_drawdown_pct=-10.0,
                            peak_return_pct=500.0, days_observed=2) == Outcome.SURVIVED


def test_dataset_counts():
    ds = LabeledDataset()
    ds.add(_tok("A", Outcome.RUGGED, _t0(0)))
    ds.add(_tok("B", Outcome.SURVIVED, _t0(1)))
    ds.add(_tok("C", Outcome.PUMPED, _t0(2)))
    assert ds.counts() == {"rugged": 1, "survived": 1, "pumped": 1}
    assert len(ds.by_outcome(Outcome.RUGGED)) == 1


def test_walk_forward_produces_folds():
    ds = LabeledDataset()
    for i in range(50):
        ds.add(_tok(f"T{i}", Outcome.SURVIVED if i % 2 == 0 else Outcome.RUGGED, _t0(i)))
    res = walk_forward(ds, lambda tr, te: 0.7, min_train=20, step=10, horizon=10)
    assert len(res.results) >= 1
    assert res.mean_score == pytest.approx(0.7, abs=1e-9)


def test_walk_forward_too_few_samples():
    ds = LabeledDataset()
    for i in range(10):
        ds.add(_tok(f"T{i}", Outcome.SURVIVED, _t0(i)))
    res = walk_forward(ds, lambda tr, te: 0.7, min_train=20)
    assert res.results == []
    assert res.mean_score == 0.0


def test_walk_forward_no_lookahead_structure():
    """Train samples must always predate test samples."""
    ds = LabeledDataset()
    for i in range(45):
        ds.add(_tok(f"T{i}", Outcome.SURVIVED if i % 2 == 0 else Outcome.RUGGED, _t0(i)))
    seen_splits = []

    def eval_split(train, test):
        train_ts = [t.launch_ts for t in train]
        test_ts = [t.launch_ts for t in test]
        assert max(train_ts) < min(test_ts)  # no look-ahead
        seen_splits.append(1)
        return 0.5

    walk_forward(ds, eval_split, min_train=20, step=10, horizon=10)
    assert seen_splits  # evaluator actually ran
