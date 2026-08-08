#!/usr/bin/env python3
"""Collect full live-feature snapshots at launch time (predictive-edge dataset).

The honest score->outcome test requires a TokenFeatures snapshot (all live
evidence: OKX, funding, market_stats, wallet analytics) recorded when the model
would actually decide — NOT a historical proxy from `note` strings. This script
runs the real pipeline on the current universe and persists a full snapshot per
token to a JSON ledger, ready for outcome backfill later.

Typical use (alongside the 6h cron):
  .venv/bin/python scripts/snapshot_collect.py --limit 8 --out data/launch_snapshots.json

WARNING: live API calls hit real rate limits; keep --limit small.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from snapshot_store import write_snapshot
from wiring import LivePipelineWire


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--out", type=str, default="data/launch_snapshots.json")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--dedupe", action="store_true",
                    help="skip tokens already present in the ledger (keep existing)")
    args = ap.parse_args()

    wire = LivePipelineWire()
    print(f"Live sources available: {wire.sources.available or '(none)'}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    existing = set()
    if args.dedupe:
        try:
            led = json.load(open(out))
            existing = {r["token"] for r in led.get("records", [])}
            print(f"[dedupe] {len(existing)} tokens already in ledger")
        except (FileNotFoundError, json.JSONDecodeError):
            existing = set()

    start = time.time()
    try:
        universe = wire.fetch_universe(limit=args.limit)
    except Exception as e:
        print(f"ERROR discovering universe: {e}", file=sys.stderr)
        return 1
    print(f"Universe: {universe.count} tokens in {time.time()-start:.1f}s\n")

    now = datetime.now(timezone.utc)
    written = 0
    for info in universe.tokens:
        if time.time() - start > args.timeout:
            print("TIMEOUT reached; stopping.", file=sys.stderr)
            break
        if not info.address:
            continue
        if args.dedupe and info.address in existing:
            print(f"  [{info.symbol or info.address[:10]}] skipped (in ledger)")
            continue
        try:
            enriched = wire.enrich_market(info)
            features = wire.build_features(enriched)
            score = wire.pipeline.score_token(features)
        except Exception as e:
            print(f"  [{info.symbol or info.address[:10]}] ERROR: {e}")
            continue
        write_snapshot(str(out), token=enriched.address, chain=enriched.chain,
                       launch_ts=now, features=features, score=score.summary(),
                       ref_price=enriched.price_usd, ref_mcap=enriched.mcap)
        written += 1
        status = "BLOCKED" if not score.admitted else "scored"
        print(f"  [{enriched.symbol or enriched.address[:10]}] {status} "
              f"RAA={score.risk_adjusted_alpha:.1f} conf={score.confidence:.2f} "
              f"insider={score.insider_probability:.2f}")

    print(f"\nSaved {written} snapshot(s) -> {out}")
    print("Next: scripts/backfill_outcomes.py --ledger <path> after the "
          "observation window to label rugged/survived/pumped, then "
          "scripts/validate_predictive_edge.py --snapshots <path>.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
