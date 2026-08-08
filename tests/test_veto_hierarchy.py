"""Test veto hierarchy (spec §4) incl. calibration-gating of SOFT/PENALTY thresholds."""
import pytest

from engines.veto import VetoEvaluator, VetoState


def _default_state(**kw) -> VetoState:
    base = VetoState()
    for k, v in kw.items():
        setattr(base, k, v)
    return base


def test_hard_veto_blocks():
    ev = VetoEvaluator()
    for field in ["rug_confirmed", "honeypot_confirmed", "actor_rep_hard_block", "contract_risk_critical"]:
        d = ev.evaluate(_default_state(**{field: True}))
        assert not d.admitted
        assert field in d.hard_reasons


def test_clean_token_admitted():
    ev = VetoEvaluator()
    d = ev.evaluate(VetoState())
    assert d.admitted
    assert d.hard_reasons == []
    assert d.soft_flags == []
    assert d.penalties == []


def test_soft_veto_pending_calibration_by_default():
    """Production: uncalibrated insider thresholds are NOT enforced, only reported."""
    ev = VetoEvaluator()
    # insider prob 0.9 > 0.80 AND hold 0.5 -> CRITICAL
    d = ev.evaluate(_default_state(insider_probability=0.9, insider_hold_ratio=0.5))
    assert d.admitted  # not blocked
    assert d.soft_flags == []  # not enforced yet
    assert "insider_prob_high_and_hold_critical" in d.pending_calibration


def test_soft_veto_enforced_when_override():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(insider_probability=0.9, insider_hold_ratio=0.5))
    assert d.admitted  # soft veto never hard-blocks
    assert "insider_prob_high_and_hold_critical" in d.soft_flags


def test_soft_veto_not_triggered_when_hold_not_critical():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    # prob high but hold 0.03 -> LOW, not CRITICAL
    d = ev.evaluate(_default_state(insider_probability=0.9, insider_hold_ratio=0.03))
    assert "insider_prob_high_and_hold_critical" not in d.soft_flags


def test_exit_liquidity_high():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(exit_liquidity_level="HIGH", insider_net_flow="SELL", public_net_flow="BUY"))
    assert "exit_liquidity_high" in d.soft_flags


def test_exit_liquidity_requires_sell_against_buy():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(exit_liquidity_level="HIGH", insider_net_flow="BUY", public_net_flow="BUY"))
    assert "exit_liquidity_high" not in d.soft_flags


def test_penalty_moderate_exposure_no_distribution():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(insider_cluster_exposure="MODERATE", active_distribution=False))
    assert "moderate_exposure_no_distribution" in d.penalties


def test_penalty_exposure_suppressed_by_distribution():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(insider_cluster_exposure="MODERATE", active_distribution=True))
    assert "moderate_exposure_no_distribution" not in d.penalties


def test_penalty_high_ita_no_cluster():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(insider_timing_advantage=0.9, funding_cluster_evidence=False))
    assert "high_ita_no_cluster" in d.penalties


def test_penalty_ita_with_cluster_suppressed():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(insider_timing_advantage=0.9, funding_cluster_evidence=True))
    assert "high_ita_no_cluster" not in d.penalties


def test_penalty_also_calibration_gated():
    ev = VetoEvaluator()  # production default
    d = ev.evaluate(_default_state(insider_cluster_exposure="MODERATE", active_distribution=False))
    assert d.penalties == []
    assert "moderate_exposure_no_distribution" in d.pending_calibration


def test_hard_block_coupled_with_soft_is_still_blocked():
    ev = VetoEvaluator(enforce_pending_calibration=True)
    d = ev.evaluate(_default_state(rug_confirmed=True, insider_probability=0.9, insider_hold_ratio=0.5))
    assert not d.admitted
    assert "rug_confirmed" in d.hard_reasons
