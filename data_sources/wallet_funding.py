"""Wallet funding trace producer (EV-021): master -> sub-wallet graph.

Consumers (spec §3): Wallet Graph, Sybil Score, Insider Intelligence.
Produces EV-021 as funding clusters: groups of wallets funded by a common
master wallet, which is how coordinated buy clusters are detected (one master
funds several sub-wallets for group buying — spec §6.6.2, Robinhood pattern).

Phase 1: pure graph aggregation. Real RPC tracing wired later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FundingEdge:
    master_wallet: str
    sub_wallet: str
    amount: float
    ts: datetime
    chain: str


@dataclass
class FundingCluster:
    cluster_id: str
    master_wallet: str
    sub_wallets: list[str] = field(default_factory=list)
    total_funded: float = 0.0
    chain: str = ""
    first_funded_ts: datetime | None = None

    @property
    def size(self) -> int:
        return len(self.sub_wallets)

    def summary(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "master_wallet": self.master_wallet,
            "size": self.size,
            "sub_wallets": self.sub_wallets,
            "total_funded": round(self.total_funded, 4),
            "chain": self.chain,
        }


@dataclass
class FundingGraph:
    """EV-021 value: clusters derived from funding edges."""
    token: str
    chain: str
    clusters: list[FundingCluster] = field(default_factory=list)

    @property
    def cluster_count(self) -> int:
        return len(self.clusters)

    def cluster_by_master(self, master: str) -> FundingCluster | None:
        for c in self.clusters:
            if c.master_wallet == master:
                return c
        return None

    def summary(self) -> dict:
        return {
            "token": self.token,
            "chain": self.chain,
            "cluster_count": len(self.clusters),
            "clusters": [c.summary() for c in self.clusters],
        }


def build_funding_graph(token: str, chain: str, edges: list[FundingEdge]) -> FundingGraph:
    """Group funding edges by master wallet into clusters."""
    by_master: dict[str, list[FundingEdge]] = {}
    for e in edges:
        by_master.setdefault(e.master_wallet, []).append(e)

    graph = FundingGraph(token=token, chain=chain)
    for i, (master, edges_for_master) in enumerate(sorted(by_master.items())):
        subs = sorted({e.sub_wallet for e in edges_for_master})
        total = sum(e.amount for e in edges_for_master)
        first = min((e.ts for e in edges_for_master), default=None)
        graph.clusters.append(FundingCluster(
            cluster_id=f"{token}-C{i+1}",
            master_wallet=master,
            sub_wallets=subs,
            total_funded=total,
            chain=chain,
            first_funded_ts=first,
        ))
    return graph
