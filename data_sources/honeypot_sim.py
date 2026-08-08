"""Honeypot simulation (spec §6.9) — Hard filter for BSC/EVM.

Producer of EV-002 (contract risk). Emulates a buy then sell to detect:
  - honeypot (can buy but cannot sell),
  - excessive buy/sell tax,
  - low/unlocked liquidity / LP removal,
  - missing multi-DEX liquidity.

The SECURITY GATE consumes EV-002; it does not re-run this simulation
(Measurement Contract §3).

Phase 1 uses a deterministic rule-based engine over on-chain contract facts.
Real EVM execution (eth_call simulate, Flashbots revm) is wired later.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from evidence.contracts import ContractRiskInput


@dataclass
class ContractFacts:
    """Raw contract facts obtained from on-chain scan (per chain)."""
    address: str
    chain: str
    buy_sellable: bool = True          # simulate: buy allowed?
    sell_sellable: bool = True         # simulate: sell allowed? (false -> honeypot)
    buy_tax_pct: float = 0.0
    sell_tax_pct: float = 0.0
    lp_locked_pct: float = 1.0         # fraction of LP locked [0,1]
    lp_burned: bool = False
    lp_total_removed: bool = False
    multi_dex_liquidity: bool = True   # listed on >1 DEX?
    dev_owns_majority_lp: bool = False
    notes: list[str] = field(default_factory=list)


# ILLUSTRATIVE thresholds (calibration doctrine).
TAX_REDLINE_PCT = 20.0
LP_LOCK_MIN_PCT = 0.5


def honeypot_risk(facts: ContractFacts) -> ContractRiskInput:
    """Compute EV-002 from contract facts. Returns consumed evidence."""
    findings: list[str] = []
    score = 0.0
    honeypot = False

    if not facts.sell_sellable or not facts.buy_sellable:
        honeypot = True
        score = 1.0
        findings.append("cannot_sell")

    # Tax redline
    max_tax = max(facts.buy_tax_pct, facts.sell_tax_pct)
    if max_tax >= TAX_REDLINE_PCT:
        findings.append(f"tax_excessive_{max_tax:.0f}pct")
        score = max(score, 0.85)
    elif max_tax >= 10.0:
        findings.append(f"tax_high_{max_tax:.0f}pct")
        score = max(score, 0.5)

    # LP risk
    if facts.lp_total_removed:
        findings.append("lp_removed")
        score = max(score, 0.95)
    if not facts.lp_locked_pct or facts.lp_locked_pct < LP_LOCK_MIN_PCT:
        findings.append("lp_unlocked")
        score = max(score, 0.6)
    if facts.dev_owns_majority_lp:
        findings.append("dev_majority_lp")
        score = max(score, 0.4)
    if not facts.multi_dex_liquidity:
        findings.append("single_dex_liquidity")

    # Level classification
    if honeypot:
        level = "CRITICAL"
    elif score >= 0.7:
        level = "CRITICAL"
    elif score >= 0.5:
        level = "RISKY"
    elif score >= 0.3:
        level = "WATCH"
    else:
        level = "SAFE"

    return ContractRiskInput(
        source="honeypot_sim",
        risk_score=round(min(1.0, score), 4),
        risk_level=level,
        is_honeypot=honeypot,
        findings=findings,
    )
