"""Test GMGN fetcher (gmgn-cli interface, mocked _run)."""
import pytest

from engines.wallet_classify import ROLE_SMART_MONEY, WalletClassifier
from fetchers.gmgn import GmgnFetcher, WalletAnalytics, _f


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("GMGN_API_KEY", raising=False)
    with pytest.raises(ValueError):
        GmgnFetcher(api_key=None)


def test_token_security_maps_to_contract_facts(monkeypatch):
    f = GmgnFetcher(api_key="fake")
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {
        "address": "ADDR", "can_sell": 1, "can_not_sell": 0,
        "buy_tax": "3", "sell_tax": "5", "burn_ratio": "0.8",
        "renounced": True, "blacklist": 0,
        "lock_summary": {"lock_percent": "0.9"},
    })
    cf = f.token_security("ADDR", "solana")
    assert cf.address == "ADDR"
    assert cf.sell_sellable is True  # can_sell=1
    assert cf.buy_tax_pct == 3.0
    assert cf.sell_tax_pct == 5.0
    assert cf.lp_locked_pct == pytest.approx(0.1)  # 1 - 0.9 lock_percent
    assert cf.lp_burned is True  # burn_ratio 0.8 > 0.5


def test_token_security_honeypot_when_cannot_sell(monkeypatch):
    f = GmgnFetcher(api_key="fake")
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {
        "can_sell": 0, "can_not_sell": 1, "buy_tax": "0", "sell_tax": "0",
        "lock_summary": {"lock_percent": "0"},
    })
    cf = f.token_security("ADDR", "solana")
    assert cf.sell_sellable is False  # cannot sell -> honeypot-prone


def test_wallet_stats_maps_to_analytics(monkeypatch):
    f = GmgnFetcher(api_key="fake")
    import time
    monkeypatch.setattr(f, "_run", lambda *a, **kw: {"data": {
        "pnl_stat": {"winrate": "0.7"},
        "buy": 12, "sell": 4,
        "common": {"created_at": time.time() - 20 * 86400},  # 20 days old -> fresh
    }})
    a = f.wallet_stats("W1", "solana")
    assert a.win_rate == 0.7
    assert a.sniper_count == 12  # buys proxy
    assert a.early_entry_rate == pytest.approx(12 / 16)
    assert a.fresh_wallet_rate == 1.0  # < 30 days


def test_analytics_to_signals_drives_smart_money_classification():
    a = WalletAnalytics(wallet="W1", chain="solana", win_rate=0.7,
                        social_influence=0.2, early_entry_rate=0.3,
                        bundler_trader_amount_rate=0.2)
    sig = a.to_wallet_signals()
    r = WalletClassifier().classify(sig)
    assert r.role == ROLE_SMART_MONEY


def test_f_helper_handles_bad_values():
    assert _f("0.5") == 0.5
    assert _f(None) == 0.0
    assert _f("abc") == 0.0
