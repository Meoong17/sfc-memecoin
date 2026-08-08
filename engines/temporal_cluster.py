"""Temporal Wallet Clustering — Insider P1 (spec roadmap Phase 3).

Detects wallets that repeatedly enter EARLY across multiple launches (a
behavioral signature of early-access participants / insiders), and integrates
with the Actor Reputation Network (spec §6.10).

For each wallet we accumulate, across launches:
  - how often it entered before public info expansion,
  - its median lead time,
  - funding-cluster membership,
  - profitability/win rate.

A wallet with consistent early entries across many tokens gets flagged as a
reputed insider and its profile is updated in the Actor Reputation DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from reputation.actor_reputation import ActorReputationDB


@dataclass
class WalletEntryRecord:
    wallet: str
    chain: str
    token: str
    entry_lead_minutes: float = 0.0       # positive = entered before info expansion
    early_entry: bool = False             # entered before public info
    in_funding_cluster: bool = False
    profitable: bool = False
    ts_minute: float = 0.0


@dataclass
class TemporalClusterResult:
    wallet: str
    chain: str
    launches_entered: int = 0
    early_entries: int = 0
    median_lead_minutes: float = 0.0
    funding_cluster_memberships: int = 0
    early_rate: float = 0.0               # early / launches
    is_reputed_insider: bool = False
    reputation_confirmed: bool = False    # profile updated in DB
    reasons: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "wallet": self.wallet,
            "chain": self.chain,
            "launches_entered": self.launches_entered,
            "early_entries": self.early_entries,
            "median_lead_minutes": round(self.median_lead_minutes, 1),
            "early_rate": round(self.early_rate, 2),
            "is_reputed_insider": self.is_reputed_insider,
            "reputation_confirmed": self.reputation_confirmed,
            "reasons": self.reasons,
        }


# ILLUSTRATIVE thresholds (calibration doctrine).
MIN_LAUNCHES = 3              # need >= this many launches before judging
REPUTED_EARLY_RATE = 0.7      # >=70% early entries across launches
REPUTED_MIN_LEAD = 5.0        # min median lead minutes


class TemporalWalletClusterer:
    """Aggregates per-wallet early-entry behavior across launches."""

    def __init__(self, reputation: ActorReputationDB | None = None) -> None:
        self.reputation = reputation or ActorReputationDB()

    def _median(self, values: list[float]) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        n = len(s)
        if n % 2 == 1:
            return s[n // 2]
        return (s[n // 2 - 1] + s[n // 2]) / 2.0

    def cluster(self, records: list[WalletEntryRecord]) -> list[TemporalClusterResult]:
        # group by (wallet, chain)
        by_wallet: dict[tuple[str, str], list[WalletEntryRecord]] = {}
        for r in records:
            by_wallet.setdefault((r.wallet, r.chain), []).append(r)

        results = []
        for (wallet, chain), rs in by_wallet.items():
            launches = len(rs)
            early = [r for r in rs if r.early_entry]
            leads = [r.entry_lead_minutes for r in early]
            res = TemporalClusterResult(
                wallet=wallet, chain=chain,
                launches_entered=launches,
                early_entries=len(early),
                median_lead_minutes=self._median(leads),
                funding_cluster_memberships=sum(1 for r in rs if r.in_funding_cluster),
                early_rate=len(early) / launches if launches else 0.0,
            )
            if (launches >= MIN_LAUNCHES
                    and res.early_rate >= REPUTED_EARLY_RATE
                    and res.median_lead_minutes >= REPUTED_MIN_LEAD):
                res.is_reputed_insider = True
                res.reasons.append("consistent_early_entry")
                if res.funding_cluster_memberships > 0:
                    res.reasons.append("funding_cluster_member")
                # integrate with Actor Reputation DB (Insider P1)
                self.reputation.register_insider(
                    wallet, chain,
                    median_entry_lead=res.median_lead_minutes,
                    common_funders=res.funding_cluster_memberships,
                )
                res.reputation_confirmed = True
            results.append(res)
        return results
