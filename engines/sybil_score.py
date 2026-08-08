"""Sybil Score Engine (spec §6.4) — EV-021 consumer.

Measures holder QUALITY via the funding graph (common funding source, wallet
creation proximity, identical trade size & route, repeated DEX interaction),
not raw holder count. Detects when a large holder count is simulated by a
small number of funding wallets.

Spec example: 12,400 holder count -> 7,800 wallets funded by -> 12 wallets ->
Sybil Risk 81/100.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from data_sources.dex_flow import DexFlowSnapshot
from data_sources.wallet_funding import FundingGraph


@dataclass
class SybilInputs:
    """Additional evidence for sybil detection (beyond EV-021)."""
    holder_count: int = 0
    wallet_creation_proximity_ratio: float = 0.0   # fraction created close in time [0,1]
    identical_trade_size_ratio: float = 0.0        # fraction of identical-size trades [0,1]
    repeated_dex_ratio: float = 0.0                # fraction reusing identical DEX route [0,1]


@dataclass
class SybilResult:
    token: str
    sybil_risk: float = 0.0       # 0..100
    funding_wallets: int = 0
    holder_count: int = 0
    funded_ratio: float = 0.0
    indicators: dict[str, float] = field(default_factory=dict)

    @property
    def risk_level(self) -> str:
        if self.sybil_risk >= 70:
            return "HIGH"
        if self.sybil_risk >= 40:
            return "MODERATE"
        return "LOW"

    def summary(self) -> dict:
        return {
            "token": self.token,
            "sybil_risk": round(self.sybil_risk, 1),
            "risk_level": self.risk_level,
            "funding_wallets": self.funding_wallets,
            "holder_count": self.holder_count,
            "funded_ratio": round(self.funded_ratio, 3),
            "indicators": {k: round(v, 3) for k, v in self.indicators.items()},
        }


# ILLUSTRATIVE weights (calibration doctrine).
_W_FUNDED = 0.30   # share of holders funded by master wallets
_W_PROX = 0.25     # wallet creation proximity
_W_IDENT = 0.25    # identical trade size/route
_W_REPEAT = 0.20   # repeated DEX interaction


class SybilScoreEngine:
    """EV-021 consumer: holder-quality scoring to detect sybil simulation."""

    def __init__(self, funding: FundingGraph, flow: DexFlowSnapshot | None = None) -> None:
        self.funding = funding
        self.flow = flow

    def score(self, inputs: SybilInputs) -> SybilResult:
        res = SybilResult(token=self.funding.token)
        res.holder_count = inputs.holder_count
        res.funding_wallets = self.funding.cluster_count

        # Funded ratio: fraction of holders that belong to a funding cluster.
        cluster_subs = {sub for c in self.funding.clusters for sub in c.sub_wallets}
        res.funded_ratio = min(1.0, len(cluster_subs) / inputs.holder_count) if inputs.holder_count else 0.0

        # Composite sybil risk. More funding masters over fewer holders -> higher risk.
        density = 0.0
        if res.funding_wallets > 0 and inputs.holder_count > 0:
            # each master funding many sub-wallets => high density => sybil-prone
            density = min(1.0, len(cluster_subs) / (res.funding_wallets * 5))

        risk = (_W_FUNDED * res.funded_ratio
                + _W_PROX * inputs.wallet_creation_proximity_ratio
                + _W_IDENT * inputs.identical_trade_size_ratio
                + _W_REPEAT * inputs.repeated_dex_ratio
                + 0.15 * density)  # small density boost

        res.sybil_risk = round(min(100.0, risk * 100.0), 1)
        res.indicators = {
            "funded_ratio": res.funded_ratio,
            "wallet_creation_proximity": inputs.wallet_creation_proximity_ratio,
            "identical_trade_size": inputs.identical_trade_size_ratio,
            "repeated_dex": inputs.repeated_dex_ratio,
            "funding_density": density,
        }
        return res
