"""Veto hierarchy (spec §4): HARD / SOFT / PENALTY.

Hard veto -> token dropped.
Soft veto  -> token flagged, not hard-dropped (added in v5 for insider).
Penalty    -> weight penalty (added in v5 for insider).

Calibration doctrine: SOFT/PENALTY thresholds that are not yet calibrated
(`Threshold.calibrated=False`) are NOT enforced in production mode; they are
reported as `pending_calibration` only. Hard vetoes that do not depend on
uncalibrated thresholds ARE enforced.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config.thresholds import Threshold, get, uncalibrated_names


class VetoViolation(Exception):
    pass


@dataclass
class VetoDecision:
    """Result of evaluating the veto hierarchy for one token."""
    token: str
    hard_blocked: bool = False
    hard_reasons: list[str] = field(default_factory=list)
    soft_flags: list[str] = field(default_factory=list)
    penalties: list[str] = field(default_factory=list)
    # Production-enforceable only after calibration:
    pending_calibration: list[str] = field(default_factory=list)

    @property
    def admitted(self) -> bool:
        """Token passes pipeline unless hard-blocked."""
        return not self.hard_blocked

    def summary(self) -> dict:
        return {
            "token": self.token,
            "admitted": self.admitted,
            "hard_reasons": self.hard_reasons,
            "soft_flags": self.soft_flags,
            "penalties": self.penalties,
            "pending_calibration": self.pending_calibration,
        }


@dataclass
class VetoState:
    """Raw signals consumed by the veto evaluator."""
    # hard veto inputs
    rug_confirmed: bool = False
    honeypot_confirmed: bool = False
    actor_rep_hard_block: bool = False
    contract_risk_critical: bool = False
    # soft veto inputs (insider, v5)
    insider_probability: float = 0.0
    insider_hold_ratio: float = 0.0      # IHR in [0,1]
    exit_liquidity_level: str = "LOW"    # LOW / MED / HIGH
    insider_net_flow: str = "FLAT"       # BUY / SELL / FLAT
    public_net_flow: str = "FLAT"        # BUY / SELL / FLAT
    # penalty inputs (insider, v5)
    insider_cluster_exposure: str = "NONE"   # NONE / MODERATE / HIGH
    active_distribution: bool = False
    insider_timing_advantage: float = 0.0    # ITA score [0,1]
    funding_cluster_evidence: bool = False


def _ihr_class(ihr: float) -> str:
    if ihr < get("ihr_low_max").value:
        return "LOW"
    if ihr < get("ihr_moderate_max").value:
        return "MODERATE"
    if ihr < get("ihr_high_max").value:
        return "HIGH"
    return "CRITICAL"


class VetoEvaluator:
    """Enforces the HARD/SOFT/PENALTY hierarchy."""

    def __init__(self, enforce_pending_calibration: bool = False) -> None:
        # Production default is to NOT enforce uncalibrated thresholds.
        self.enforce_pending_calibration = enforce_pending_calibration
        self._uncal = set(uncalibrated_names())

    # --- hard vetoes (enforced always; no uncalibrated dependency) ---
    def _evaluate_hard(self, s: VetoState, d: VetoDecision) -> None:
        if s.rug_confirmed:
            d.hard_blocked = True
            d.hard_reasons.append("rug_confirmed")
        if s.honeypot_confirmed:
            d.hard_blocked = True
            d.hard_reasons.append("honeypot_confirmed")
        if s.actor_rep_hard_block:
            d.hard_blocked = True
            d.hard_reasons.append("actor_rep_hard_block")
        if s.contract_risk_critical:
            d.hard_blocked = True
            d.hard_reasons.append("contract_risk_critical")

    # --- soft vetoes (v5 insider) ---
    def _evaluate_soft(self, s: VetoState, d: VetoDecision) -> None:
        prob_th = get("insider_prob_soft_veto")
        ihr_crit = get("ihr_critical_min")
        # Soft veto 1: insider prob very high AND hold CRITICAL
        if (s.insider_probability > prob_th.value and _ihr_class(s.insider_hold_ratio) == "CRITICAL"):
            self._apply(prob_th, d, "insider_prob_high_and_hold_critical",
                        lambda: d.soft_flags.append("insider_prob_high_and_hold_critical"))
        # Soft veto 2: exit liquidity HIGH (insider selling while public buying)
        if s.exit_liquidity_level == "HIGH" and s.insider_net_flow == "SELL" and s.public_net_flow == "BUY":
            self._apply(Threshold("exit_liq", 0, False), d, "exit_liquidity_high",
                        lambda: d.soft_flags.append("exit_liquidity_high"))

    # --- penalties (v5 insider) ---
    def _evaluate_penalty(self, s: VetoState, d: VetoDecision) -> None:
        # Penalty 1: moderate insider exposure without active distribution
        if s.insider_cluster_exposure == "MODERATE" and not s.active_distribution:
            self._apply(Threshold("penalty_exposure", 0, False), d, "moderate_exposure_no_distribution",
                        lambda: d.penalties.append("moderate_exposure_no_distribution"))
        # Penalty 2: high timing advantage without funding-cluster proof (weak, watch only)
        if s.insider_timing_advantage > 0.8 and not s.funding_cluster_evidence:
            self._apply(Threshold("penalty_ita_no_cluster", 0, False), d, "high_ita_no_cluster",
                        lambda: d.penalties.append("high_ita_no_cluster"))

    def _apply(self, t: Threshold, d: VetoDecision, name: str, fn) -> None:
        """Enforce a soft/penalty threshold only if calibrated (or override on)."""
        if t.calibrated or self.enforce_pending_calibration:
            fn()
        else:
            d.pending_calibration.append(name)

    def evaluate(self, state: VetoState, token: str = "TKN") -> VetoDecision:
        d = VetoDecision(token=token)
        self._evaluate_hard(state, d)
        self._evaluate_soft(state, d)
        self._evaluate_penalty(state, d)
        return d
