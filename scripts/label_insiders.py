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

from backfill import BackfillConfig
from backtest.insider_labels import label_from_gmgn
from wiring import LiveSourceBundle, LivePipelineWire


def _gmgn_trending_universe(gmgn, chain="solana", intervals=("1h", "6h", "24h", "7d")):
    """Universe from GMGN `market trending` (mature tokens, can exceed DexScreener's
    ~30-profile cap). Deduped across intervals. Returns list of
    {address, chain, created_ts} (created_ts enables temporal walk-forward)."""
    cfg = BackfillConfig(chain=chain, trending_intervals=intervals)
    chain_flag = {"solana": "sol"}.get(chain, chain)
    tokens: dict[str, dict] = {}
    for iv in intervals:
        try:
            data = gmgn._run("market", "trending", "--chain", chain_flag,
                             "--interval", iv, "--limit", "100",
                             "--min-created", cfg.trending_min_created, "--raw")
        except Exception:
            continue
        rank = ((data or {}).get("data") or {}).get("rank") or []
        for t in rank:
            addr = t.get("address")
            if addr:
                tokens[addr] = {
                    "address": addr, "chain": chain,
                    "created_ts": int(t.get("creation_timestamp") or t.get("created_timestamp") or 0),
                }
    return list(tokens.values())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", type=str, default="data/insider_labeled_dataset_v1.json")
    ap.add_argument("--universe", type=str, default="dex",
                    choices=["dex", "trending"],
                    help="universe source: dex (DexScreener ~30) or trending (GMGN, large)")
    args = ap.parse_args()

    sources = LiveSourceBundle.from_env()
    wire = LivePipelineWire(sources=sources, sources_from_env=False)
    if sources.gmgn is None:
        print("GMGN unavailable; cannot collect insider labels.")
        return 1

    if args.universe == "trending":
        cand = _gmgn_trending_universe(sources.gmgn)
        print(f"GMGN trending universe: {len(cand)} tokens (pre-limit)")
    else:
        uni = wire.fetch_universe(limit=args.limit)
        cand = [{"address": t.address, "chain": t.chain} for t in uni.tokens]
        print(f"DexScreener universe: {len(cand)} tokens")

    rows = []
    seen = set()
    for t in cand:
        addr, chain = t["address"], t["chain"]
        if addr in seen or not addr or chain not in ("solana", "sol"):
            continue
        if len(rows) >= args.limit:
            break
        seen.add(addr)
        dev = sources.gmgn.dev_trader_signals(addr, "solana")
        sec = sources.gmgn._run("token", "security", "--chain", "sol",
                                "--address", addr)
        lbl = label_from_gmgn(addr, "solana", dev, sec)
        rec = lbl.summary()
        rec["created_ts"] = t.get("created_ts", 0)  # enables temporal walk-forward
        rows.append(rec)
        print(f"  {addr[:10]} -> {lbl.outcome.value}")

    c = Counter(r["outcome"] for r in rows)
    print(f"\nCollected: {len(rows)} samples | {dict(c)}")

    if rows:
        payload = {
            "generated_at": time.time(),
            "label_type": "insider_onchain (rug/dev_dump/early_sell/clean) — "
                          "NOT price proxy",
            "source": "GMGN token traders --tag dev + token security",
            "universe": args.universe,
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

