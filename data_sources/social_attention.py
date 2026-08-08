"""Social Attention producer (EV-003): mention velocity + author diversity.

Consumers (spec §3): Narrative Velocity, Social Bot.
Produces EV-003 as raw social metrics that downstream engines consume via the
Measurement Contract (never recomputed by consumers).

Phase 3: pure aggregation over raw mention records. Real platform ingestion
(Twitter/X, Telegram) wired later via same interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Mention:
    author_id: str
    text: str
    ts: datetime
    platform: str = "twitter"


@dataclass
class SocialSnapshot:
    """EV-003 evidence value for one token over a window."""
    token: str
    window_start: datetime
    window_end: datetime
    total_mentions: int = 0
    unique_authors: int = 0
    engagement_total: int = 0
    mentions_by_platform: dict[str, int] = field(default_factory=dict)
    author_age_days: dict[str, int] = field(default_factory=dict)  # author -> account age days
    mentions: list[Mention] = field(default_factory=list)

    @property
    def author_diversity(self) -> float:
        """Ratio unique authors / total mentions [0,1]; high = organic."""
        if self.total_mentions == 0:
            return 0.0
        return self.unique_authors / self.total_mentions

    @property
    def engagement_per_mention(self) -> float:
        if self.total_mentions == 0:
            return 0.0
        return self.engagement_total / self.total_mentions

    def summary(self) -> dict:
        return {
            "token": self.token,
            "total_mentions": self.total_mentions,
            "unique_authors": self.unique_authors,
            "author_diversity": round(self.author_diversity, 3),
            "engagement_per_mention": round(self.engagement_per_mention, 2),
            "mentions_by_platform": self.mentions_by_platform,
        }


def aggregate_mentions(token: str, mentions: list[Mention],
                       window_start: datetime, window_end: datetime,
                       *, author_age_days: dict[str, int] | None = None,
                       engagement_total: int = 0) -> SocialSnapshot:
    snap = SocialSnapshot(token=token, window_start=window_start, window_end=window_end)
    snap.mentions = list(mentions)
    snap.total_mentions = len(mentions)
    snap.unique_authors = len({m.author_id for m in mentions})
    snap.engagement_total = engagement_total
    snap.author_age_days = dict(author_age_days or {})
    for m in mentions:
        snap.mentions_by_platform[m.platform] = snap.mentions_by_platform.get(m.platform, 0) + 1
    return snap
