"""Test Security Gate + Honeypot sim + Actor Reputation (Phase 1)."""
import pytest

from data_sources.honeypot_sim import ContractFacts, honeypot_risk
from engines.security_gate import SecurityGate, SecurityDecision
from evidence.contracts import ContractRiskInput
from reputation.actor_reputation import ActorProfile, ActorReputationDB


# ---- honeypot_sim (EV-002 producer) ----

def test_clean_contract_safe():
    f = ContractFacts(address="0x..", chain="bsc")
    r = honeypot_risk(f)
    assert r.risk_level == "SAFE"
    assert not r.is_honeypot
    assert r.risk_score < 0.3


def test_cannot_sell_is_honeypot():
    f = ContractFacts(address="0x..", chain="bsc", sell_sellable=False)
    r = honeypot_risk(f)
    assert r.is_honeypot
    assert r.risk_level == "CRITICAL"
    assert "cannot_sell" in r.findings


def test_excessive_tax():
    f = ContractFacts(address="0x..", chain="bsc", sell_tax_pct=30.0)
    r = honeypot_risk(f)
    assert r.risk_level == "CRITICAL"
    assert "tax_excessive_30pct" in r.findings


def test_lp_removed_critical():
    f = ContractFacts(address="0x..", chain="bsc", lp_total_removed=True)
    r = honeypot_risk(f)
    assert r.risk_level == "CRITICAL"
    assert "lp_removed" in r.findings


def test_lp_unlocked_risky():
    f = ContractFacts(address="0x..", chain="bsc", lp_locked_pct=0.1)
    r = honeypot_risk(f)
    assert r.risk_level == "RISKY"
    assert "lp_unlocked" in r.findings


# ---- actor reputation ----

def test_dev_score_and_hard_block():
    db = ActorReputationDB()
    p = db.register_dev("devA", "bsc", launches=17, successful=3, rugged=11,
                        abandoned=3, lps_removed=7)
    assert p.dev_score < 30
    assert p.is_hard_block_dev


def test_good_dev_not_hard_blocked():
    db = ActorReputationDB()
    p = db.register_dev("devGood", "bsc", launches=10, successful=8, rugged=1, lps_removed=0)
    assert p.dev_score >= 50
    assert not p.is_hard_block_dev


def test_lookup_by_wallet_chain():
    db = ActorReputationDB()
    db.register_dev("devA", "solana", launches=5, rugged=0)
    assert db.lookup("devA", "solana") is not None
    assert db.lookup("devA", "bsc") is None  # different chain


# ---- security gate ----

def test_gate_blocks_honeypot():
    gate = SecurityGate()
    ev = ContractRiskInput(source="honeypot_sim", risk_level="CRITICAL", is_honeypot=True)
    d = gate.evaluate("TOK", "bsc", ev)
    assert d.blocked
    assert "honeypot" in d.hard_reasons


def test_gate_blocks_critical_contract():
    gate = SecurityGate()
    ev = ContractRiskInput(source="honeypot_sim", risk_level="CRITICAL", risk_score=0.9)
    d = gate.evaluate("TOK", "bsc", ev)
    assert d.blocked
    assert "contract_risk_critical" in d.hard_reasons


def test_gate_blocks_actor_hard_block():
    gate = SecurityGate()
    ev = ContractRiskInput(source="honeypot_sim", risk_level="SAFE")
    prof = ActorProfile(wallet="devX", chain="bsc", role_tag="dev",
                        launches=20, rugged=18, lps_removed=15)
    d = gate.evaluate("TOK", "bsc", ev, actor_profile=prof)
    assert d.blocked
    assert "actor_rep_hard_block" in d.hard_reasons


def test_gate_uses_reputation_db_lookup():
    db = ActorReputationDB()
    db.register_dev("devY", "bsc", launches=25, rugged=22, lps_removed=20)
    gate = SecurityGate(reputation=db)
    ev = ContractRiskInput(source="honeypot_sim", risk_level="SAFE")
    d = gate.evaluate("TOK", "bsc", ev, deployer="devY")
    assert d.blocked
    assert d.actor is not None


def test_gate_admits_clean():
    gate = SecurityGate()
    ev = ContractRiskInput(source="honeypot_sim", risk_level="SAFE", risk_score=0.1)
    d = gate.evaluate("TOK", "bsc", ev, deployer="unknown_wallet")
    assert not d.blocked
    assert d.hard_reasons == []


def test_larp_not_hard_block_at_gate():
    gate = SecurityGate()
    ev = ContractRiskInput(source="honeypot_sim", risk_level="SAFE")
    d = gate.evaluate("TOK", "bsc", ev, larp=True)
    assert not d.blocked  # LARP is soft/penalty, not gate hard-block
    assert "larp" in d.notes
