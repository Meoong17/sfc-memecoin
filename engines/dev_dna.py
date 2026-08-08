"""Dev DNA — 5-level deployer match (spec §6.1, roadmap Phase 1).

Matches a current project's deployer against known patterns from the Actor
Reputation Network, returning a 0-5 match level:
  0 = no match (unknown / clean)
  1 = wallet similarity (same funder)
  2 = same deployer as a past launch
  3 = same deployer + past rug/abandon
  4 = same deployer + past LP removal
  5 = exact known-bad deployer (rug pattern + LP removal + abandonment)

Higher match = stronger dev-risk signal, feeding the security gate / veto.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reputation.actor_reputation import ActorReputationDB


@dataclass
class DevMatchResult:
    level: int = 0                      # 0..5
    matched_wallet: str | None = None
    matched_dev_score: int | None = None
    reasons: list[str] = field(default_factory=list)

    @property
    def is_suspicious(self) -> bool:
        return self.level >= 3

    def summary(self) -> dict:
        return {
            "level": self.level,
            "matched_wallet": self.matched_wallet,
            "matched_dev_score": self.matched_dev_score,
            "is_suspicious": self.is_suspicious,
            "reasons": self.reasons,
        }


class DevDNAMatcher:
    """Matches deployer against Actor Reputation DB history."""

    def __init__(self, reputation: ActorReputationDB | None = None) -> None:
        self.reputation = reputation or ActorReputationDB()

    def match(self, deployer: str, chain: str) -> DevMatchResult:
        prof = self.reputation.lookup(deployer, chain)
        if prof is None or prof.role_tag != "dev":
            return DevMatchResult()  # level 0, no prior record

        result = DevMatchResult(level=1, matched_wallet=deployer,
                                matched_dev_score=prof.dev_score)
        result.reasons.append("known_dev_deployer")

        # Level escalates with each confirming bad-history signal.
        if prof.rugged > 0:
            result.level = max(result.level, 2)
            result.reasons.append(f"past_rugs_{prof.rugged}")
        if prof.abandoned > 0:
            result.level = max(result.level, 3)
            result.reasons.append(f"past_abandoned_{prof.abandoned}")
        if prof.lps_removed > 0:
            result.level = max(result.level, 4)
            result.reasons.append(f"past_lp_removals_{prof.lps_removed}")
        if prof.rugged >= 3 and prof.lps_removed >= 2:
            result.level = 5
            result.reasons.append("rug_pattern_lp_removal")

        # A high dev_score (safe dev) caps suspicion at level 1.
        if prof.dev_score >= 60:
            result.level = min(result.level, 1)
        return result
