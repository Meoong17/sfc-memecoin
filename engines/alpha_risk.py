"""Alpha / Risk Engine (spec §6.15, §8) — output dimensions + Risk-Adjusted Alpha.

Produces the core 0-100 scores:
  - Alpha        : raw opportunity potential
  - Organic      : quality of demand
  - Safety       : structural safety
  - Smart Money  : quality of wallet flow
  - Risk-Adjusted Alpha: Alpha discounted by downside risk (incl. insider
    distribution & exit liquidity risk — v5 addition, spec §8)

Weights/penalties are ILLUSTRATIVE (calibration doctrine, docs/CALIBRATION.md).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engines.insider_intel import InsiderResult
from engines.sybil_score import SybilResult


@dataclass
class AlphaInputs:
    """Sub-score inputs (each precomputed by prior engines)."""
    alpha: float = 0.0              # raw 0-100
    organic: float = 0.0            # 0-100
    safety: float = 0.0             # 0-100
    smart_money: float = 0.0        # 0-100
    # insider downside (v5)
    insider: InsiderResult | None = None
    sybil: SybilResult | None = None


@dataclass
class AlphaResult:
    alpha: float = 0.0
    organic: float = 0.0
    safety: float = 0.0
    smart_money: float = 0.0
    risk_adjusted_alpha: float = 0.0
    risk_penalty: float = 0.0      # fraction of alpha removed [0,1]
    downside_factors: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "alpha": round(self.alpha, 1),
            "organic": round(self.organic, 1),
            "safety": round(self.safety, 1),
            "smart_money": round(self.smart_money, 1),
            "risk_adjusted_alpha": round(self.risk_adjusted_alpha, 1),
            "risk_penalty": round(self.risk_penalty, 3),
            "downside_factors": self.downside_factors,
        }


# ILLUSTRATIVE penalty weights (calibration doctrine).
_EXIT_LIQ_PENALTY = {"LOW": 0.0, "MED": 0.15, "HIGH": 0.30}
_IHR_PENALTY = {"LOW": 0.0, "MODERATE": 0.10, "HIGH": 0.20, "CRITICAL": 0.30}
_SYBIL_PENALTY = 0.15
_DISTRIBUTION_PENALTY = 0.15
# OKX dev-reputation downside (serial rugger / dev sold-off / coordination),
# separate from IHR/exit so it discounts without double-counting.
_DEV_REP_PENALTY = {"LOW": 0.0, "MED": 0.15, "HIGH": 0.30}


class AlphaRiskEngine:
    """Computes raw scores + Risk-Adjusted Alpha with downside discount."""

    def compute(self, inp: AlphaInputs) -> AlphaResult:
        res = AlphaResult(
            alpha=inp.alpha, organic=inp.organic, safety=inp.safety,
            smart_money=inp.smart_money,
        )
        penalty = 0.0

        # Insider downside (v5): exit liquidity + IHR + distribution
        if inp.insider is not None:
            penalty += _EXIT_LIQ_PENALTY.get(inp.insider.exit_liquidity_risk, 0.0)
            penalty += _IHR_PENALTY.get(inp.insider.ihr_class, 0.0)
            if inp.insider.insider_distribution:
                penalty += _DISTRIBUTION_PENALTY
                res.downside_factors.append("insider_distribution")
            if inp.insider.exit_liquidity_risk == "HIGH":
                res.downside_factors.append("exit_liquidity_high")
            if inp.insider.ihr_class in ("HIGH", "CRITICAL"):
                res.downside_factors.append(f"insider_hold_{inp.insider.ihr_class}")
            # OKX dev-reputation downside (serial rugger / dev sold-off / coord)
            dev_pen = _DEV_REP_PENALTY.get(inp.insider.dev_reputation_risk, 0.0)
            penalty += dev_pen
            if dev_pen > 0:
                res.downside_factors.append(
                    f"okx_dev_reputation_{inp.insider.dev_reputation_risk}")

        # Sybil downside
        if inp.sybil is not None and inp.sybil.risk_level == "HIGH":
            penalty += _SYBIL_PENALTY
            res.downside_factors.append("sybil_high")

        res.risk_penalty = min(1.0, penalty)
        res.risk_adjusted_alpha = max(0.0, inp.alpha * (1.0 - res.risk_penalty))
        return res
