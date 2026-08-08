"""LARP detection (spec §6.1, roadmap Phase 1).

LARP = a project that fakes legitimacy (fake dev identity, copied artwork/
narrative, bot-driven presence) to look real. This module produces a boolean +
confidence LARP flag consumed by the security gate as a soft/penalty signal
(spec: LARP is not a hard block; it feeds veto hierarchy).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LarpSignals:
    """Raw signals a project can exhibit that suggest LARP."""
    fake_dev_identity: bool = False        # dev not verifiable / stolen identity
    stolen_artwork: bool = False           # reused/scraped art across launches
    copied_narrative: bool = False         # narrative text copied verbatim
    bot_social_presence: bool = False      # social growth driven by bots
    no_original_contract: bool = False     # copied existing token contract
    fresh_dev_wallet: bool = False         # wallet created right before launch
    notes: list[str] = field(default_factory=list)


@dataclass
class LarpResult:
    is_larp: bool = False
    larp_score: float = 0.0                # 0..1
    signals: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "is_larp": self.is_larp,
            "larp_score": round(self.larp_score, 3),
            "signals": self.signals,
        }


# ILLUSTRATIVE threshold (calibration doctrine).
LARP_SCORE_THRESHOLD = 0.6


class LarpDetector:
    """Rule-based LARP detection from signals."""

    def detect(self, signals: LarpSignals) -> LarpResult:
        weights = {
            "fake_dev_identity": 0.30,
            "stolen_artwork": 0.25,
            "copied_narrative": 0.20,
            "bot_social_presence": 0.25,
            "no_original_contract": 0.35,
            "fresh_dev_wallet": 0.20,
        }
        score = 0.0
        present: list[str] = []
        for name, w in weights.items():
            if getattr(signals, name):
                score += w
                present.append(name)
        score = min(1.0, score)
        return LarpResult(
            is_larp=score >= LARP_SCORE_THRESHOLD,
            larp_score=round(score, 3),
            signals=present,
        )
