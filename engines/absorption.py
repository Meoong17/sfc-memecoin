"""Absorption Engine (spec §6.13).

Detects strong demand absorbed with relatively small price response. Neutral
label ("ABSORPTION DETECTED"), NOT an accumulation claim — the Regime Engine
judges consistency with real accumulation (spec v4/v5 doctrine).

Plus factors: Demand, Liquidity, Smart Money, Holder Growth, Buy Pressure, Social
Minus factors: Price Response, Whale Selling, Liquidity Stress, Insider Supply
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AbsorptionInputs:
    # plus factors (0..1, higher = more demand)
    demand: float = 0.0
    liquidity: float = 0.0
    smart_money: float = 0.0
    holder_growth: float = 0.0
    buy_pressure: float = 0.0
    social_attention: float = 0.0
    # minus factors (0..1, higher = more supply/response that works against absorption)
    price_response: float = 0.0
    whale_selling: float = 0.0
    liquidity_stress: float = 0.0
    insider_supply: float = 0.0


@dataclass
class AbsorptionResult:
    token: str
    absorption_score: float = 0.0    # 0..1
    absorption_detected: bool = False
    demand_index: float = 0.0
    supply_index: float = 0.0
    detail: dict[str, float] = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "absorption_score": round(self.absorption_score, 3),
            "absorption_detected": self.absorption_detected,
            "demand_index": round(self.demand_index, 3),
            "supply_index": round(self.supply_index, 3),
        }


# ILLUSTRATIVE threshold (calibration doctrine).
ABSORPTION_DETECT_THRESHOLD = 0.6


class AbsorptionEngine:
    """Computes demand/supply balance and absorption signal."""

    def compute(self, token: str, inp: AbsorptionInputs) -> AbsorptionResult:
        r = AbsorptionResult(token=token)
        # demand = mean of plus factors; supply = mean of minus factors
        r.demand_index = (inp.demand + inp.liquidity + inp.smart_money
                          + inp.holder_growth + inp.buy_pressure + inp.social_attention) / 6.0
        r.supply_index = (inp.price_response + inp.whale_selling
                          + inp.liquidity_stress + inp.insider_supply) / 4.0

        # Absorption = strong demand absorbed by weak price response.
        # score is high when demand is high relative to supply.
        net = r.demand_index - r.supply_index
        r.absorption_score = max(0.0, min(1.0, net))
        r.absorption_detected = r.absorption_score >= ABSORPTION_DETECT_THRESHOLD
        r.detail = {
            "demand_index": r.demand_index,
            "supply_index": r.supply_index,
            "net": round(net, 3),
        }
        return r
