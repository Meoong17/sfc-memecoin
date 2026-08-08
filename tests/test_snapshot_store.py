"""Test the launch-snapshot store (round-trip serialize/deserialize)."""
import json
from datetime import datetime, timedelta, timezone

from data_sources.dex_flow import Swap
from data_sources.wallet_funding import FundingEdge
from engines.insider_intel import EntryEvent
from fetchers.gmgn import WalletAnalytics
from pipeline import TokenFeatures
from snapshot_store import (deserialize_features, load_ledger, serialize_features,
                            write_snapshot)


def _full_features() -> TokenFeatures:
    f = TokenFeatures(token="AAAABBBBCCCCDDDD", chain="solana")
    f.funding_clusters = [
        FundingEdge(master_wallet="M", sub_wallet="S1", amount=1e6,
                    ts=datetime(2026, 8, 1, tzinfo=timezone.utc), chain="solana"),
        FundingEdge(master_wallet="M", sub_wallet="S2", amount=2e6,
                    ts=datetime(2026, 8, 1, 0, 5, tzinfo=timezone.utc), chain="solana"),
    ]
    f.swaps = [Swap(wallet="w1", side="BUY", amount_token=1000, amount_quote=5.0,
                    ts=datetime(2026, 8, 1, tzinfo=timezone.utc), pool="pool1")]
    f.entry_events = [EntryEvent(wallet="w1", buy_ts_minutes=-30.0, amount=100)]
    f.wallet_analytics = [WalletAnalytics(wallet="w1", chain="solana",
                                          sniper_count=3, win_rate=0.7,
                                          suspected_insider_hold_rate=0.5)]
    f.okx_signals = {"okx_rug_pull_count": 1, "okx_top10_holdings_percent": 60.0}
    f.market_stats = {"holder_count": 1000, "smart_wallets": 150}
    f.suspected_insider_holdings = 6e6
    f.insider_cluster_supply = 4e6
    f.effective_circulating_supply = 1e7
    f.contract_renounced = True
    f.contract_lp_burned = True
    f.alpha_raw = 90.0
    f.organic_raw = 31.0
    f.smart_money_raw = 60.0
    f.safety_raw = 50.0
    return f


def test_roundtrip_full_features(tmp_path):
    f = _full_features()
    d = serialize_features(f)
    f2 = deserialize_features(d)
    assert f2.token == f.token and f2.chain == f.chain
    assert f2.suspected_insider_holdings == 6e6
    assert f2.insider_cluster_supply == 4e6
    assert f2.effective_circulating_supply == 1e7
    assert f2.contract_renounced and f2.contract_lp_burned
    assert f2.okx_signals == {"okx_rug_pull_count": 1, "okx_top10_holdings_percent": 60.0}
    assert f2.market_stats == {"holder_count": 1000, "smart_wallets": 150}
    # nested dataclasses
    assert len(f2.funding_clusters) == 2
    assert f2.funding_clusters[0].sub_wallet == "S1"
    assert f2.funding_clusters[0].ts == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert f2.swaps[0].side == "BUY"
    assert f2.entry_events[0].buy_ts_minutes == -30.0
    assert f2.wallet_analytics[0].sniper_count == 3
    assert f2.wallet_analytics[0].suspected_insider_hold_rate == 0.5
    # raw weights preserved
    assert f2.alpha_raw == 90.0 and f2.organic_raw == 31.0


def test_write_and_load_ledger(tmp_path):
    path = str(tmp_path / "snap.json")
    f = _full_features()
    write_snapshot(path, token=f.token, chain=f.chain,
                   launch_ts=datetime.now(timezone.utc), features=f,
                   score={"risk_adjusted_alpha": 40.0},
                   ref_price=0.1, ref_mcap=1e6)
    # second append must not clobber the first
    f2 = _full_features()
    write_snapshot(path, token="SECONDTOKEN", chain="solana",
                   launch_ts=datetime.now(timezone.utc), features=f2)
    led = load_ledger(path)
    assert led["format"] == "sfc_memecoin_launch_snapshot_v1"
    assert len(led["records"]) == 2
    r0 = led["records"][0]
    assert r0["token"] == f.token
    assert r0["ref_price"] == 0.1
    assert r0["ref_mcap"] == 1e6
    assert r0["outcome"] is None
    assert r0["features"]["suspected_insider_holdings"] == 6e6
    # round-trip the stored record
    f_rt = deserialize_features(r0["features"])
    assert f_rt.token == f.token
    assert f_rt.okx_signals == f.okx_signals
    assert json.dumps(r0["features"])  # JSON-serializable
