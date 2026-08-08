"""Test Wallet Classification Engine (Phase 2, 11-role taxonomy)."""
from engines.wallet_classify import (
    ROLE_BUNDLER, ROLE_DEV, ROLE_INSIDER, ROLE_KOL, ROLE_MM, ROLE_PUBLIC,
    ROLE_SMART_MONEY, ROLE_SNIPER, ROLE_SYBIL, ROLE_UNKNOWN, WalletClassifier,
    WalletSignals,
)


def _sig(**kw):
    base = dict(wallet="W", in_organic_holder_set=True)
    base.update(kw)
    return WalletSignals(**base)


c = WalletClassifier()


def test_dev():
    assert c.classify(_sig(is_deployer=True)).role == ROLE_DEV


def test_insider_early_entry():
    r = c.classify(_sig(buy_before_info_expansion=True, entry_lead_seconds=600.0))
    assert r.role == ROLE_INSIDER


def test_sybil():
    r = c.classify(_sig(flagged_sybil=True, in_organic_holder_set=False))
    assert r.role == ROLE_SYBIL


def test_bundler_coordinated_launch():
    r = c.classify(_sig(buys_coordinated=True, in_funding_cluster=True,
                        first_buy_at_launch_ms=500.0))
    assert r.role == ROLE_BUNDLER


def test_sniper_launch_buy():
    r = c.classify(_sig(first_buy_at_launch_ms=1000.0))
    assert r.role == ROLE_SNIPER


def test_kol():
    r = c.classify(_sig(high_social_influence=0.9))
    assert r.role == ROLE_KOL


def test_smart_money():
    r = c.classify(_sig(high_win_rate=0.7, high_frequency=5.0))
    assert r.role == ROLE_SMART_MONEY


def test_market_maker_high_freq():
    r = c.classify(_sig(high_frequency=100.0))
    assert r.role == ROLE_MM


def test_public_organic():
    r = c.classify(_sig())
    assert r.role == ROLE_PUBLIC


def test_unknown_no_organic():
    r = c.classify(_sig(in_organic_holder_set=False))
    assert r.role == ROLE_UNKNOWN


def test_precedence_dev_over_everything():
    r = c.classify(_sig(is_deployer=True, flagged_sybil=True, buys_coordinated=True,
                        buy_before_info_expansion=True))
    assert r.role == ROLE_DEV


def test_all_roles_cover_11():
    from engines.wallet_classify import ALL_ROLES
    assert len(ALL_ROLES) == 11
