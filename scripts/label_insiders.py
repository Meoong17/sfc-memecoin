#!/usr/bin/env python3
"""Collect a real INSIDER-labeled dataset from live GMGN on-chain signals.

Labels a token universe by dev/holder/LP on-chain behaviour (rug / dev_dump /
early_sell / clean) — NOT price. This is the "real insider label" source the
calibration ledger needs (v5 §8), distinct from the fragile price-proxy labels.

Usage:
  .venv/bin/python scripts/label_insiders.py [--limit N] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.insider_labels import label_from_gmgn
from wiring import LiveSourceBundle, LivePipelineWire


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", type=str, default="data/insider_labeled_dataset_v1.json")
    args = ap.parse_args()

    sources = LiveSourceBundle.from_env()
    wire = LivePipelineWire(sources=sources, sources_from_env=False)
    if sources.gmgn is None:
        print("GMGN unavailable; cannot collect insider labels.")
        return 1
    uni = wire.fetch_universe(limit=args.limit)
    print(f"Universe: {uni.count} tokens")

    rows = []
    seen = set()
    for info in uni.tokens:
        if info.address in seen:
            continue
        seen.add(info.address)
        enr = wire.enrich_market(info)
        if enr.chain not in ("solana", "sol"):
            continue
        dev = sources.gmgn.dev_trader_signals(enr.address, enr.chain)
        sec = sources.gmgn._run("token", "security", "--chain", "sol",
                                "--address", enr.address)
        lbl = label_from_gmgn(enr.address, enr.chain, dev, sec)
        rows.append(lbl.summary())
        print(f"  {enr.address[:10]} -> {lbl.outcome.value}")

    c = Counter(r["outcome"] for r in rows)
    print(f"\nCollected: {len(rows)} samples | {dict(c)}")

    if rows:
        payload = {
            "generated_at": time.time(),
            "label_type": "insider_onchain (rug/dev_dump/early_sell/clean) — "
                          "NOT price proxy",
            "source": "GMGN token traders --tag dev + token security",
            "n": len(rows),
            "counts": dict(c),
            "samples": rows,
        }
        with open(args.out, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"Saved -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
