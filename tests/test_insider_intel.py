"""Test Insider Intelligence Engine P0 (Phase 2, spec §6.6)."""
from datetime import datetime, timedelta

from data_sources.dex_flow import Swap, aggregate_swaps
from data_sources.wallet_funding import FundingEdge, build_funding_graph
from engines.insider_intel import (
    EntryEvent, InsiderInputs, InsiderIntelligenceEngine,
)


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def _flow(public_buy=True):
    swaps = [
        Swap("pub1", "BUY", 1000, 100, _t(0)),
        Swap("pub2", "BUY", 1000, 100, _t(0)),
    ]
    if not public_buy:
        swaps = [Swap("pub1", "SELL", 1000, 100, _t(0))]
    return aggregate_swaps("TOK", "solana", swaps, _t(0), _t(1))


def _empty_funding():
    return build_funding_graph("TOK", "solana", [])


def test_early_entry_detection():
    ins = InsiderInputs(
        entry_events=[
            EntryEvent("W-A", -42.0, 100),
            EntryEvent("W-B", -35.0, 100),
            EntryEvent("W-C", 30.0, 100),  # after launch -> not early
        ],
        launch_minute=0.0, info_expansion_minute=18.0,
    )
    eng = InsiderIntelligenceEngine(_empty_funding())
    r = eng.analyze("TOK", ins)
    assert set(r.early_entry_events) == {"W-A", "W-B"}
    assert r.ita > 0.3


def test_ihr_classification():
    eng = InsiderIntelligenceEngine(_empty_funding())
    cases = [(0.03, "LOW"), (0.07, "MODERATE"), (0.15, "HIGH"), (0.25, "CRITICAL")]
    for ihr, cls in cases:
        ins = InsiderInputs(suspected_insider_holdings=ihr, effective_circulating_supply=1.0)
        assert eng.analyze("TOK", ins).ihr_class == cls


def test_exit_liquidity_high_when_insider_distributes_and_public_buys():
    edges = [FundingEdge("M1", "w1", 500, _t(0), "solana"),
             FundingEdge("M1", "w2", 500, _t(0), "solana")]
    fg = build_funding_graph("TOK", "solana", edges)
    flow = _flow(public_buy=True)
    eng = InsiderIntelligenceEngine(fg, flow)
    ins = InsiderInputs(
        insider_cluster_supply=0.5, effective_circulating_supply=1.0,
        entry_events=[EntryEvent("w1", -30.0, 100)],
        launch_minute=0.0, info_expansion_minute=10.0,
    )
    r = eng.analyze("TOK", ins)
    assert r.insider_distribution
    assert r.exit_liquidity_risk == "HIGH"
    assert r.insider_probability >= 0.6


def test_clean_no_insider():
    eng = InsiderIntelligenceEngine(_empty_funding(), _flow(public_buy=True))
    ins = InsiderInputs(
        entry_events=[EntryEvent("pub1", 60.0, 100)],
        launch_minute=0.0, info_expansion_minute=20.0,
        insider_cluster_supply=0.0, effective_circulating_supply=1.0,
    )
    r = eng.analyze("TOK", ins)
    assert r.insider_probability == 0.0
    assert r.ihr_class == "LOW"
    assert r.exit_liquidity_risk == "LOW"


def test_no_supply_safe_ihr():
    eng = InsiderIntelligenceEngine(_empty_funding())
    r = eng.analyze("TOK", InsiderInputs(effective_circulating_supply=0.0))
    assert r.ihr == 0.0
    assert r.ihr_class == "LOW"


def test_summary_shape():
    eng = InsiderIntelligenceEngine(_empty_funding())
    r = eng.analyze("TOK", InsiderInputs(
        entry_events=[EntryEvent("A", -10.0, 50)], launch_minute=0.0,
        info_expansion_minute=5.0, effective_circulating_supply=100.0,
        suspected_insider_holdings=10.0))
    s = r.summary()
    assert s["token"] == "TOK"
    for k in ["insider_probability", "ihr", "ihr_class", "exit_liquidity_risk",
              "ita", "evidence", "counter_evidence"]:
        assert k in s
