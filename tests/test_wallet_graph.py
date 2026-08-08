"""Test Wallet Graph Engine (Phase 2, EV-021 consumer)."""
from datetime import datetime, timedelta

from data_sources.dex_flow import Swap, aggregate_swaps
from data_sources.wallet_funding import FundingEdge, build_funding_graph
from engines.wallet_graph import WalletGraphEngine


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def test_builds_graph_from_funding():
    edges = [
        FundingEdge("M1", "w1", 500, _t(0), "solana"),
        FundingEdge("M1", "w2", 500, _t(0), "solana"),
        FundingEdge("M2", "w9", 1000, _t(0), "solana"),
    ]
    fg = build_funding_graph("TOK", "solana", edges)
    eng = WalletGraphEngine(fg)
    res = eng.build()
    assert res.n_components == 2
    assert res.n_nodes == 5  # M1,w1,w2,M2,w9


def test_common_funder_suspected_dev_insider():
    edges = [
        FundingEdge("M1", "w1", 400, _t(0), "solana"),
        FundingEdge("M1", "w2", 400, _t(0), "solana"),
        FundingEdge("M1", "w3", 400, _t(0), "solana"),
    ]
    fg = build_funding_graph("TOK", "solana", edges)
    flow = aggregate_swaps(
        "TOK", "solana",
        [Swap("w1", "BUY", 1000, 100, _t(0)), Swap("w2", "BUY", 1000, 100, _t(0)),
         Swap("w3", "BUY", 1000, 100, _t(0))],
        _t(0), _t(1))
    eng = WalletGraphEngine(fg, flow)
    res = eng.build()
    # Single component with common funder M1 and high ownership share
    assert len(res.clusters) == 1
    assert res.clusters[0].common_funder == "M1"
    assert res.clusters[0].token_ownership_pct == 100.0
    assert res.clusters[0].trading_correlation >= 0.7
    assert res.clusters[0].suspected_dev_insider


def test_no_funding_no_suspect():
    fg = build_funding_graph("TOK", "solana", [])
    eng = WalletGraphEngine(fg)
    res = eng.build()
    assert res.n_nodes == 0
    assert res.n_components == 0
    assert res.clusters == []


def test_summary_shape():
    edges = [FundingEdge("M1", "w1", 100, _t(0), "solana")]
    fg = build_funding_graph("TOK", "solana", edges)
    res = WalletGraphEngine(fg).build()
    s = res.summary()
    assert s["token"] == "TOK"
    assert s["n_components"] == 1
    assert "clusters" in s
