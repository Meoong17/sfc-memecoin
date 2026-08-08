#!/usr/bin/env python3
"""Phase 2 smoke test: wallet graph + sybil + classify + insider + risk on labeled tokens.

Two illustrative labeled scenarios from spec §8:
  - "BULLISH_RISKY" : high raw Alpha but high insider risk -> RAA drops sharply
  - "HEALTHY"       : lower raw Alpha, low insider -> RAA stays high

This is a SMOKE test (does it run + sane direction), NOT calibration.

Run: .venv/bin/python scripts/smoke_phase2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import datetime, timedelta

from data_sources.dex_flow import Swap, aggregate_swaps
from data_sources.wallet_funding import FundingEdge, build_funding_graph
from engines.alpha_risk import AlphaInputs, AlphaRiskEngine
from engines.insider_intel import EntryEvent, InsiderInputs, InsiderIntelligenceEngine
from engines.sybil_score import SybilInputs, SybilScoreEngine
from engines.wallet_classify import WalletClassifier, WalletSignals
from engines.wallet_graph import WalletGraphEngine


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def build_case(name, *, insider_cluster, public_buy, supply_by_role, early_entries):
    # funding graph
    edges = []
    for i in range(5):
        edges.append(FundingEdge("MASTER1", f"ins{i}", 100, _t(0), "solana"))
    if not insider_cluster:
        edges = []
    fg = build_funding_graph(name, "solana", edges)

    # swap flow
    swaps = [Swap(f"pub{i}", "BUY" if public_buy else "SELL", 1000, 100, _t(0)) for i in range(20)]
    flow = aggregate_swaps(name, "solana", swaps, _t(0), _t(1))

    # wallet graph
    wg = WalletGraphEngine(fg, flow).build()

    # sybil
    syb = SybilScoreEngine(fg, flow).score(SybilInputs(
        holder_count=100,
        wallet_creation_proximity_ratio=0.8 if insider_cluster else 0.05,
        identical_trade_size_ratio=0.8 if insider_cluster else 0.05,
        repeated_dex_ratio=0.7 if insider_cluster else 0.05,
    ))

    # classify the insider wallet
    clf = WalletClassifier()
    cl = clf.classify(WalletSignals(wallet="ins0", in_funding_cluster=insider_cluster,
                                    buy_before_info_expansion=bool(early_entries),
                                    entry_lead_seconds=600.0 if early_entries else 0.0))

    # insider intel
    ins = InsiderInputs(
        entry_events=[EntryEvent(w, -30.0 if early_entries else 45.0, 100) for w in ["ins0", "ins1", "ins2"]],
        launch_minute=0.0, info_expansion_minute=10.0,
        suspected_insider_holdings=0.5 if insider_cluster else 0.0,
        effective_circulating_supply=1.0,
        insider_cluster_supply=0.5 if insider_cluster else 0.0,
    )
    ie = InsiderIntelligenceEngine(fg, flow).analyze(name, ins)

    # alpha / risk
    alpha_in = AlphaInputs(
        alpha=92 if insider_cluster else 84,
        organic=87 if insider_cluster else 91,
        safety=83 if insider_cluster else 94,
        smart_money=91 if insider_cluster else 86,
        insider=ie, sybil=syb,
    )
    ar = AlphaRiskEngine().compute(alpha_in)
    return {"name": name, "wg": wg, "syb": syb, "classify": cl, "insider": ie, "alpha": ar}


def main() -> int:
    risky = build_case("BULLISH_RISKY", insider_cluster=True, public_buy=True,
                       supply_by_role={}, early_entries=True)
    healthy = build_case("HEALTHY", insider_cluster=False, public_buy=True,
                         supply_by_role={}, early_entries=False)

    print("=== SFC Memecoin Phase 2 smoke test ===")
    for case in (risky, healthy):
        c = case
        print(f"\n[{c['name']}]")
        print(f"  wallet_graph: {c['wg'].n_components} component(s), "
              f"{sum(1 for x in c['wg'].clusters if x.suspected_dev_insider)} suspected insider cluster(s)")
        print(f"  sybil_risk  : {c['syb'].sybil_risk} ({c['syb'].risk_level})")
        print(f"  classified  : {c['classify'].role} (conf {c['classify'].confidence})")
        print(f"  insider_prob: {c['insider'].insider_probability} | IHR {c['insider'].ihr_class} "
              f"| dist {c['insider'].distribution_level} | exit {c['insider'].exit_liquidity_risk}")
        print(f"  ALPHA={c['alpha'].alpha:.0f} ORGANIC={c['alpha'].organic:.0f} "
              f"SAFETY={c['alpha'].safety:.0f} SM={c['alpha'].smart_money:.0f}")
        print(f"  RISK-ADJUSTED ALPHA={c['alpha'].risk_adjusted_alpha:.1f} "
              f"(penalty {c['alpha'].risk_penalty:.0%})  factors={c['alpha'].downside_factors}")

    r, h = risky["alpha"], healthy["alpha"]
    assert r.risk_adjusted_alpha < h.risk_adjusted_alpha, "BULLISH_RISKY should rank below HEALTHY after risk"
    print("\n=== PASS: Risk-Adjusted Alpha correctly penalizes insider-heavy token ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
