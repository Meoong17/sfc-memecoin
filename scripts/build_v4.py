#!/usr/bin/env python3
"""Build v4 large dataset (n>100) with wider universe + more intervals.

Goal: validate stability of twitter_create_token_count (corr +0.921 on n=40)
at larger n and re-run walk-forward for an honest verdict.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backfill import BackfillConfig, DatasetBackfiller
from fetchers.gmgn import GmgnFetcher


def main() -> int:
    cfg = BackfillConfig(
        chain="solana",
        max_tokens=140,
        min_launch_days_ago=2,
        max_launch_days_ago=120,
        universe_mode="trending",
        trending_min_created="7d",
        # wider interval mix to preserve class variety at higher n
        trending_intervals=("1h", "6h", "24h", "7d"),
    )
    gmgn = GmgnFetcher()
    bf = DatasetBackfiller(gmgn, cfg)
    print("=== v4 backfill: trending 1h/6h/24h/7d, max=140 ===")
    ds = bf.build()
    print("\nResult:", len(ds.samples), "samples", ds.counts())
    if not ds.samples:
        print("No samples.")
        return 1
    out = "data/labeled_dataset_v4_large.json"
    bf.save(ds, out)
    print("Saved ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
