"""GMGN fetcher — via gmgn-cli (official OpenAPI CLI).

GMGN OpenAPI is accessed through the official `gmgn-cli` (npm package,
repo GMGNAI/gmgn-skills) — NOT direct REST to gmgn.ai (which is Cloudflare-
protected, verified HTTP 403). gmgn-cli handles auth (GMGN_API_KEY +
GMGN_PRIVATE_KEY request-signing) and returns JSON.

This fetcher shells out to `npx gmgn-cli`, parses JSON, and maps into the
existing dataclasses so the pipeline consumes real data:

  token security  -> ContractFacts (EV-002 producer input)
  portfolio stats -> WalletAnalytics -> WalletSignals (classification)

Requires GMGN_API_KEY (and GMGN_PRIVATE_KEY for signing) in .env.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field

from data_sources.honeypot_sim import ContractFacts
from engines.wallet_classify import WalletSignals
from fetchers.base import FetchError


@dataclass
class WalletAnalytics:
    """Wallet behavioral metrics -> WalletSignals."""
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
        }


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass
class TokenMarketStats:
    """Token market microstructure stats (from GMGN `token info`).

    Feeds the core weight mapping (Organic = quality of demand, Smart Money =
    quality of wallet flow) so Risk-Adjusted Alpha is measured, not a constant.
    Empty/zero = no data (degraded, not a signal).
    """
    address: str
    chain: str
    holder_count: int = 0
    locked_ratio: float = 0.0          # fraction of supply LP-locked [0,1]
    smart_wallets: int = 0
    sniper_wallets: int = 0
    bundler_wallets: int = 0
    fresh_wallets: int = 0
    whale_wallets: int = 0
    renowned_wallets: int = 0
    rat_trader_wallets: int = 0
    creator_wallets: int = 0
    buys_24h: int = 0
    sells_24h: int = 0
    swaps_24h: int = 0
    buy_volume_24h: float = 0.0
    sell_volume_24h: float = 0.0
    volume_24h: float = 0.0
    price_24h: float = 0.0            # 24h price change fraction (e.g. 0.41 = +41%)

    def summary(self) -> dict:
        return {
            "address": self.address, "chain": self.chain,
            "holder_count": self.holder_count, "locked_ratio": round(self.locked_ratio, 4),
            "smart_wallets": self.smart_wallets, "sniper_wallets": self.sniper_wallets,
            "bundler_wallets": self.bundler_wallets, "fresh_wallets": self.fresh_wallets,
            "whale_wallets": self.whale_wallets, "renowned_wallets": self.renowned_wallets,
            "rat_trader_wallets": self.rat_trader_wallets,
            "creator_wallets": self.creator_wallets,
            "buys_24h": self.buys_24h, "sells_24h": self.sells_24h, "swaps_24h": self.swaps_24h,
            "buy_volume_24h": round(self.buy_volume_24h, 2),
            "sell_volume_24h": round(self.sell_volume_24h, 2),
            "volume_24h": round(self.volume_24h, 2), "price_24h": round(self.price_24h, 4),
        }


class GmgnFetcher:
    """Fetches GMGN data via the official gmgn-cli."""

    def __init__(self, api_key: str | None = None, *, cli: str = "gmgn-cli") -> None:
        self.api_key = api_key or os.getenv("GMGN_API_KEY")
        if not self.api_key:
            raise ValueError("GMGN_API_KEY missing (set in .env)")
        self.cli = cli
        if shutil.which("npx") is None:
            raise RuntimeError("npx not found; gmgn-cli requires Node/npx")

    def _run(self, *args: str) -> dict:
        """Run gmgn-cli with the API key, return parsed JSON."""
        env = dict(os.environ)
        if self.api_key is None:
            raise FetchError("GMGN_API_KEY missing")
        env["GMGN_API_KEY"] = self.api_key
        cmd = ["npx", "--yes", self.cli, *args, "--raw"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                  env=env, check=False)
        except (subprocess.TimeoutExpired, OSError) as e:
            raise FetchError(f"gmgn-cli {args[0]} failed: {e}") from e
        if proc.returncode != 0:
            raise FetchError(f"gmgn-cli {args[0]} exited {proc.returncode}: "
                             f"{proc.stderr.strip()[:200] or proc.stdout.strip()[:200]}")
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise FetchError(f"gmgn-cli {args[0]} non-JSON output: {proc.stdout[:200]}") from e

    def _chain_flag(self, chain: str) -> str:
        return {"solana": "sol", "sol": "sol", "bsc": "bsc", "base": "base"}.get(chain, chain)

    # --- dev/creator wallet lookup -> master wallet for EV-021 funding trace ---
    def find_dev_wallet(self, address: str, chain: str = "solana") -> str | None:
        """Find the token's dev wallet via `token traders --tag dev`.

        Returns the first dev `account_address`, or None if no dev trader is
        tagged (e.g. no GMGN dev record). This wallet is the natural EV-021
        master to trace funding edges from.
        """
        try:
            data = self._run("token", "traders", "--chain", self._chain_flag(chain),
                             "--address", address, "--tag", "dev", "--limit", "5")
        except FetchError:
            return None
        lst = data.get("list") or []
        for t in lst:
            acc = t.get("account_address") or t.get("address")
            if acc:
                return acc
        return None

    # --- dev dump signals (on-chain insider evidence) ---
    def dev_trader_signals(self, address: str, chain: str = "solana") -> dict:
        """Pull the dev trader's on-chain sell/transfer activity (insider label).

        Maps fields VERIFIED live in `token traders --tag dev`: the dev's own
        sell ratio and transfer-out amount are direct evidence of dev-dump.
        Returns a dict with keys prefixed `dev_` (empty if no dev record).
        """
        try:
            data = self._run("token", "traders", "--chain", self._chain_flag(chain),
                             "--address", address, "--tag", "dev", "--limit", "5")
        except FetchError:
            return {}
        lst = data.get("list") or []
        if not lst:
            return {}
        t = lst[0]
        def f(k):
            try:
                return float(t.get(k))
            except (TypeError, ValueError):
                return 0.0
        return {
            "dev_wallet": t.get("account_address") or t.get("address"),
            "dev_sell_amount_percentage": f("sell_amount_percentage"),
            "dev_sell_tx_count": int(f("sell_tx_count_cur")),
            "dev_buy_tx_count": int(f("buy_tx_count_cur")),
            "dev_current_sell_amount": f("current_sell_amount"),
            "dev_current_transfer_out_amount": f("current_transfer_out_amount"),
        }

    # --- token market microstructure -> TokenMarketStats (core weight mapping) ---
    def market_stats(self, address: str, chain: str = "solana") -> TokenMarketStats:
        """Fetch token basic info + realtime price microstructure from GMGN.

        Maps `token info` fields onto TokenMarketStats so the pipeline can drive
        Organic (quality of demand) and Smart Money (quality of wallet flow) from
        real data instead of constants. Returns a stats object (zeros if the
        fetch fails / no data — degraded, not a signal).
        """
        st = TokenMarketStats(address=address, chain=chain)
        try:
            data = self._run("token", "info", "--chain", self._chain_flag(chain),
                             "--address", address)
        except FetchError:
            return st
        st.holder_count = int(_f(data.get("holder_count"), 0))
        st.locked_ratio = min(1.0, _f(data.get("locked_ratio"), 0.0))

        tags = data.get("wallet_tags_stat") or {}
        if isinstance(tags, dict):
            st.smart_wallets = int(_f(tags.get("smart_wallets"), 0))
            st.sniper_wallets = int(_f(tags.get("sniper_wallets"), 0))
            st.bundler_wallets = int(_f(tags.get("bundler_wallets"), 0))
            st.fresh_wallets = int(_f(tags.get("fresh_wallets"), 0))
            st.whale_wallets = int(_f(tags.get("whale_wallets"), 0))
            st.renowned_wallets = int(_f(tags.get("renowned_wallets"), 0))
            st.rat_trader_wallets = int(_f(tags.get("rat_trader_wallets"), 0))
            st.creator_wallets = int(_f(tags.get("creator_wallets"), 0))

        p = data.get("price") or {}
        if isinstance(p, dict):
            st.buys_24h = int(_f(p.get("buys_24h"), 0))
            st.sells_24h = int(_f(p.get("sells_24h"), 0))
            st.swaps_24h = int(_f(p.get("swaps_24h"), 0))
            st.buy_volume_24h = max(0.0, _f(p.get("buy_volume_24h"), 0.0))
            st.sell_volume_24h = max(0.0, _f(p.get("sell_volume_24h"), 0.0))
            st.volume_24h = max(0.0, _f(p.get("volume_24h"), 0.0))
            # price_24h is a fraction change (e.g. 0.41 = +41%); it can be < -1
            st.price_24h = _f(p.get("price_24h"), 0.0)
        return st

    # --- token security -> ContractFacts (EV-002) ---
    def token_security(self, address: str, chain: str = "solana") -> ContractFacts:
        """Fetch token security metrics, map into ContractFacts for honeypot sim."""
        data = self._run("token", "security", "--chain", self._chain_flag(chain),
                         "--address", address)
        # Map GMGN security fields onto ContractFacts (EV-002 producer input).
        # is_honeypot: can't sell AND not renounced -> honeypot-ish.
        can_sell = _f(data.get("can_sell", 1))
        can_not_sell = _f(data.get("can_not_sell", 0))
        sellable = can_sell == 1 or can_not_sell == 0
        lp = data.get("lock_summary") or {}
        lp_locked = 1.0 - _f(lp.get("lock_percent", "0"), 1.0)
        return ContractFacts(
            address=address,
            chain=chain,
            buy_sellable=True,
            sell_sellable=sellable,
            buy_tax_pct=_f(data.get("buy_tax", "0")),
            sell_tax_pct=_f(data.get("sell_tax", "0")),
            lp_locked_pct=lp_locked,
            lp_burned=_f(data.get("burn_ratio", "0")) > 0.5,
            lp_total_removed=False,
            multi_dex_liquidity=True,
            dev_owns_majority_lp=False,
            notes=[f"gmgn_top10_holder_rate={data.get('top_10_holder_rate')}",
                   f"gmgn_is_renounced={data.get('renounced')}",
                   f"gmgn_blacklist={data.get('blacklist')}",
                   f"gmgn_flags={data.get('flags')}"],
        )

    # --- portfolio stats -> WalletAnalytics (classification) ---
    def wallet_stats(self, wallet: str, chain: str = "solana", period: str = "30d") -> WalletAnalytics:
        """Fetch wallet trading stats via gmgn-cli portfolio stats.

        Maps to the FIELDS ACTUALLY RETURNED by gmgn-cli (verified live):
          pnl_stat.winrate, buy, sell, common.created_at (wallet age),
          pnl_stat.avg_holding_period.
        Sniper/bundler/insider_hold rates live in OTHER endpoints
        (token traders / follow-wallet) and are left 0 here until wired.
        """
        data = self._run("portfolio", "stats", "--chain", self._chain_flag(chain),
                         "--wallet", wallet, "--period", period)
        d = data.get("data", data)
        pnl = d.get("pnl_stat") or {}
        common = d.get("common") or {}

        # wallet age -> fresh_wallet_rate (created_at unix -> 0 if recent)
        created = _f(common.get("created_at"), 0.0)
        import time
        age_days = (time.time() - created) / 86400.0 if created else 0.0
        fresh_wallet = 1.0 if age_days < 30 else (0.5 if age_days < 90 else 0.0)

        return WalletAnalytics(
            wallet=wallet,
            chain=chain,
            win_rate=_f(pnl.get("winrate")),
            sniper_count=int(_f(d.get("buy"))),   # buys as a volume proxy
            early_entry_rate=_f(d.get("buy")) / max(1.0, _f(d.get("buy")) + _f(d.get("sell"))),
            fresh_wallet_rate=fresh_wallet,
        )
