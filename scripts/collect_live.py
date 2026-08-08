#!/usr/bin/env python3
"""Live collection: fetch real universe -> score via pipeline -> ranking.

Usage:
  .venv/bin/python scripts/collect_live.py [--limit N] [--out PATH] [--timeout S]

Fetches a real token universe (DexScreener), scores each admitted token through
the full pipeline (with GMGN security + Helius when keys present), and prints a
Risk-Adjusted Alpha ranking. This is the live entrypoint mirroring
SFC Terminal's collect flow.

WARNING: live API calls hit real rate limits; start with a small --limit.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.sse_server import RankingBoard
from wiring import LivePipelineWire


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5, help="universe size (start small)")
    ap.add_argument("--out", type=str, default="", help="optional JSON output path")
    ap.add_argument("--timeout", type=float, default=120, help="overall timeout seconds")
    args = ap.parse_args()

    wire = LivePipelineWire()
    print(f"Live sources available: {wire.sources.available or '(none)'}")

    start = time.time()
    try:
        universe = wire.fetch_universe(limit=args.limit)
    except Exception as e:
        print(f"ERROR discovering universe: {e}", file=sys.stderr)
        return 1
    print(f"Universe: {universe.count} tokens fetched in {time.time()-start:.1f}s\n")

    board = RankingBoard()
    for info in universe.tokens:
        if time.time() - start > args.timeout:
            print("TIMEOUT reached; stopping.", file=sys.stderr)
            break
        if not info.address:
            continue
        try:
            score = wire.score_from_market(info)
        except Exception as e:
            print(f"  [{info.symbol or info.address[:10]}] SCORE ERROR: {e}")
            continue
        board.add(score)
        status = "BLOCKED" if not score.admitted else "scored"
        print(f"  {info.symbol or info.address[:10]:<12} {status:<8} "
              f"RAA={score.risk_adjusted_alpha:6.1f} insider={score.insider_probability:.2f}")

    print("\n=== Ranking (Risk-Adjusted Alpha, admitted only) ===")
    ranked = board.ranked()
    for i, r in enumerate(ranked, 1):
        print(f"  {i}. {r['token'][:16]:<18} RAA={r['risk_adjusted_alpha']:.1f} "
              f"conf={r['confidence']:.2f} conf<>={r['confluence_label']}")

    if args.out:
        out = Path(args.out)
        out.write_text(json.dumps(board.snapshot(), indent=2))
        print(f"\nSaved snapshot -> {out}")

    print(f"\nDone in {time.time()-start:.1f}s | {board.snapshot()['admitted']} admitted / {board.snapshot()['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
