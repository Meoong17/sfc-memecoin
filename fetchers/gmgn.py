"""GMGN fetcher — token + wallet analytics (feature set for classification).

GMGN Agent API (docs.gmgn.ai) provides per-token and per-wallet analytics that
feed Wallet Classification (spec §6.5) and Insider Intelligence: token holders,
top traders, smart money, KOL, and wallet metrics like sniper/bundler ratios,
fresh-wallet rate, early-entry behavior.

Requires GMGN_API_KEY in .env. Maps into existing dataclasses where possible;
the wallet metrics feed WalletSignals for classification.

NOTE: exact endpoint paths/shapes depend on GMGN's OpenAPI. Verify against
docs.gmgn.ai when you have your key. Endpoints here are structured to be
adjusted to the real response once you test with live key.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from engines.wallet_classify import WalletSignals
from fetchers.base import BaseFetcher, FetchError

GMGN_BASE = "https://gmgn.ai"


@dataclass
class WalletAnalytics:
    """Wallet behavioral metrics (gmgn feature set -> WalletSignals)."""
    wallet: str
    chain: str
    sniper_count: int = 0
    bundler_trader_amount_rate: float = 0.0
    rat_trader_amount_rate: float = 0.0
    suspected_insider_hold_rate: float = 0.0
    fresh_wallet_rate: float = 0.0
    win_rate: float = 0.0
    early_entry_rate: float = 0.0
    social_influence: float = 0.0

    def to_wallet_signals(self) -> WalletSignals:
        """Map gmgn analytics into the classification signal contract."""
        return WalletSignals(
            wallet=self.wallet,
            high_win_rate=min(1.0, self.win_rate),
            high_social_influence=min(1.0, self.social_influence),
            buy_before_info_expansion=self.early_entry_rate >= 0.5,
            buys_coordinated=self.bundler_trader_amount_rate >= 0.5,
        )

    def summary(self) -> dict:
        return {
            "wallet": self.wallet,
            "chain": self.chain,
            "sniper_count": self.sniper_count,
            "bundler_trader_amount_rate": round(self.bundler_trader_amount_rate, 3),
            "rat_trader_amount_rate": round(self.rat_trader_amount_rate, 3),
            "suspected_insider_hold_rate": round(self.suspected_insider_hold_rate, 3),
            "fresh_wallet_rate": round(self.fresh_wallet_rate, 3),
            "win_rate": round(self.win_rate, 3),
            "early_entry_rate": round(self.early_entry_rate, 3),
        }


class GmgnFetcher(BaseFetcher):
    """Fetches GMGN token/wallet analytics."""

    def __init__(self, api_key: str | None = None, *, cache_dir: str | None = None,
                 cache_ttl: int = 300) -> None:
        self.api_key = api_key or os.getenv("GMGN_API_KEY")
        self.base = os.getenv("GMGN_BASE_URL", GMGN_BASE)
        if not self.api_key:
            raise ValueError("GMGN_API_KEY missing (set in .env or pass api_key=)")
        super().__init__(source="dex_api", cache_dir=cache_dir, cache_ttl=cache_ttl)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def wallet_analytics(self, wallet: str, chain: str = "solana") -> WalletAnalytics:
        """Fetch wallet behavioral metrics from GMGN.

        Endpoint structure is a best-effort mapping to the GMGN wallet API;
        adjust `path` to the real endpoint when you test with a live key.
        """
        path = f"/api/v1/wallet/{wallet}/analytics"
        url = f"{self.base}{path}"
        cache_key = f"gmgn_wallet_{chain}_{wallet}"
        try:
            data = self._get(url, params={"chain": chain}, headers=self._headers(),
                             cache_key=cache_key)
        except FetchError as e:
            raise FetchError(f"GMGN wallet {wallet}: {e}") from e

        d = data.get("data", data)
        return WalletAnalytics(
            wallet=wallet,
            chain=chain,
            sniper_count=int(d.get("sniper_count", 0) or 0),
            bundler_trader_amount_rate=float(d.get("bundler_trader_amount_rate", 0.0) or 0.0),
            rat_trader_amount_rate=float(d.get("rat_trader_amount_rate", 0.0) or 0.0),
            suspected_insider_hold_rate=float(d.get("suspected_insider_hold_rate", 0.0) or 0.0),
            fresh_wallet_rate=float(d.get("fresh_wallet_rate", 0.0) or 0.0),
            win_rate=float(d.get("win_rate", 0.0) or 0.0),
            early_entry_rate=float(d.get("early_entry_rate", 0.0) or 0.0),
            social_influence=float(d.get("social_influence", 0.0) or 0.0),
        )
