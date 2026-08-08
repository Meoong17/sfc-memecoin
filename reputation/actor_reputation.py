"""Actor Reputation Network — merged dev + insider profiles (spec §6.10).

One schema for dev wallets and insider wallets, so there is no second source of
truth. Phase 1 scope: read/lookup + basic profile; reputation computation wired
to measurement contract evidence in later phases.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ActorProfile:
    """Reputation profile for a wallet (dev, insider, smart money, etc.)."""
    wallet: str
    chain: str
    role_tag: str = "unknown"            # dev / insider / smart_money / ...
    launches: int = 0
    tokens_entered: int = 0
    successful: int = 0
    rugged: int = 0
    abandoned: int = 0
    median_entry_lead: float | None = None   # minutes, insider/sniper
    profitability: float | None = None
    win_rate: float | None = None
    avg_hold_time: float | None = None
    distribution_behavior: str = "UNKNOWN"   # post-entry sell pattern
    common_funders: int = 0
    cluster_id: str | None = None
    confidence: float = 0.5                  # profile reliability [0,1]
    lps_removed: int = 0

    @property
    def dev_score(self) -> int:
        """0-100 dev reputation (higher = safer). Spec §6.10 example: 8/100 -> HARD BLOCK."""
        if self.launches == 0:
            return 50
        success_ratio = self.successful / self.launches
        rugged_penalty = (self.rugged / self.launches) * 60
        lp_penalty = self.lps_removed * 8
        score = 50 + (success_ratio * 50) - rugged_penalty - lp_penalty
        return max(0, min(100, int(round(score))))

    @property
    def is_hard_block_dev(self) -> bool:
        """Dev with overwhelmingly bad record -> HARD BLOCK (spec §6.10 example)."""
        return self.dev_score < 30 and self.launches >= 3

    def summary(self) -> dict:
        return {
            "wallet": self.wallet,
            "chain": self.chain,
            "role_tag": self.role_tag,
            "launches": self.launches,
            "rugged": self.rugged,
            "successful": self.successful,
            "dev_score": self.dev_score,
            "is_hard_block_dev": self.is_hard_block_dev,
            "confidence": self.confidence,
        }


class ActorReputationDB:
    """In-memory profile store (Phase 1; SQLite/PostgreSQL later)."""

    def __init__(self) -> None:
        self._profiles: dict[str, ActorProfile] = {}

    def upsert(self, profile: ActorProfile) -> None:
        key = f"{profile.chain}:{profile.wallet}"
        self._profiles[key] = profile

    def lookup(self, wallet: str, chain: str) -> ActorProfile | None:
        return self._profiles.get(f"{chain}:{wallet}")

    def register_dev(self, wallet: str, chain: str, *, launches, successful=0,
                     rugged=0, abandoned=0, lps_removed=0, confidence=0.5) -> ActorProfile:
        p = ActorProfile(
            wallet=wallet, chain=chain, role_tag="dev",
            launches=launches, successful=successful, rugged=rugged,
            abandoned=abandoned, lps_removed=lps_removed, confidence=confidence,
        )
        self.upsert(p)
        return p

    def register_insider(self, wallet: str, chain: str, *, median_entry_lead=None,
                         win_rate=None, common_funders=0, cluster_id=None,
                         confidence=0.5) -> ActorProfile:
        p = ActorProfile(
            wallet=wallet, chain=chain, role_tag="insider",
            median_entry_lead=median_entry_lead, win_rate=win_rate,
            common_funders=common_funders, cluster_id=cluster_id,
            confidence=confidence,
        )
        self.upsert(p)
        return p

    def count(self) -> int:
        return len(self._profiles)
