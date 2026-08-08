#!/usr/bin/env python3
"""Walk-forward on a SAVED labeled dataset (no live fetch).

Use this instead of scripts/calibrate.py when the dataset already exists —
calibrate.py re-fetches live data every run, which makes the walk-forward
verdict not reproducible against a fixed dataset. This reads the JSON, rebuilds
the LabeledDataset, and runs the same rugged-rate-stability walk-forward.

Usage:
  .venv/bin/python scripts/walk_forward_dataset.py [--ds data/*.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.labeler import LabeledDataset, LabeledToken, Outcome
from backtest.walk_forward import walk_forward


def _rug_precision(train, test):
    from collections import Counter
    tc = Counter(t.outcome.value for t in train)
    xc = Counter(t.outcome.value for t in test)
    tr = tc.get("rugged", 0) / (sum(tc.values()) or 1)
    xr = xc.get("rugged", 0) / (sum(xc.values()) or 1)
    return 1.0 - min(1.0, abs(tr - xr) * 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", type=str, default="data/labeled_dataset_v4_large.json")
    args = ap.parse_args()
    data = json.load(open(args.ds))
    ds = LabeledDataset()
    for s in data["samples"]:
        ds.add(LabeledToken(
            token=s["token"], chain=s.get("chain", "solana"),
            launch_ts=datetime.fromisoformat(s["launch"]),
            outcome=Outcome(s["outcome"]),
            peak_return_pct=s.get("peak_return_pct", 0.0),
            final_return_pct=s.get("final_return_pct", 0.0),
            days_observed=s.get("days_observed", 0),
            note=s.get("note", ""),
        ))
    print(f"Dataset: {args.ds}  n={len(ds.samples)}  counts={ds.counts()}")
    wf = walk_forward(ds, _rug_precision, min_train=20, step=10, horizon=10)
    if not wf.results:
        print("Too few samples for walk-forward.")
        return 0
    print(f"folds: {len(wf.results)} | mean score: {wf.mean_score:.3f}")
    for r in wf.results:
        print(f"  fold {r.fold_index}: train={r.train_n} test={r.test_n} score={r.score:.3f}")
    verdict = "SUPPORTED" if wf.mean_score >= 0.6 else "INSUFFICIENT (ILLUSTRATIVE stands)"
    print(f"\nVerdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
