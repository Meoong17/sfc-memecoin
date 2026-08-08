"""DexScreener fetcher — token discovery + market snapshot (EV-002/DQI inputs).

DexScreener public API is FREE (no key) and reliable for price/liquidity/
volume/holders per token. It is the discovery + DQI source.

Public API:
  GET https://api.dexscreener.com/token-profiles/latest/v1      -> recent token profiles
  GET https://api.dexscreener.com/latest/dex/tokens/{address}   -> token detail

Maps into existing data_sources dataclasses where relevant; other fields feed
the pipeline's TokenFeatures directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from fetchers.base import BaseFetcher, FetchError

BASE = "https://api.dexscreener.com"


@dataclass
class TokenMarketInfo:
    """Market snapshot for one token (discovery + DQI)."""
    address: str
    chain: str
    symbol: str = ""
    name: str = ""
    price_usd: float = 0.0
    volume_24h: float = 0.0
    liquidity_usd: float = 0.0
    mcap: float | None = None
    holders: int | None = None
    dex_id: str = ""
    pair_address: str = ""
    is_dex_screener_profile: bool = False

    def summary(self) -> dict:
        return {
            "address": self.address,
            "chain": self.chain,
            "symbol": self.symbol,
            "price_usd": self.price_usd,
            "volume_24h": self.volume_24h,
            "liquidity_usd": self.liquidity_usd,
            "mcap": self.mcap,
            "holders": self.holders,
        }


class DexScreenerFetcher(BaseFetcher):
    """Fetches token market data from DexScreener public API."""

    def __init__(self, *, cache_dir: str | None = None, cache_ttl: int = 300) -> None:
        super().__init__(source="dex_api", cache_dir=cache_dir, cache_ttl=cache_ttl)

    def token_profiles(self, limit: int = 20) -> list[TokenMarketInfo]:
        """Fetch recent token profiles (discovery universe)."""
        data = self._get(f"{BASE}/token-profiles/latest/v1", cache_key="ds_profiles")
        out: list[TokenMarketInfo] = []
        for p in data or []:
            chain = (p.get("chainId") or "").lower()
            info = TokenMarketInfo(
                address=p.get("tokenAddress", ""),
                chain=chain,
                symbol=(p.get("symbol") or ""),
                name=(p.get("name") or ""),
                is_dex_screener_profile=True,
            )
            # volumes may be nested per-chain
            vol = p.get("volume") or {}
            if isinstance(vol, dict):
                info.volume_24h = float(vol.get("h24") or 0.0)
            out.append(info)
            if len(out) >= limit:
                break
        return out

    def token_detail(self, address: str, chain: str = "solana") -> TokenMarketInfo | None:
        """Fetch detailed market data for one token address."""
        key = f"ds_detail_{chain}_{address}"
        try:
            data = self._get(f"{BASE}/latest/dex/tokens/{address}", cache_key=key)
        except FetchError:
            return None
        pairs = data.get("pairs") or []
        if not pairs:
            return None
        # pick the pair on the requested chain with most liquidity
        chain_pairs = [p for p in pairs if (p.get("chainId") or "").lower() == chain]
        if not chain_pairs:
            chain_pairs = pairs
        best = max(chain_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd") or 0.0))

        liq = best.get("liquidity") or {}
        info = TokenMarketInfo(
            address=address,
            chain=(best.get("chainId") or chain).lower(),
            symbol=(best.get("baseToken") or {}).get("symbol", ""),
            name=(best.get("baseToken") or {}).get("name", ""),
            price_usd=float(best.get("priceUsd") or 0.0),
            volume_24h=float((best.get("volume") or {}).get("h24") or 0.0),
            liquidity_usd=float(liq.get("usd") or 0.0),
            mcap=float(best.get("fdv") or 0.0) if best.get("fdv") else None,
            dex_id=best.get("dexId", ""),
            pair_address=best.get("pairAddress", ""),
            is_dex_screener_profile=False,
        )
        # holders sometimes present on boosted profiles; not always available
        return info


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
