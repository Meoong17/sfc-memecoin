"""Social Bot / Artificial Attention Detection (spec §6.11).

Distinguishes ORGANIC social from ARTIFICIAL (bot-driven) before sentiment
enters the Alpha score. Consumes EV-003 (SocialSnapshot); does NOT recompute.

Key metric: Social Organicity Score. Artificial patterns show high mention
growth with flat author growth and low engagement-per-author.

Spec examples:
  MENCURIGAKAN: Mentions +600% | Followers +2% | Engagement +580%  -> bot-heavy
  ORGANIK:      Mentions +250% | Unique authors +180% | Engagement +230%
"""
from __future__ import annotations

from dataclasses import dataclass, field

from data_sources.social_attention import SocialSnapshot


@dataclass
class SocialOrganicityInputs:
    """Cross-window growth + account-age evidence."""
    snapshot: SocialSnapshot
    prev_mentions: int = 0
    prev_unique_authors: int = 0
    prev_engagement: int = 0
    prev_followers: int = 0
    cur_followers: int = 0
    # avg account age days of authors (low = fresh/bot-prone)
    avg_author_age_days: float = 0.0


@dataclass
class SocialOrganicityResult:
    token: str
    organicity_score: float = 0.0      # 0 (bot) .. 1 (organic)
    label: str = "UNKNOWN"             # ORGANIC / MIXED / ARTIFICIAL
    indicators: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "organicity_score": round(self.organicity_score, 3),
            "label": self.label,
            "reasons": self.reasons,
        }


# ILLUSTRATIVE thresholds (calibration doctrine).
ARTIFICIAL_MAX_ORGANICITY = 0.35
ORGANIC_MIN_ORGANICITY = 0.65


class SocialBotDetector:
    """Computes Social Organicity Score from EV-003 + growth deltas."""

    def detect(self, inp: SocialOrganicityInputs) -> SocialOrganicityResult:
        s = inp.snapshot
        res = SocialOrganicityResult(token=s.token)

        # 1. author diversity (organic signal)
        diversity = s.author_diversity

        # 2. engagement per unique author (bot accounts inflate count, low eng/author)
        eng_per_author = (s.engagement_total / s.unique_authors) if s.unique_authors else 0.0

        # 3. mention vs author growth divergence
        mention_growth = 0.0
        author_growth = 0.0
        if inp.prev_mentions > 0:
            mention_growth = (s.total_mentions - inp.prev_mentions) / inp.prev_mentions
        if inp.prev_unique_authors > 0:
            author_growth = (s.unique_authors - inp.prev_unique_authors) / inp.prev_unique_authors
        growth_alignment = 0.0
        if mention_growth > 0:
            # organic: author growth tracks mention growth; bot: mentions way ahead
            growth_alignment = min(1.0, author_growth / mention_growth) if mention_growth else 1.0

        # 4. account age (fresh wallets/authors = bot-prone)
        age_factor = min(1.0, inp.avg_author_age_days / 30.0)

        score = (0.30 * diversity + 0.25 * growth_alignment
                 + 0.25 * min(1.0, eng_per_author / 5.0) + 0.20 * age_factor)
        score = max(0.0, min(1.0, score))

        res.organicity_score = round(score, 3)
        res.indicators = {
            "author_diversity": round(diversity, 3),
            "growth_alignment": round(growth_alignment, 3),
            "engagement_per_author": round(eng_per_author, 2),
            "avg_author_age_days": round(inp.avg_author_age_days, 1),
        }

        if score <= ARTIFICIAL_MAX_ORGANICITY:
            res.label = "ARTIFICIAL"
            res.reasons.append("bot_driven_attention")
        elif score >= ORGANIC_MIN_ORGANICITY:
            res.label = "ORGANIC"
        else:
            res.label = "MIXED"

        return res
