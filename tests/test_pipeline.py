"""Test Screening Pipeline orchestration (Phase 5)."""
from datetime import datetime, timedelta

from data_sources.dex_flow import Swap
from data_sources.wallet_funding import FundingEdge
from engines.insider_intel import EntryEvent
from pipeline import ScreeningPipeline, TokenFeatures, _contract_status


def _t(i):
    return datetime(2026, 8, 1) + timedelta(hours=i)


def _clean_features(token="TOK"):
    return TokenFeatures(
        token=token, chain="solana",
        funding_clusters=[FundingEdge("M1", "w1", 500, _t(0), "solana")],
        swaps=[Swap("w1", "BUY", 1000, 100, _t(0)), Swap("pub", "BUY", 1000, 100, _t(0))],
        contract_risk_level="SAFE", contract_risk_score=0.1, is_honeypot=False,
        deployer="devClean",
        entry_events=[EntryEvent("w1", -30.0, 100)],
        launch_minute=0.0, info_expansion_minute=10.0,
        suspected_insider_holdings=0.0, effective_circulating_supply=1.0,
        insider_cluster_supply=0.0,
        mention_series=[10, 20, 40],
        alpha_raw=80.0, organic_raw=75.0, safety_raw=85.0, smart_money_raw=78.0,
    )


def test_pipeline_scores_clean_token():
    pipe = ScreeningPipeline()
    s = pipe.score_token(_clean_features())
    assert s.admitted
    assert s.risk_adjusted_alpha > 0
    assert 0.0 < s.confidence <= 1.0
    assert set(s.outputs.keys()) >= {"security", "wallet_graph", "sybil", "insider",
                                     "absorption", "regime", "confluence", "alpha_risk",
                                     "confidence"}


def test_pipeline_blocks_honeypot():
    pipe = ScreeningPipeline()
    f = _clean_features("BAD")
    f.is_honeypot = True
    s = pipe.score_token(f)
    assert not s.admitted
    assert "honeypot" in s.hard_block_reasons


def test_pipeline_blocks_critical_contract():
    pipe = ScreeningPipeline()
    f = _clean_features("CRIT")
    f.contract_risk_level = "CRITICAL"
    s = pipe.score_token(f)
    assert not s.admitted
    assert "contract_risk_critical" in s.hard_block_reasons


def test_pipeline_insider_detection_lowers_alpha():
    pipe = ScreeningPipeline()
    clean = pipe.score_token(_clean_features("CLEAN"))
    risky = _clean_features("RISKY")
    risky.suspected_insider_holdings = 0.5
    risky.insider_cluster_supply = 0.5
    risky.entry_events = [EntryEvent("w1", -30.0, 100), EntryEvent("w2", -25.0, 100)]
    r = pipe.score_token(risky)
    assert r.insider_probability > clean.insider_probability
    assert r.risk_adjusted_alpha < clean.risk_adjusted_alpha


def test_pipeline_summary_shape():
    s = ScreeningPipeline().score_token(_clean_features())
    sm = s.summary()
    for k in ["token", "chain", "admitted", "risk_adjusted_alpha", "confidence",
              "insider_probability", "confluence_label", "regime", "outputs"]:
        assert k in sm


def _cf(token="TOK", **kw):
    base = dict(token=token, chain="solana", is_honeypot=False,
                contract_sell_sellable=True, contract_lp_locked_pct=0.0,
                contract_lp_burned=False, contract_renounced=False)
    base.update(kw)
    return TokenFeatures(**base)


def test_contract_status_verified():
    # renounced + LP burned/locked + not honeypot = VERIFIED (the secure badge)
    assert _contract_status(_cf(contract_renounced=True, contract_lp_burned=True)) == "VERIFIED"
    assert _contract_status(_cf(contract_renounced=True, contract_lp_locked_pct=0.9)) == "VERIFIED"


def test_contract_status_locked_when_lp_secure_not_renounced():
    assert _contract_status(_cf(contract_lp_burned=True)) == "LOCKED"
    assert _contract_status(_cf(contract_lp_locked_pct=0.7)) == "LOCKED"


def test_contract_status_risky_when_lp_unsecured():
    # sellable but LP unsecured (low lock, not burned)
    assert _contract_status(_cf(contract_lp_locked_pct=0.1)) == "RISKY"


def test_contract_status_critical_when_honeypot():
    assert _contract_status(_cf(is_honeypot=True)) == "CRITICAL"
    assert _contract_status(_cf(contract_sell_sellable=False)) == "CRITICAL"


def test_contract_status_unknown_when_no_facts():
    assert _contract_status(_cf()) == "UNKNOWN"


def test_score_token_exposes_contract_status():
    pipe = ScreeningPipeline()
    f = _clean_features("VERIF")
    f.contract_renounced = True
    f.contract_lp_burned = True
    s = pipe.score_token(f)
    assert s.contract_status == "VERIFIED"
    assert s.summary()["contract_status"] == "VERIFIED"
