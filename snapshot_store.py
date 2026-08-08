"""Snapshot store for the predictive-edge test (score -> outcome, honestly).

The labeled datasets only carry GMGN-trending features in `note` strings, so a
score->outcome test on them can only use a historical PROXY of the core weights
(insider/OKX/funding path is absent). To run the real pipeline on real data at
the moment the model would actually decide, we must record a FULL TokenFeatures
snapshot (all live evidence: OKX, funding, market_stats, wallet analytics, ...)
at launch time, then backfill the OUTCOME later.

This module serializes / deserializes a TokenFeatures to/from JSON so the
pipeline can be re-run on stored evidence. Storing the features (not just the
score) keeps the ledger future-proof: if the formula changes, we can re-score
the same snapshots without re-fetching.

Design:
  - snapshot_store.serialize_features(f) -> dict   (JSON-safe)
  - snapshot_store.deserialize_features(d) -> TokenFeatures
  - snapshot_store.write_snapshot(path, token, chain, launch_ts, features, score)
  - snapshot_store.load_ledger(path) -> list of record dicts
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from data_sources.dex_flow import Swap
from data_sources.wallet_funding import FundingEdge
from engines.insider_intel import EntryEvent
from fetchers.gmgn import WalletAnalytics
from pipeline import TokenFeatures


def _ts_to_str(x: Any) -> Any:
    if isinstance(x, datetime):
        return x.isoformat()
    return x


def _ts_from_str(x: Any) -> Any:
    if isinstance(x, str) and "T" in x:
        try:
            return datetime.fromisoformat(x)
        except ValueError:
            return x
    return x


def _swap_to_dict(s: Swap) -> dict:
    return {"wallet": s.wallet, "side": s.side,
            "amount_token": s.amount_token, "amount_quote": s.amount_quote,
            "ts": _ts_to_str(s.ts), "pool": s.pool}


def _swap_from_dict(d: dict) -> Swap:
    return Swap(wallet=d.get("wallet", ""), side=d.get("side", ""),
                amount_token=d.get("amount_token", 0.0),
                amount_quote=d.get("amount_quote", 0.0),
                ts=_ts_from_str(d.get("ts")), pool=d.get("pool", ""))


def _edge_to_dict(e: FundingEdge) -> dict:
    return {"master_wallet": e.master_wallet, "sub_wallet": e.sub_wallet,
            "amount": e.amount, "ts": _ts_to_str(e.ts), "chain": e.chain}


def _edge_from_dict(d: dict) -> FundingEdge:
    return FundingEdge(master_wallet=d.get("master_wallet", ""),
                       sub_wallet=d.get("sub_wallet", ""),
                       amount=d.get("amount", 0.0),
                       ts=_ts_from_str(d.get("ts")),
                       chain=d.get("chain", ""))


def _entry_to_dict(e: EntryEvent) -> dict:
    return {"wallet": e.wallet, "buy_ts_minutes": e.buy_ts_minutes,
            "amount": e.amount}


def _entry_from_dict(d: dict) -> EntryEvent:
    return EntryEvent(wallet=d.get("wallet", ""),
                      buy_ts_minutes=d.get("buy_ts_minutes", 0.0),
                      amount=d.get("amount", 0.0))


_WALLET_KEYS = ["wallet", "chain", "sniper_count", "bundler_trader_amount_rate",
                "rat_trader_amount_rate", "suspected_insider_hold_rate",
                "fresh_wallet_rate", "win_rate", "early_entry_rate",
                "social_influence"]


def _ws_to_dict(w: WalletAnalytics) -> dict:
    return {k: getattr(w, k) for k in _WALLET_KEYS}


def _ws_from_dict(d: dict) -> WalletAnalytics:
    return WalletAnalytics(
        wallet=str(d.get("wallet", "")),
        chain=str(d.get("chain", "")),
        sniper_count=int(d.get("sniper_count", 0) or 0),
        bundler_trader_amount_rate=float(d.get("bundler_trader_amount_rate", 0.0)),
        rat_trader_amount_rate=float(d.get("rat_trader_amount_rate", 0.0)),
        suspected_insider_hold_rate=float(d.get("suspected_insider_hold_rate", 0.0)),
        fresh_wallet_rate=float(d.get("fresh_wallet_rate", 0.0)),
        win_rate=float(d.get("win_rate", 0.0)),
        early_entry_rate=float(d.get("early_entry_rate", 0.0)),
        social_influence=float(d.get("social_influence", 0.0)))


def serialize_features(f: TokenFeatures) -> dict:
    """TokenFeatures -> JSON-safe dict (all evidence preserved)."""
    return {
        "token": f.token,
        "chain": f.chain,
        "funding_clusters": [_edge_to_dict(e) for e in f.funding_clusters],
        "swaps": [_swap_to_dict(s) for s in f.swaps],
        "contract_risk_level": f.contract_risk_level,
        "contract_risk_score": f.contract_risk_score,
        "is_honeypot": f.is_honeypot,
        "deployer": f.deployer,
        "contract_sell_sellable": f.contract_sell_sellable,
        "contract_lp_locked_pct": f.contract_lp_locked_pct,
        "contract_lp_burned": f.contract_lp_burned,
        "contract_renounced": f.contract_renounced,
        "entry_events": [_entry_to_dict(e) for e in f.entry_events],
        "launch_minute": f.launch_minute,
        "info_expansion_minute": f.info_expansion_minute,
        "suspected_insider_holdings": f.suspected_insider_holdings,
        "effective_circulating_supply": f.effective_circulating_supply,
        "insider_cluster_supply": f.insider_cluster_supply,
        "mention_series": list(f.mention_series),
        "domains": list(f.domains),
        "wallet_analytics": [_ws_to_dict(w) for w in f.wallet_analytics],
        "okx_signals": dict(f.okx_signals),
        "market_stats": dict(f.market_stats),
        "alpha_raw": f.alpha_raw,
        "organic_raw": f.organic_raw,
        "safety_raw": f.safety_raw,
        "smart_money_raw": f.smart_money_raw,
    }


def deserialize_features(d: dict) -> TokenFeatures:
    """JSON-safe dict -> TokenFeatures (round-trip for re-scoring)."""
    f = TokenFeatures(token=d.get("token", ""), chain=d.get("chain", ""))
    f.funding_clusters = [_edge_from_dict(e) for e in d.get("funding_clusters", [])]
    f.swaps = [_swap_from_dict(s) for s in d.get("swaps", [])]
    f.contract_risk_level = d.get("contract_risk_level", "SAFE")
    f.contract_risk_score = d.get("contract_risk_score", 0.0)
    f.is_honeypot = d.get("is_honeypot", False)
    f.deployer = d.get("deployer", "")
    f.contract_sell_sellable = d.get("contract_sell_sellable", True)
    f.contract_lp_locked_pct = d.get("contract_lp_locked_pct", 0.0)
    f.contract_lp_burned = d.get("contract_lp_burned", False)
    f.contract_renounced = d.get("contract_renounced", False)
    f.entry_events = [_entry_from_dict(e) for e in d.get("entry_events", [])]
    f.launch_minute = d.get("launch_minute", 0.0)
    f.info_expansion_minute = d.get("info_expansion_minute", 0.0)
    f.suspected_insider_holdings = d.get("suspected_insider_holdings", 0.0)
    f.effective_circulating_supply = d.get("effective_circulating_supply", 0.0)
    f.insider_cluster_supply = d.get("insider_cluster_supply", 0.0)
    f.mention_series = list(d.get("mention_series", []))
    f.domains = list(d.get("domains", []))
    f.wallet_analytics = [_ws_from_dict(w) for w in d.get("wallet_analytics", [])]
    f.okx_signals = dict(d.get("okx_signals", {}))
    f.market_stats = dict(d.get("market_stats", {}))
    f.alpha_raw = d.get("alpha_raw", 50.0)
    f.organic_raw = d.get("organic_raw", 50.0)
    f.safety_raw = d.get("safety_raw", 50.0)
    f.smart_money_raw = d.get("smart_money_raw", 50.0)
    return f


def write_snapshot(path: str, *, token: str, chain: str, launch_ts: datetime,
                   features: TokenFeatures, score: dict | None = None,
                   ref_price: float | None = None,
                   ref_mcap: float | None = None) -> None:
    """Append one snapshot record to the ledger JSON file."""
    try:
        with open(path) as fh:
            ledger = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        ledger = {"format": "sfc_memecoin_launch_snapshot_v1", "records": []}
    ledger["records"].append({
        "token": token,
        "chain": chain,
        "launch_ts": launch_ts.isoformat(),
        "ref_price": ref_price,          # price at snapshot time (return base)
        "ref_mcap": ref_mcap,
        "features": serialize_features(features),
        "score": score or {},
        "outcome": None,          # backfilled later by backfill_outcomes.py
        "final_return_pct": None,
        "peak_return_pct": None,
        "days_observed": 0,
    })
    with open(path, "w") as fh:
        json.dump(ledger, fh, indent=2)


def load_ledger(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)
