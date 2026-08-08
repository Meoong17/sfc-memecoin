"""Test OKX Onchain OS fetcher (onchainos CLI interface, mocked _run)."""
import pytest

from fetchers.base import FetchError
from fetchers.okx import OkxFetcher, _f


def test_requires_all_three_creds(monkeypatch):
    monkeypatch.delenv("OKX_API_KEY", raising=False)
    monkeypatch.delenv("OKX_SECRET_KEY", raising=False)
    monkeypatch.delenv("OKX_PASSPHRASE", raising=False)
    with pytest.raises(ValueError):
        OkxFetcher()


def test_requires_passphrase(monkeypatch):
    monkeypatch.setenv("OKX_API_KEY", "k")
    monkeypatch.setenv("OKX_SECRET_KEY", "s")
    monkeypatch.delenv("OKX_PASSPHRASE", raising=False)
    with pytest.raises(ValueError):
        OkxFetcher()


def test_universe_maps_tokens(monkeypatch):
    f = OkxFetcher(cli="onchainos")
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {"ok": True, "data": [
        {"tokenAddress": "AAA", "name": "X", "createdTimestamp": "1786203423000",
         "tags": {"devHoldingsPercent": "44", "insidersPercent": "5"}},
    ]})
    toks = f.universe("solana", "NEW")
    assert len(toks) == 1
    assert toks[0]["tokenAddress"] == "AAA"


def test_token_dev_info_maps_rug(monkeypatch):
    f = OkxFetcher(cli="onchainos")
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {"ok": True, "data": {
        "devLaunchedInfo": {"rugPullCount": "3", "migratedCount": "1",
                            "goldenGemCount": "0", "totalTokens": "9"},
        "devHoldingInfo": {"devHoldingPercent": "12.5", "devAddress": "W",
                           "fundingAddress": "F"},
    }})
    d = f.token_dev_info("AAA")
    assert d["devLaunchedInfo"]["rugPullCount"] == "3"
    assert d["devHoldingInfo"]["devHoldingPercent"] == "12.5"


def test_insider_signals_maps_okx_fields(monkeypatch):
    f = OkxFetcher(cli="onchainos")
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {"ok": True, "data": {
        "devLaunchedInfo": {"rugPullCount": "2", "totalTokens": "5"},
        "devHoldingInfo": {"devHoldingPercent": "8.0", "devAddress": "W",
                           "fundingAddress": "F"},
    }})
    sig = f.insider_signals("AAA")
    assert sig["okx_rug_pull_count"] == 2.0
    assert sig["okx_dev_total_tokens"] == 5.0
    assert sig["okx_dev_holding_percent"] == 8.0
    assert sig["okx_dev_address"] == "W"
    assert sig["okx_funding_address"] == "F"


def test_tags_signals_maps_percentages(monkeypatch):
    f = OkxFetcher(cli="onchainos")
    token = {"tags": {"insidersPercent": "10", "snipersPercent": "44.38",
                      "bundlersPercent": "0", "top10HoldingsPercent": "89.5",
                      "devHoldingsPercent": "44.38", "freshWalletsPercent": "0",
                      "suspectedPhishingWalletPercent": "1.07",
                      "totalHolders": "6"}}
    sig = f.tags_signals(token)
    assert sig["okx_insiders_percent"] == 10.0
    assert sig["okx_snipers_percent"] == 44.38
    assert sig["okx_top10_holdings_percent"] == 89.5
    assert sig["okx_total_holders"] == 6.0


def test_token_tags_by_address_parses_details(monkeypatch):
    f = OkxFetcher(cli="onchainos")
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {"ok": True, "data": {
        "tokenAddress": "AAA", "name": "X", "tags": {
            "snipersPercent": "0.25", "top10HoldingsPercent": "15.34",
            "devHoldingsPercent": "0", "totalHolders": "170"}}})
    sig = f.token_tags_by_address("AAA")
    assert sig["okx_snipers_percent"] == 0.25
    assert sig["okx_top10_holdings_percent"] == 15.34
    assert sig["okx_total_holders"] == 170.0


def test_token_tags_by_address_null_data_degrades(monkeypatch):
    f = OkxFetcher(cli="onchainos")
    # non-mememump address returns ok:true with data:null
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {"ok": True, "data": None})
    assert f.token_tags_by_address("NOTAMEMEPUMP") == {}


def test_token_tags_by_address_failure_degrades(monkeypatch):
    f = OkxFetcher(cli="onchainos")
    def _boom(*a, **kw):
        raise FetchError("okx down")
    monkeypatch.setattr(f, "_run", _boom)
    assert f.token_tags_by_address("AAA") == {}


def test_f_helper_handles_bad_values():
    assert _f("12.5") == 12.5
    assert _f(None) == 0.0
    assert _f("") == 0.0
    assert _f("abc") == 0.0
