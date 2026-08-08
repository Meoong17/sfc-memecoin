"""Test Dev DNA matcher + LARP detector (Phase 1)."""
import pytest

from engines.dev_dna import DevDNAMatcher
from engines.larp import LarpDetector, LarpSignals
from reputation.actor_reputation import ActorReputationDB


# ---- Dev DNA ----

def test_unknown_deployer_level_0():
    db = ActorReputationDB()
    m = DevDNAMatcher(db)
    r = m.match("unknown", "bsc")
    assert r.level == 0
    assert not r.is_suspicious


def test_known_safe_dev_capped_level_1():
    db = ActorReputationDB()
    db.register_dev("devGood", "bsc", launches=10, successful=8, rugged=1, lps_removed=0)
    m = DevDNAMatcher(db)
    r = m.match("devGood", "bsc")
    assert r.level <= 1
    assert not r.is_suspicious


def test_rug_history_escalates():
    db = ActorReputationDB()
    db.register_dev("devRug", "bsc", launches=6, rugged=4, lps_removed=3)
    m = DevDNAMatcher(db)
    r = m.match("devRug", "bsc")
    assert r.level >= 4
    assert r.is_suspicious


def test_full_rug_pattern_level_5():
    db = ActorReputationDB()
    db.register_dev("devBad", "bsc", launches=10, rugged=8, abandoned=2, lps_removed=6)
    m = DevDNAMatcher(db)
    r = m.match("devBad", "bsc")
    assert r.level == 5
    assert "rug_pattern_lp_removal" in r.reasons


def test_wallet_not_found_other_chain():
    db = ActorReputationDB()
    db.register_dev("devX", "solana", launches=5, rugged=4)
    m = DevDNAMatcher(db)
    assert m.match("devX", "bsc").level == 0


# ---- LARP ----

def test_clean_not_larp():
    d = LarpDetector()
    r = d.detect(LarpSignals())
    assert not r.is_larp
    assert r.larp_score == 0.0


def test_larp_with_multiple_signals():
    d = LarpDetector()
    s = LarpSignals(fake_dev_identity=True, stolen_artwork=True, no_original_contract=True)
    r = d.detect(s)
    assert r.is_larp
    assert r.larp_score >= 0.6
    assert "stolen_artwork" in r.signals


def test_single_weak_signal_not_larp():
    d = LarpDetector()
    s = LarpSignals(fresh_dev_wallet=True)
    r = d.detect(s)
    assert not r.is_larp


def test_larp_score_threshold_boundary():
    d = LarpDetector()
    # 0.30 + 0.35 = 0.65 >= 0.6 -> larp
    s = LarpSignals(fake_dev_identity=True, no_original_contract=True)
    assert d.detect(s).is_larp
