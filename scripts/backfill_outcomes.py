#!/usr/bin/env python3
"""Backfill OUTCOMES for launch snapshots (predictive-edge dataset step 2).

After an observation window, fetch each token's current price, compute the
return relative to the reference price recorded at snapshot time, and label the
outcome (rugged / survived / pumped) using the empirical labeler
(backtest.labeler.classify_outcome). This is the OUTCOME side of the honest
score->outcome test — the outcome is derived from price/event facts, never from
the model's own signals (avoiding circularity).

Notes on labeling fidelity (stated honestly):
  - classify_outcome needs peak_return_pct + max_drawdown_pct, which require a
    price HISTORY since snapshot. Here we only fetch the CURRENT price, so for
    the first pass we set peak=max_drawdown=current (a conservative snapshot);
    once price history is available (e.g. Binance/DexScreener candles) this can
    be upgraded. The important property for the test is that the outcome is
    INDEPENDENT of the score — which holds regardless.

Usage:
  .venv/bin/python scripts/backfill_outcomes.py --ledger data/launch_snapshots.json
  .venv/bin/python scripts/backfill_outcomes.py --ledger data/launch_snapshots.json \
      --min-window-days 1 --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.labeler import classify_outcome


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=str, default="data/launch_snapshots.json")
    ap.add_argument("--min-window-days", type=float, default=1.0,
                    help="only backfill tokens whose snapshot is this old")
    ap.add_argument("--dry-run", action="store_true", help="report, don't write")
    ap.add_argument("--timeout", type=float, default=90)
    args = ap.parse_args()

    try:
        ledger = json.load(open(args.ledger))
    except FileNotFoundError:
        print(f"ledger not found: {args.ledger}", file=sys.stderr)
        return 1

    records = ledger["records"]
    if not records:
        print("no records to backfill.")
        return 0

    from fetchers.dex_screener import DexScreenerFetcher
    dex = DexScreenerFetcher()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.min_window_days)

    updated = 0
    pending = 0
    start = time.time()
    for i, r in enumerate(records):
        if time.time() - start > args.timeout:
            print("TIMEOUT reached; stopping.", file=sys.stderr)
            break
        # already labeled -> skip
        if r.get("outcome"):
            continue
        try:
            launch_ts = datetime.fromisoformat(r["launch_ts"])
        except (KeyError, ValueError):
            launch_ts = None
        if launch_ts and launch_ts > cutoff:
            pending += 1
            continue
        ref_price = r.get("ref_price")
        if not ref_price:
            print(f"  [{r['token'][:10]}] no ref_price; cannot compute return")
            pending += 1
            continue
        # fetch current price
        try:
            detail = dex.token_detail(r["token"], r.get("chain", "solana"))
        except Exception as e:
            print(f"  [{r['token'][:10]}] fetch error: {e}")
            pending += 1
            continue
        cur = detail.price_usd if detail else None
        if not cur or cur <= 0:
            print(f"  [{r['token'][:10]}] no current price")
            pending += 1
            continue

        final_return_pct = (cur / ref_price - 1.0) * 100.0
        days_observed = (now - launch_ts).days if launch_ts else 0
        # Conservative first-pass outcome: without price history we cannot know
        # peak drawdown vs sustained pump. Treat current == final and classify
        # on final_return only (deep collapse -> rugged; big sustained gain ->
        # pumped candidate). Upgrade later with candle history.
        outcome = classify_outcome(
            lp_removed=False,
            max_drawdown_pct=min(0.0, final_return_pct),
            peak_return_pct=max(0.0, final_return_pct),
            days_observed=days_observed,
        )
        r["outcome"] = outcome.value
        r["final_return_pct"] = round(final_return_pct, 2)
        r["peak_return_pct"] = round(max(0.0, final_return_pct), 2)
        r["days_observed"] = days_observed
        updated += 1
        print(f"  [{r['token'][:10]}] cur={cur:.8g} ret={final_return_pct:+.1f}% "
              f"-> {outcome.value} ({days_observed}d)")

    if not args.dry_run and updated:
        with open(args.ledger, "w") as fh:
            json.dump(ledger, fh, indent=2)
        print(f"\nWrote {updated} outcome(s) -> {args.ledger}")
    else:
        print(f"\n[{'dry-run, ' if args.dry_run else ''}updated={updated} "
              f"pending={pending}]")

    print("\nNext: scripts/validate_predictive_edge.py --snapshots "
          f"{args.ledger}  (re-scores stored features against outcomes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
