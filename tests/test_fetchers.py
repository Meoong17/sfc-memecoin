"""Test fetcher layer: base HTTP + DexScreener mapping + Helius transfer extraction.

Network calls are mocked; tests verify mapping logic, rate-limit/retry/cache
behavior, and dataclass construction — not live API availability.
"""
import json

import pytest

from data_sources.wallet_funding import FundingEdge
from fetchers.base import BaseFetcher, FetchError, _TokenBucket
from fetchers.dex_screener import DexScreenerFetcher
from fetchers.helius import HeliusRpcFetcher


# --- token bucket ---

def test_token_bucket_never_negative():
    tb = _TokenBucket(per_sec=1000)
    for _ in range(5):
        tb.acquire()  # should not sleep/error
    assert tb.tokens >= 0.0


# --- base cache ---

def test_cache_roundtrip(tmp_path):
    class F(BaseFetcher):
        def run(self, key, val):
            self._cache_put(key, val)
            return self._cache_get(key)
    f = F(cache_dir=str(tmp_path))
    assert f.run("k1", {"a": 1}) == {"a": 1}


# --- DexScreener mapping (mocked) ---

class _MockDex(BaseFetcher):
    def __init__(self, **kw):
        super().__init__(source="dex_api", **kw)
        self._mock = None
    def _get(self, url, **kw):
        return self._mock


def test_dex_profiles_map_to_token_market_info(monkeypatch):
    f = DexScreenerFetcher(cache_ttl=0)
    monkeypatch.setattr(f, "_get", lambda url, **kw: [
        {"tokenAddress": "addr1", "chainId": "solana", "symbol": "TKN",
         "name": "Token", "volume": {"h24": 1234.5}},
    ])
    out = f.token_profiles(limit=5)
    assert len(out) == 1
    assert out[0].address == "addr1"
    assert out[0].volume_24h == 1234.5
    assert out[0].is_dex_screener_profile


def test_dex_detail_picks_best_liquidity_pair(monkeypatch):
    f = DexScreenerFetcher(cache_ttl=0)
    monkeypatch.setattr(f, "_get", lambda url, **kw: {"pairs": [
        {"chainId": "solana", "baseToken": {"symbol": "A"}, "priceUsd": "0.5",
         "volume": {"h24": "100"}, "liquidity": {"usd": "500"}},
        {"chainId": "solana", "baseToken": {"symbol": "B"}, "priceUsd": "0.9",
         "volume": {"h24": "900"}, "liquidity": {"usd": "9000"}},
    ]})
    d = f.token_detail("addr", "solana")
    assert d is not None
    assert d.symbol == "B"  # higher liquidity pair chosen
    assert d.price_usd == 0.9


def test_dex_detail_no_pairs_returns_none(monkeypatch):
    f = DexScreenerFetcher(cache_ttl=0)
    monkeypatch.setattr(f, "_get", lambda url, **kw: {"pairs": []})
    assert f.token_detail("addr") is None


# --- Helius transfer extraction ---

def _parsed_tx(src, dst, amount, mint, sig):
    return {
        "meta": {"err": None, "innerInstructions": []},
        "transaction": {
            "signatures": [sig],
            "message": {"instructions": [
                {"program": "spl-token", "parsed": {
                    "type": "transferChecked",
                    "info": {"source": src, "destination": dst, "mint": mint,
                             "tokenAmount": {"amount": str(amount)}},
                }},
            ]},
        },
    }


def test_helius_extract_transfers_from_parsed_instructions():
    f = HeliusRpcFetcher(api_key="fake")
    tx = _parsed_tx("SRC", "DST", 100.0, "MINT", "SIG1")
    out = f._extract_transfers(tx)
    assert len(out) == 1
    assert out[0]["source"] == "SRC"
    assert out[0]["destination"] == "DST"
    assert out[0]["amount"] == 100.0
    assert out[0]["mint"] == "MINT"


def test_helius_skips_failed_tx():
    f = HeliusRpcFetcher(api_key="fake")
    tx = {"meta": {"err": {"InstructionError": [0, 0]}, "innerInstructions": []}}
    assert f._extract_transfers(tx) == []


def test_helius_requires_api_key(monkeypatch):
    monkeypatch.delenv("HELIUS_API_KEY", raising=False)
    with pytest.raises(ValueError):
        HeliusRpcFetcher(api_key=None)


def test_helius_fetch_funding_edges_integration(monkeypatch):
    """End-to-end mocked: signature fetch + parse -> FundingEdge list."""
    f = HeliusRpcFetcher(api_key="fake")
    # mock get_signatures and get_parsed_transaction
    monkeypatch.setattr(f, "get_signatures",
                        lambda addr, **kw: [{"signature": "S1"}, {"signature": "S2"}])
    monkeypatch.setattr(f, "get_parsed_transaction", lambda sig: _parsed_tx("MASTER", "SUB", 50.0, "MINT", sig))
    edges = f.fetch_funding_edges("MASTER", token_mint="MINT")
    assert isinstance(edges, list)
    assert len(edges) == 2  # both sigs (S1,S2) yield a MASTER->SUB transfer
    e = edges[0]
    assert isinstance(e, FundingEdge)
    assert e.master_wallet == "MASTER"
    assert e.sub_wallet == "SUB"  # correct receiver from parsed destination
