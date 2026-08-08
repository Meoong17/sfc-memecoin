"""Outcome labeling schema for backtest.

Every token in the backtest gets one of three labels used across phases
(v5 §8, §10) to validate thresholds/formulas:
    - "rugged"   : rug pull / honeypot / dev dump / LP removal
    - "survived" : traded but never rugged; no collapse
    - "pumped"   : large sustained upside (for alpha validation)

Labeling must be data-driven (historical outcomes), NOT derived from the same
signals the model scores — otherwise it is circular and invalid for calibration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Outcome(str, Enum):
    RUGGED = "rugged"
    SURVIVED = "survived"
    PUMPED = "pumped"


@dataclass
class LabeledToken:
    """A token with an empirically-assigned outcome label."""
    token: str
    chain: str
    launch_ts: datetime
    outcome: Outcome
    peak_return_pct: float = 0.0        # max gain from launch
    final_return_pct: float = 0.0       # return at end of observation window
    days_observed: int = 0
    note: str = ""

    def summary(self) -> dict:
        return {
            "token": self.token,
            "chain": self.chain,
            "launch": self.launch_ts.isoformat(),
            "outcome": self.outcome.value,
            "peak_return_pct": self.peak_return_pct,
            "final_return_pct": self.final_return_pct,
            "days_observed": self.days_observed,
            "note": self.note,
        }


# Labeling rules — empirical, data-driven (thresholds here are ABOUT outcomes,
# separate from the ILLUSTRATIVE model thresholds in config/thresholds.py).

RUG_LP_REMOVAL = True        # LP removal -> rugged
RUG_MAX_DD_PCT = -60.0       # drawdown worse than this from peak -> rugged candidate
PUMP_MIN_PEAK_PCT = 300.0    # peak >= this AND sustained -> pumped
PUMP_MIN_HOLD_DAYS = 7       # sustained window (days) to count as "pumped" not flash
SURVIVE_NO_RUG_DAYS = 14     # no rug event within this window -> survived


def classify_outcome(
    *,
    lp_removed: bool,
    max_drawdown_pct: float,
    peak_return_pct: float,
    days_observed: int,
) -> Outcome:
    """Classify a token outcome from historical price/event facts.

    Order matters: rugged first, then pumped (only if sustained), else survived.
    """
    if lp_removed or max_drawdown_pct <= RUG_MAX_DD_PCT:
        return Outcome.RUGGED
    if peak_return_pct >= PUMP_MIN_PEAK_PCT and days_observed >= PUMP_MIN_HOLD_DAYS:
        return Outcome.PUMPED
    return Outcome.SURVIVED


@dataclass
class LabeledDataset:
    """Collection of labeled tokens for walk-forward validation."""
    samples: list[LabeledToken] = field(default_factory=list)

    def add(self, t: LabeledToken) -> None:
        self.samples.append(t)

    def counts(self) -> dict[str, int]:
        from collections import Counter
        c = Counter(t.outcome.value for t in self.samples)
        return dict(c)

    def by_outcome(self, outcome: Outcome) -> list[LabeledToken]:
        return [t for t in self.samples if t.outcome == outcome]

    def summary(self) -> dict:
        return {
            "n": len(self.samples),
            "counts": self.counts(),
        }
