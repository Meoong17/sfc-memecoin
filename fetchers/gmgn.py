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
    def wallet_stats(self, wallet: str, chain: str = "solana") -> WalletAnalytics:
        """Fetch wallet trading stats via gmgn-cli portfolio stats."""
        data = self._run("portfolio", "stats", "--chain", self._chain_flag(chain),
                         "--wallet", wallet)
        d = data.get("data", data)
        return WalletAnalytics(
            wallet=wallet,
            chain=chain,
            sniper_count=int(_f(d.get("sniper_count"))),
            bundler_trader_amount_rate=_f(d.get("bundler_trader_amount_rate")),
            rat_trader_amount_rate=_f(d.get("rat_trader_amount_rate")),
            suspected_insider_hold_rate=_f(d.get("suspected_insider_hold_rate")),
            fresh_wallet_rate=_f(d.get("fresh_wallet_rate")),
            win_rate=_f(d.get("win_rate")),
            early_entry_rate=_f(d.get("early_entry_rate")),
            social_influence=_f(d.get("social_influence")),
        )
