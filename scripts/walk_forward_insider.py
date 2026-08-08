#!/usr/bin/env python3
"""Walk-forward on an INSIDER-labeled dataset (rug/dev_dump/early_sell/clean).

Like scripts/walk_forward_dataset.py but for the on-chain insider labels
(backtest/insider_labels.py), ordered by created_ts (launch time) so the folds
are temporal (no look-ahead). Evaluator = stability of the "dirty" rate
(dev_dump + rug, i.e. NOT clean) between train and test — a well-calibrated
label should not let the base rate shift wildly across time.

Usage:
  .venv/bin/python scripts/walk_forward_insider.py [--ds data/*.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.walk_forward import walk_forward


def _dirty_precision(train, test):
    """Stability of dirty-rate (dev_dump+rug) between train and test.
    1.0 if rates match; lower as they diverge. Label read from LabeledToken.note
    (carries the insider outcome string), since LabeledToken.outcome is the
    price-based Outcome enum."""
    def dirty_rate(samples):
        c = Counter(s.note for s in samples)
        total = sum(c.values()) or 1
        return (c.get("dev_dump", 0) + c.get("rug", 0)) / total
    tr = dirty_rate(train)
    te = dirty_rate(test)
    return 1.0 - min(1.0, abs(tr - te) * 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ds", type=str, default="data/insider_labeled_dataset_v2_large.json")
    args = ap.parse_args()
    data = json.load(open(args.ds))

    samples = []
    for s in data["samples"]:
        samples.append({
            "token": s["token"],
            "created_ts": s.get("created_ts", 0),
            "outcome": s["outcome"],
        })
    samples.sort(key=lambda s: s["created_ts"])
    n = len(samples)
    c = Counter(s["outcome"] for s in samples)
    print(f"Dataset: {args.ds}  n={n}  counts={dict(c)}")
    has_ts = sum(1 for s in samples if s["created_ts"])
    print(f"samples with created_ts: {has_ts}/{n}")

    if n < 21:
        print("Too few samples for walk-forward; thresholds stay ILLUSTRATIVE.")
        return 0

    # build a lightweight ordered dataset for walk_forward (needs .launch_ts + .note)
    from datetime import datetime
    from backtest.labeler import LabeledDataset, LabeledToken, Outcome

    ds = LabeledDataset()
    for s in samples:
        ts = datetime.fromtimestamp(s["created_ts"]) if s["created_ts"] else datetime(2026, 8, 1)
        # carry the insider label in note; outcome placeholder unused by evaluator
        ds.add(LabeledToken(token=s["token"], chain="solana", launch_ts=ts,
                            outcome=Outcome.SURVIVED, note=s["outcome"]))
    wf = walk_forward(ds, _dirty_precision, min_train=20, step=10, horizon=10)
    if not wf.results:
        print("Too few samples for walk-forward; thresholds stay ILLUSTRATIVE.")
        return 0
    print(f"folds: {len(wf.results)} | mean score: {wf.mean_score:.3f}")
    for r in wf.results:
        print(f"  fold {r.fold_index}: train={r.train_n} test={r.test_n} score={r.score:.3f}")
    verdict = "SUPPORTED" if wf.mean_score >= 0.6 else "INSUFFICIENT (ILLUSTRATIVE stands)"
    print(f"\nVerdict: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
