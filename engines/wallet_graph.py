"""Wallet Graph Engine (spec §6.3) — EV-021 consumer.

Builds a graph of wallet/token/LP relationships from on-chain evidence and
analyzes: connected components, community detection, wallet similarity. Uses
EV-021 (funding graph) plus EV-001 (swap flow) as inputs; does NOT recompute
them (Measurement Contract §3).

Suspected dev/insider cluster detection: a component funded by a common master
with high trading correlation + high token ownership.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from data_sources.dex_flow import DexFlowSnapshot
from data_sources.wallet_funding import FundingGraph

# ILLUSTRATIVE thresholds (calibration doctrine).
TOKEN_OWNERSHIP_SUSPECT_PCT = 8.0
TRADING_CORR_HIGH = 0.7


@dataclass
class WalletCluster:
    component_id: int
    wallet_count: int
    token_ownership_pct: float = 0.0
    common_funder: str | None = None
    trading_correlation: float = 0.0
    wallets: list[str] = field(default_factory=list)

    @property
    def suspected_dev_insider(self) -> bool:
        return (self.common_funder is not None
                and self.token_ownership_pct >= TOKEN_OWNERSHIP_SUSPECT_PCT
                and self.trading_correlation >= TRADING_CORR_HIGH)


@dataclass
class WalletGraphResult:
    token: str
    chain: str
    n_nodes: int
    n_components: int
    clusters: list[WalletCluster] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "chain": self.chain,
            "n_nodes": self.n_nodes,
            "n_components": self.n_components,
            "clusters": [{
                "component_id": c.component_id,
                "wallet_count": c.wallet_count,
                "token_ownership_pct": round(c.token_ownership_pct, 2),
                "common_funder": c.common_funder,
                "suspected_dev_insider": c.suspected_dev_insider,
            } for c in self.clusters],
        }


class WalletGraphEngine:
    """EV-021 consumer: maps funding clusters + swap flows into a wallet graph."""

    def __init__(self, funding: FundingGraph, flow: DexFlowSnapshot | None = None) -> None:
        self.funding = funding
        self.flow = flow

    def build(self) -> WalletGraphResult:
        g = nx.Graph()
        # Nodes & edges from funding graph: master --funds--> sub_wallet
        for cluster in self.funding.clusters:
            master = cluster.master_wallet
            g.add_node(master)
            for sub in cluster.sub_wallets:
                g.add_node(sub)
                g.add_edge(master, sub)
        # If swap flow provided, add buyer/seller nodes & edges (shared token holding)
        if self.flow is not None:
            for w in self.flow.trades_per_wallet:
                g.add_node(w)

        components = list(nx.connected_components(g))
        result = WalletGraphResult(
            token=self.funding.token,
            chain=self.funding.chain,
            n_nodes=g.number_of_nodes(),
            n_components=len(components),
        )

        # Total token supply unknown in Phase 1; ownership % is a placeholder from
        # the funding cluster ratio until real supply data is wired. Flag ILLUSTRATIVE.
        total_funded = sum(c.total_funded for c in self.funding.clusters) or 1.0

        for cid, comp in enumerate(components):
            wallets = sorted(comp)
            # Common funder = master present in this component
            masters = {c.master_wallet for c in self.funding.clusters}
            funder = next((w for w in wallets if w in masters), None)
            comp_funded = sum(c.total_funded for c in self.funding.clusters if c.master_wallet in comp)
            ownership = (comp_funded / total_funded) * 100.0
            # trading correlation placeholder from trades-per-wallet concentration
            corr = self._trading_correlation(wallets)
            result.clusters.append(WalletCluster(
                component_id=cid,
                wallet_count=len(wallets),
                token_ownership_pct=round(ownership, 2),
                common_funder=funder,
                trading_correlation=round(corr, 3),
                wallets=wallets,
            ))
        return result

    def _trading_correlation(self, wallets: list[str]) -> float:
        """Coordinated-participation ratio (ILLUSTRATIVE proxy).

        Fraction of the component's wallets that actively trade this token.
        When a single funding cluster's sub-wallets all buy the same token, the
        ratio is high -> signals coordinated behavior. True cross-token trading
        correlation needs multi-token flow data (later phase).
        """
        if self.flow is None or not wallets:
            return 0.0
        active = [w for w in wallets if self.flow.trades_per_wallet.get(w, 0) > 0]
        return len(active) / len(wallets)
