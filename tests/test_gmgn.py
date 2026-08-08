"""Test GMGN fetcher mapping (mocked)."""
import pytest

from engines.wallet_classify import ROLE_SMART_MONEY, WalletClassifier
from fetchers.gmgn import GmgnFetcher, WalletAnalytics


def test_requires_api_key(monkeypatch):
    monkeypatch.delenv("GMGN_API_KEY", raising=False)
    with pytest.raises(ValueError):
        GmgnFetcher(api_key=None)


def test_wallet_analytics_maps_fields(monkeypatch):
    f = GmgnFetcher(api_key="fake")
    monkeypatch.setattr(f, "_get", lambda url, **kw: {"data": {
        "sniper_count": 12,
        "bundler_trader_amount_rate": 0.6,
        "rat_trader_amount_rate": 0.3,
        "suspected_insider_hold_rate": 0.2,
        "fresh_wallet_rate": 0.1,
        "win_rate": 0.7,
        "early_entry_rate": 0.8,
        "social_influence": 0.4,
    }})
    a = f.wallet_analytics("W1", "solana")
    assert a.sniper_count == 12
    assert a.bundler_trader_amount_rate == 0.6
    assert a.win_rate == 0.7


def test_wallet_analytics_to_signals_drives_classification():
    a = WalletAnalytics(wallet="W1", chain="solana", win_rate=0.7,
                        social_influence=0.2, early_entry_rate=0.3,
                        bundler_trader_amount_rate=0.2)
    sig = a.to_wallet_signals()
    # high win rate, low freq -> smart money (if no higher-precedence signal)
    clf = WalletClassifier()
    r = clf.classify(sig)
    assert r.role == ROLE_SMART_MONEY


def test_wallet_analytics_coordinated_bundler():
    a = WalletAnalytics(wallet="W1", chain="solana",
                        bundler_trader_amount_rate=0.8,
                        early_entry_rate=0.9, win_rate=0.5)
    sig = a.to_wallet_signals()
    assert sig.buys_coordinated is True
    assert sig.buy_before_info_expansion is True


def test_summary_shape():
    a = WalletAnalytics(wallet="W1", chain="solana", sniper_count=5)
    s = a.summary()
    assert s["wallet"] == "W1"
    assert "sniper_count" in s and "win_rate" in s
