#!/usr/bin/env python3
"""Run calibration: backfill LabeledDataset from real data -> walk-forward.

Usage:
  .venv/bin/python scripts/calibrate.py [--max N] [--out PATH] [--save-ds PATH]

Fetches real token history (GMGN trenches + kline), labels outcomes, saves the
dataset, and runs walk-forward re-validation to decide which thresholds are
empirically supported (vs ILLUSTRATIVE).

Run: .venv/bin/python scripts/calibrate.py --max 15
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backfill import BackfillConfig, DatasetBackfiller
from backtest.walk_forward import walk_forward
from fetchers.gmgn import GmgnFetcher


def _rug_precision(train, test):
    """Evaluator: fraction of test tokens labeled rugged that ARE rugged.

    In a well-calibrated model, higher rug_ratio in training should not change
    the base rate; we measure label separation between train/test rugged rate.
    Returns a score in [0,1] representing consistency.
    """
    from collections import Counter
    train_c = Counter(t.outcome.value for t in train)
    test_c = Counter(t.outcome.value for t in test)
    train_total = sum(train_c.values()) or 1
    test_total = sum(test_c.values()) or 1
    train_rug = train_c.get("rugged", 0) / train_total
    test_rug = test_c.get("rugged", 0) / test_total
    # 1.0 if rates match (stable), lower if they diverge
    return 1.0 - min(1.0, abs(train_rug - test_rug) * 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=15, help="max tokens to label")
    ap.add_argument("--save-ds", type=str, default="", help="save labeled dataset JSON path")
    ap.add_argument("--chain", type=str, default="solana")
    ap.add_argument("--min-age", type=int, default=2)
    ap.add_argument("--universe", type=str, default="trending",
                    choices=["trending", "trenches"],
                    help="universe source: trending (mature, default) or trenches (new)")
    args = ap.parse_args()

    gmgn = GmgnFetcher()
    cfg = BackfillConfig(chain=args.chain, max_tokens=args.max,
                         min_launch_days_ago=args.min_age, universe_mode=args.universe)
    backfiller = DatasetBackfiller(gmgn, cfg)

    print(f"=== Backfilling labeled dataset (chain={args.chain}, max={args.max}) ===")
    ds = backfiller.build()
    print(f"\nDataset: {len(ds.samples)} samples")
    print("Outcome counts:", ds.counts())
    if not ds.samples:
        print("No samples; nothing to calibrate.")
        return 0

    if args.save_ds:
        backfiller.save(ds, args.save_ds)
        print(f"Saved dataset -> {args.save_ds}")

    # Walk-forward on rugged-rate stability
    print("\n=== Walk-forward re-validation (rugged-rate stability) ===")
    wf = walk_forward(ds, _rug_precision, min_train=8, step=5, horizon=5)
    if wf.results:
        print(f"  folds: {len(wf.results)} | mean score: {wf.mean_score:.3f}")
        for r in wf.results[:8]:
            print(f"    fold {r.fold_index}: train={r.train_n} test={r.test_n} score={r.score:.3f}")
        verdict = "SUPPORTED" if wf.mean_score >= 0.6 else "INSUFFICIENT (ILLUSTRATIVE stands)"
        print(f"\n  Verdict: {verdict}")
    else:
        print("  Too few samples for walk-forward; thresholds remain ILLUSTRATIVE.")

    print("\nNOTE: This validates label STABILITY, not predictive power. Production "
          "threshold changes still require calibration against labeled outcomes "
          "of the specific metric (IHR, ITA, etc.). See docs/CALIBRATION.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
