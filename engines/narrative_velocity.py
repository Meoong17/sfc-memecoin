"""Narrative Velocity Engine (spec §6.12).

Measures the SPEED of narrative change, combined with on-chain confirmation
(cross-domain): Social up + DEX flow up + unique wallets up + liquidity up
together = high-velocity narrative, more meaningful than mentions alone.

Consumes EV-003 (social) + EV-001 (flow) via the Measurement Contract.

Spec example time-series: 09:00->120 | 10:00->190 | 11:00->340 | 12:00->720 | 13:00->1450
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NarrativeDomain:
    """One confirmation domain (social, dex flow, wallets, liquidity)."""
    name: str
    current: float = 0.0
    prev: float = 0.0

    @property
    def growth_rate(self) -> float:
        if self.prev == 0:
            return 0.0
        return (self.current - self.prev) / self.prev


@dataclass
class NarrativeInputs:
    token: str
    mention_series: list[float] = field(default_factory=list)  # per-time-slot mention counts
    domains: list[NarrativeDomain] = field(default_factory=list)  # cross-domain confirmation

    def series_growth_rate(self) -> float:
        """Acceleration across the mention time-series (last vs first non-zero)."""
        pts = [x for x in self.mention_series if x > 0]
        if len(pts) < 2:
            return 0.0
        return (pts[-1] - pts[0]) / pts[0]


@dataclass
class NarrativeResult:
    token: str
    velocity: float = 0.0            # 0..1
    velocity_label: str = "FLAT"
    mention_growth: float = 0.0
    cross_domain_confirmations: int = 0
    confirming_domains: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "velocity": round(self.velocity, 3),
            "velocity_label": self.velocity_label,
            "mention_growth": round(self.mention_growth, 2),
            "cross_domain_confirmations": self.cross_domain_confirmations,
            "confirming_domains": self.confirming_domains,
        }


# ILLUSTRATIVE thresholds (calibration doctrine).
HIGH_GROWTH = 1.0     # >100% series growth
CONFIRM_UP = 0.2      # domain growth >20% counts as confirming


class NarrativeVelocityEngine:
    """Computes narrative velocity with cross-domain confirmation."""

    def analyze(self, inp: NarrativeInputs) -> NarrativeResult:
        res = NarrativeResult(token=inp.token)
        res.mention_growth = inp.series_growth_rate()

        # cross-domain confirmation
        confirming = [d for d in inp.domains if d.growth_rate >= CONFIRM_UP]
        res.confirming_domains = [d.name for d in confirming]
        res.cross_domain_confirmations = len(confirming)

        # velocity: blend mention acceleration + cross-domain breadth
        velocity = 0.0
        if res.mention_growth > 0:
            velocity += min(1.0, res.mention_growth / 3.0) * 0.5
        velocity += min(1.0, len(confirming) / 3.0) * 0.5
        res.velocity = max(0.0, min(1.0, velocity))

        if res.velocity >= 0.7 or res.mention_growth >= 2.0:
            res.velocity_label = "ACCELERATING"
        elif res.velocity >= 0.4:
            res.velocity_label = "RISING"
        elif res.velocity > 0.0:
            res.velocity_label = "FLAT"
        elif res.mention_growth < -0.2:
            res.velocity_label = "DECLINING"
        else:
            res.velocity_label = "FLAT"
        return res
