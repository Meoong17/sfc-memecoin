"""Security Gate (spec §6.1) — Hard filter stage 1.

Inputs: contract risk (EV-002), honeypot status, actor reputation lookup,
LARP check. Outputs a structured decision with hard-block reasons, consumed
downstream by the veto hierarchy.

NOTE: honeypot_sim is the EV-002 producer. The gate consumes EV-002, it does
NOT re-run the simulation (Measurement Contract §3).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from evidence.contracts import ContractRiskInput
from reputation.actor_reputation import ActorReputationDB, ActorProfile


@dataclass
class SecurityDecision:
    token: str
    chain: str
    blocked: bool = False
    hard_reasons: list[str] = field(default_factory=list)
    contract_level: str = "UNKNOWN"
    actor: dict | None = None
    larp: bool = False
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "chain": self.chain,
            "blocked": self.blocked,
            "hard_reasons": self.hard_reasons,
            "contract_level": self.contract_level,
            "actor": self.actor,
            "larp": self.larp,
            "notes": self.notes,
        }


# ILLUSTRATIVE threshold (calibration doctrine) — see config/thresholds.py.
CONTRACT_CRITICAL_SCORE = 0.7


class SecurityGate:
    """First-stage hard filter: contract risk + honeypot + actor rep + LARP."""

    def __init__(self, reputation: ActorReputationDB | None = None,
                 enforce_hard: bool = True) -> None:
        self.reputation = reputation or ActorReputationDB()
        self.enforce_hard = enforce_hard

    def evaluate(self, token: str, chain: str, contract: ContractRiskInput,
                 *, deployer: str | None = None, larp: bool = False,
                 actor_profile: ActorProfile | None = None) -> SecurityDecision:
        d = SecurityDecision(token=token, chain=chain)
        d.contract_level = contract.risk_level
        d.larp = larp

        # --- EV-002 contract risk ---
        if contract.is_honeypot:
            d.blocked = True
            d.hard_reasons.append("honeypot")
        elif contract.risk_level == "CRITICAL" or contract.risk_score >= CONTRACT_CRITICAL_SCORE:
            d.blocked = True
            d.hard_reasons.append("contract_risk_critical")
        elif contract.risk_level == "RISKY":
            d.blocked = True
            d.hard_reasons.append("contract_risk_risky")

        # --- actor reputation lookup ---
        prof = actor_profile
        if prof is None and deployer is not None:
            prof = self.reputation.lookup(deployer, chain)
        if prof is not None:
            d.actor = prof.summary()
            if prof.is_hard_block_dev:
                d.blocked = True
                d.hard_reasons.append("actor_rep_hard_block")

        # --- LARP ---
        if larp:
            d.notes.append("larp")
            # LARP is a soft/penalty signal, not a hard block at this stage.

        return d
