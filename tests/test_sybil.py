"""Test Sybil Score Engine (Phase 2, EV-021 consumer)."""
from datetime import datetime, timedelta

from data_sources.wallet_funding import FundingEdge, build_funding_graph
from engines.sybil_score import SybilInputs, SybilScoreEngine


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def _many_subs(chain="solana"):
    edges = []
    for i in range(50):
        edges.append(FundingEdge("MASTER1", f"sub{i}", 100, _t(0), chain))
        edges.append(FundingEdge("MASTER2", f"subA{i}", 100, _t(0), chain))
    return build_funding_graph("TOK", chain, edges)


def test_high_sybil_risk_when_highly_funded():
    fg = _many_subs()  # 100 sub-wallets from 2 masters
    eng = SybilScoreEngine(fg)
    res = eng.score(SybilInputs(
        holder_count=105,
        wallet_creation_proximity_ratio=0.8,
        identical_trade_size_ratio=0.8,
        repeated_dex_ratio=0.7,
    ))
    assert res.risk_level == "HIGH"
    assert res.sybil_risk >= 70


def test_low_sybil_when_organic():
    fg = build_funding_graph("TOK", "solana", [])  # no funding clusters
    eng = SybilScoreEngine(fg)
    res = eng.score(SybilInputs(
        holder_count=1000,
        wallet_creation_proximity_ratio=0.05,
        identical_trade_size_ratio=0.05,
        repeated_dex_ratio=0.05,
    ))
    assert res.risk_level == "LOW"
    assert res.sybil_risk < 40


def test_funded_ratio_computation():
    edges = [FundingEdge("M1", "w1", 100, _t(0), "solana"),
             FundingEdge("M1", "w2", 100, _t(0), "solana")]
    fg = build_funding_graph("TOK", "solana", edges)
    eng = SybilScoreEngine(fg)
    res = eng.score(SybilInputs(holder_count=10))
    assert res.funding_wallets == 1
    assert res.funded_ratio == 0.2  # 2/10


def test_zero_holders_safe():
    fg = _many_subs()
    eng = SybilScoreEngine(fg)
    res = eng.score(SybilInputs(holder_count=0))
    assert res.sybil_risk == 0.0
    assert res.risk_level == "LOW"


def test_summary_shape():
    fg = _many_subs()
    res = SybilScoreEngine(fg).score(SybilInputs(holder_count=100))
    s = res.summary()
    assert s["token"] == "TOK"
    assert "sybil_risk" in s and "risk_level" in s and "indicators" in s
