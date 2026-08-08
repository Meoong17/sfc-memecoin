"""DEX flow producer (EV-001): wallet swap flow from DEX data.

Consumers (spec §3): Microstructure, Absorption.
Produces EV-001 as a structured wallet-flow snapshot for one token.

Phase 1: a pure aggregation over raw swap records. Real DEX ingestion (Raydium
getTrades, PancakeSwap subgraph) is wired later via the same interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from collections import Counter


@dataclass
class Swap:
    wallet: str
    side: str                # "BUY" or "SELL"
    amount_token: float
    amount_quote: float
    ts: datetime
    pool: str = ""


@dataclass
class DexFlowSnapshot:
    """EV-001 evidence value for one token over a window."""
    token: str
    chain: str
    window_start: datetime
    window_end: datetime
    total_buy: float = 0.0
    total_sell: float = 0.0
    unique_buyers: int = 0
    unique_sellers: int = 0
    trades_per_wallet: dict[str, int] = field(default_factory=dict)
    buy_sell_size: dict[str, float] = field(default_factory=dict)  # side -> avg size
    swaps: list[Swap] = field(default_factory=list)

    @property
    def net_flow(self) -> float:
        return self.total_buy - self.total_sell

    @property
    def net_flow_direction(self) -> str:
        if self.net_flow > 0:
            return "BUY"
        if self.net_flow < 0:
            return "SELL"
        return "FLAT"

    @property
    def avg_trades_per_wallet(self) -> float:
        if not self.trades_per_wallet:
            return 0.0
        return sum(self.trades_per_wallet.values()) / len(self.trades_per_wallet)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "chain": self.chain,
            "total_buy": round(self.total_buy, 4),
            "total_sell": round(self.total_sell, 4),
            "net_flow": round(self.net_flow, 4),
            "net_flow_direction": self.net_flow_direction,
            "unique_buyers": self.unique_buyers,
            "unique_sellers": self.unique_sellers,
            "avg_trades_per_wallet": round(self.avg_trades_per_wallet, 3),
        }


def aggregate_swaps(token: str, chain: str, swaps: list[Swap],
                    window_start: datetime, window_end: datetime) -> DexFlowSnapshot:
    """Aggregate raw swaps into an EV-001 snapshot."""
    snap = DexFlowSnapshot(token=token, chain=chain,
                           window_start=window_start, window_end=window_end)
    per_wallet: Counter = Counter()
    buy_sizes: list[float] = []
    sell_sizes: list[float] = []
    buyers: set[str] = set()
    sellers: set[str] = set()

    for s in swaps:
        snap.swaps.append(s)
        per_wallet[s.wallet] += 1
        if s.side.upper() == "BUY":
            snap.total_buy += s.amount_quote
            buy_sizes.append(s.amount_quote)
            buyers.add(s.wallet)
        else:
            snap.total_sell += s.amount_quote
            sell_sizes.append(s.amount_quote)
            sellers.add(s.wallet)

    snap.trades_per_wallet = dict(per_wallet)
    snap.unique_buyers = len(buyers)
    snap.unique_sellers = len(sellers)
    snap.buy_sell_size["BUY"] = sum(buy_sizes) / len(buy_sizes) if buy_sizes else 0.0
    snap.buy_sell_size["SELL"] = sum(sell_sizes) / len(sell_sizes) if sell_sizes else 0.0
    return snap
