"""Test EV-001 (dex_flow) + EV-021 (wallet_funding) producers (Phase 1)."""
from datetime import datetime, timedelta

from data_sources.dex_flow import Swap, aggregate_swaps
from data_sources.wallet_funding import FundingEdge, build_funding_graph


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


# ---- EV-001 dex flow ----

def test_aggregate_swaps_net_buy():
    swaps = [
        Swap("A", "BUY", 1000, 100.0, _t(0)),
        Swap("B", "BUY", 1000, 90.0, _t(0)),
        Swap("C", "SELL", 500, 40.0, _t(1)),
        Swap("A", "SELL", 200, 15.0, _t(1)),
    ]
    snap = aggregate_swaps("TOK", "solana", swaps, _t(0), _t(2))
    assert snap.total_buy == 190.0
    assert snap.total_sell == 55.0
    assert snap.net_flow_direction == "BUY"
    assert snap.unique_buyers == 2
    assert snap.unique_sellers == 2


def test_aggregate_swaps_net_sell_direction():
    swaps = [
        Swap("A", "SELL", 1000, 100.0, _t(0)),
        Swap("B", "BUY", 100, 10.0, _t(0)),
    ]
    snap = aggregate_swaps("TOK", "solana", swaps, _t(0), _t(1))
    assert snap.net_flow_direction == "SELL"


def test_avg_trades_per_wallet():
    swaps = [
        Swap("A", "BUY", 1000, 10.0, _t(0)),
        Swap("A", "BUY", 1000, 10.0, _t(0)),
        Swap("B", "BUY", 1000, 10.0, _t(0)),
    ]
    snap = aggregate_swaps("TOK", "solana", swaps, _t(0), _t(1))
    assert snap.avg_trades_per_wallet == 1.5  # A=2, B=1 -> (3/2)
    assert snap.trades_per_wallet["A"] == 2


# ---- EV-021 wallet funding ----

def test_build_funding_graph_clusters():
    edges = [
        FundingEdge("MASTER1", "w1", 500.0, _t(0), "solana"),
        FundingEdge("MASTER1", "w2", 500.0, _t(0), "solana"),
        FundingEdge("MASTER1", "w3", 300.0, _t(1), "solana"),
        FundingEdge("MASTER2", "w9", 1000.0, _t(0), "solana"),
    ]
    g = build_funding_graph("TOK", "solana", edges)
    assert g.cluster_count == 2
    c1 = g.cluster_by_master("MASTER1")
    assert c1 is not None
    assert c1.size == 3
    assert c1.total_funded == 1300.0
    assert c1.summary()["cluster_id"] == "TOK-C1"


def test_funding_graph_empty():
    g = build_funding_graph("TOK", "solana", [])
    assert g.cluster_count == 0


def test_funding_edge_summary_shape():
    edges = [FundingEdge("M", "w1", 100.0, _t(0), "solana")]
    g = build_funding_graph("TOK", "solana", edges)
    s = g.summary()
    assert s["token"] == "TOK"
    assert s["cluster_count"] == 1
    assert s["clusters"][0]["size"] == 1
