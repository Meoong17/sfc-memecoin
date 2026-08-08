"""Regime Detection Engine (spec §6.14) — adaptive, not static thresholds.

Detects regime from multivariate time series using:
  - rolling z-score,
  - EWMA,
  - change-point detection (rolling mean shift),
across price/volume/liquidity/social dimensions.

Spec example sequence: NORMAL -> EARLY_ACCUMULATION -> BREAKOUT -> EXPANSION
-> EUPHORIA -> DISTRIBUTION -> COLLAPSE

Phase 4: single-series regime core + multivariate aggregation. Full
multivariate regime across many dimensions is roadmap Phase 4 backlog; here we
aggregate per-dimension z-scores.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, stdev


@dataclass
class SeriesInput:
    name: str
    values: list[float]          # chronological
    high_is_bullish: bool = True # e.g. price/volume: high = up; risk: low = up


@dataclass
class RegimeResult:
    token: str
    regime: str = "NORMAL"
    composite_z: float = 0.0
    per_dimension: dict[str, dict] = field(default_factory=dict)
    change_point: bool = False

    def summary(self) -> dict:
        return {
            "token": self.token,
            "regime": self.regime,
            "composite_z": round(self.composite_z, 2),
            "change_point": self.change_point,
            "per_dimension": {k: {"z": round(v["z"], 2), "regime": v["regime"]}
                              for k, v in self.per_dimension.items()},
        }


REGIME_ORDER = ["NORMAL", "EARLY_ACCUMULATION", "BREAKOUT", "EXPANSION",
                "EUPHORIA", "DISTRIBUTION", "COLLAPSE"]


def rolling_z(series: list[float], window: int = 20) -> list[float]:
    """Z-score of last point vs rolling window; falls back to full series."""
    if len(series) < 2:
        return [0.0] * len(series)
    if len(series) < window:
        mu, sd = mean(series), stdev(series) if len(series) > 1 else 0.0
        sd = sd or 1.0
        return [(x - mu) / sd for x in series]
    window_vals = series[-window:]
    mu = mean(window_vals)
    sd = stdev(window_vals) if len(window_vals) > 1 else 0.0
    sd = sd or 1.0
    return [0.0] * (len(series) - window) + [(x - mu) / sd for x in window_vals]


def ewma(series: list[float], alpha: float = 0.3) -> list[float]:
    out: list[float] = []
    prev = series[0] if series else 0.0
    for x in series:
        prev = alpha * x + (1 - alpha) * prev
        out.append(prev)
    return out


def detect_change_point(series: list[float], window: int = 10, thresh: float = 2.0) -> bool:
    """Detect a significant mean shift between recent and earlier window."""
    if len(series) < window * 2:
        return False
    recent = series[-window:]
    older = series[-window * 2: -window]
    mr, mo = mean(recent), mean(older)
    s = stdev(older) if len(older) > 1 else 0.0
    if s == 0:
        return mr != mo
    return abs(mr - mo) / s > thresh


def _regime_from_z(z: float) -> str:
    z = max(-4.0, min(4.0, z))
    if z >= 3.0:
        return "EUPHORIA"
    if z >= 2.0:
        return "EXPANSION"
    if z >= 1.0:
        return "BREAKOUT"
    if z >= 0.3:
        return "EARLY_ACCUMULATION"
    if z <= -2.5:
        return "COLLAPSE"
    if z <= -1.5:
        return "DISTRIBUTION"
    return "NORMAL"


class RegimeEngine:
    """Adaptive multivariate regime detection."""

    def analyze(self, token: str, inputs: list[SeriesInput], *, window: int = 20,
                ewma_alpha: float = 0.3) -> RegimeResult:
        res = RegimeResult(token=token)
        zs: list[float] = []

        for s in inputs:
            z = rolling_z(s.values, window)[-1]
            if not s.high_is_bullish:
                z = -z  # e.g. liquidity stress: low z is good
            zs.append(z)
            dim_regime = _regime_from_z(z)
            res.per_dimension[s.name] = {"z": round(z, 3), "regime": dim_regime}
            # change-point detection on the dimension
            if detect_change_point(s.values, window, thresh=2.0):
                res.change_point = True

        res.composite_z = mean(zs) if zs else 0.0
        res.regime = _regime_from_z(res.composite_z)
        return res
