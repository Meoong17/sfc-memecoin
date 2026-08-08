#!/usr/bin/env python3
"""Phase 5 smoke test: full pipeline + ranking end-to-end.

Scores several tokens (clean, insider-heavy, honeypot-blocked) through the full
pipeline and verifies ranking order + exclusion of blocked tokens.

Run: .venv/bin/python scripts/smoke_phase5.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_sources.dex_flow import Swap
from data_sources.wallet_funding import FundingEdge
from dashboard.sse_server import RankingBoard
from engines.insider_intel import EntryEvent
from pipeline import ScreeningPipeline, TokenFeatures


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def _base(token):
    return TokenFeatures(
        token=token, chain="solana",
        funding_clusters=[FundingEdge("M1", "w1", 500, _t(0), "solana")],
        swaps=[Swap("w1", "BUY", 1000, 100, _t(0)), Swap("pub", "BUY", 1000, 100, _t(0))],
        contract_risk_level="SAFE", contract_risk_score=0.1, is_honeypot=False,
        deployer="devClean",
        entry_events=[EntryEvent("w1", -30.0, 100)],
        launch_minute=0.0, info_expansion_minute=10.0,
        suspected_insider_holdings=0.0, effective_circulating_supply=1.0,
        insider_cluster_supply=0.0,
        mention_series=[10, 20, 40],
    )


def main() -> int:
    pipe = ScreeningPipeline()
    board = RankingBoard()

    # 1. clean token, solid fundamentals
    clean = _base("CLEAN")
    clean.alpha_raw, clean.organic_raw = 80, 78
    clean.safety_raw, clean.smart_money_raw = 88, 82
    board.add(pipe.score_token(clean))

    # 2. insider-heavy token: high raw alpha but big insider exposure
    insider = _base("INSIDER_HEAVY")
    insider.alpha_raw, insider.organic_raw = 95, 70
    insider.safety_raw, insider.smart_money_raw = 60, 90
    insider.suspected_insider_holdings = 0.5
    insider.insider_cluster_supply = 0.5
    insider.entry_events = [EntryEvent("w1", -30.0, 100), EntryEvent("w2", -25.0, 100)]
    board.add(pipe.score_token(insider))

    # 3. honeypot -> must be blocked
    honeypot = _base("HONEYPOT")
    honeypot.alpha_raw = 99
    honeypot.is_honeypot = True
    board.add(pipe.score_token(honeypot))

    # 4. solid but modest
    modest = _base("MODEST")
    modest.alpha_raw, modest.organic_raw = 70, 80
    modest.safety_raw, modest.smart_money_raw = 85, 75
    board.add(pipe.score_token(modest))

    print("=== SFC Memecoin Phase 5 full pipeline smoke test ===")
    for s in board.scores:
        flag = "  <-- BLOCKED" if not s.admitted else ""
        print(f"  {s.token:<14} admitted={s.admitted} RAA={s.risk_adjusted_alpha:6.1f} "
              f"insider={s.insider_probability:.2f} conf={s.confidence:.2f} "
              f"conf<>{s.confluence_label}{flag}")

    ranked = board.ranked()
    print("\nFinal ranking (admitted only, by Risk-Adjusted Alpha):")
    for i, r in enumerate(ranked, 1):
        print(f"  {i}. {r['token']:<14} RAA={r['risk_adjusted_alpha']:.1f}")

    # assertions
    assert board.snapshot()["admitted"] == 3, "honeypot should be excluded"
    tokens = [r["token"] for r in ranked]
    assert "HONEYPOT" not in tokens, "blocked token must not be ranked"
    assert tokens[0] != "INSIDER_HEAVY", "insider-heavy should not rank first despite raw alpha 95"
    assert tokens[0] in ("CLEAN", "MODEST"), "a safe token should top the ranking"
    assert all(t["risk_adjusted_alpha"] >= 0 for t in ranked)
    print("\n=== PASS: Phase 5 pipeline + ranking end-to-end correct ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
