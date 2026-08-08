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
    ap.add_argument("--notify", action="store_true",
                    help="push the ranking to Telegram (TELEGRAM_BOT_TOKEN/CHAT_ID in .env)")
    args = ap.parse_args()

    wire = LivePipelineWire()
    print(f"Live sources available: {wire.sources.available or '(none)'}")

    notif = None
    if args.notify:
        from scripts.telegram_notify import TelegramNotifier
        notif = TelegramNotifier()
        print(f"[telegram] enabled={notif.enabled}")

    start = time.time()
    try:
        universe = wire.fetch_universe(limit=args.limit)
    except Exception as e:
        print(f"ERROR discovering universe: {e}", file=sys.stderr)
        return 1
    print(f"Universe: {universe.count} tokens fetched in {time.time()-start:.1f}s\n")

    board = RankingBoard()
    market_by_token: dict[str, dict] = {}   # token -> {symbol, price, mcap, liq, vol}
    for info in universe.tokens:
        if time.time() - start > args.timeout:
            print("TIMEOUT reached; stopping.", file=sys.stderr)
            break
        if not info.address:
            continue
        try:
            enriched = wire.enrich_market(info)
            score = wire.score_from_market(enriched)
        except Exception as e:
            print(f"  [{info.symbol or info.address[:10]}] SCORE ERROR: {e}")
            continue
        board.add(score)
        market_by_token[enriched.address] = {
            "symbol": enriched.symbol,
            "price_usd": enriched.price_usd,
            "mcap": enriched.mcap,
            "liquidity_usd": enriched.liquidity_usd,
            "volume_24h": enriched.volume_24h,
        }
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
        snap = board.snapshot()
        _attach_market(snap, market_by_token)
        out.write_text(json.dumps(snap, indent=2))
        print(f"\nSaved snapshot -> {out}")

    if notif is not None:
        snap = board.snapshot()
        _attach_market(snap, market_by_token)
        ok = notif.send_ranking(snap, universe_size=len(universe.tokens))
        print(f"[telegram] ranking sent={ok}")

    print(f"\nDone in {time.time()-start:.1f}s | {board.snapshot()['admitted']} admitted / {board.snapshot()['count']}")
    return 0


def _attach_market(snap: dict, market_by_token: dict[str, dict]) -> None:
    """Merge symbol/price/mcap/liquidity/volume into each ranking item.

    RankingBoard items carry the token address; the market data was captured
    per-token during collection. This keeps the notifier format decoupled from
    the collection internals (the snapshot is the contract).
    """
    for item in snap.get("ranking", []):
        tok = item.get("token")
        m = market_by_token.get(tok)
        if m:
            item["symbol"] = m.get("symbol", "")
            item["price_usd"] = m.get("price_usd", 0.0)
            item["mcap"] = m.get("mcap")
            item["liquidity_usd"] = m.get("liquidity_usd", 0.0)
            item["volume_24h"] = m.get("volume_24h", 0.0)


if __name__ == "__main__":
    raise SystemExit(main())
