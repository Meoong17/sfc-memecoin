"""OKX Onchain OS fetcher — via the official `onchainos` CLI.

OKX Onchain OS DEX/Market API is accessed through the official `onchainos`
CLI (installed via `curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh`
→ prebuilt release binary at `~/.local/bin/onchainos`, v4.4.9 verified). The
CLI handles the HMAC auth (OK-ACCESS-* headers) internally using the env vars
`OKX_API_KEY` / `OKX_SECRET_KEY` / `OKX_PASSPHRASE` (all three required).

This is a SEPARATE API from GMGN — useful as a fallback when GMGN is
rate-limit-banned, and as a richer dev-rug / insider minority-class source:

  memepump tokens           -> universe (tags.devHoldingsPercent, insidersPercent,
                                        snipersPercent, bundlersPercent, top10HoldingsPercent)
  memepump token-dev-info   -> devLaunchedInfo.{rugPullCount,migratedCount,totalTokens},
                               devHoldingInfo.devHoldingPercent / devAddress / fundingAddress
  memepump token-bundle-info-> bundler/sniper analysis

Pattern mirrors fetchers/gmgn.py: shell out to the CLI, parse JSON, map into
the existing dataclasses / dicts so the pipeline stays unchanged.

Requires OKX_API_KEY + OKX_SECRET_KEY + OKX_PASSPHRASE in .env.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

from fetchers.base import FetchError


class OkxFetcher:
    """Fetches OKX Onchain OS memepump data via the `onchainos` CLI."""

    def __init__(self, *, cli: str = "onchainos") -> None:
        key = os.getenv("OKX_API_KEY")
        secret = os.getenv("OKX_SECRET_KEY")
        passphrase = os.getenv("OKX_PASSPHRASE")
        if not (key and secret and passphrase):
            raise ValueError(
                "OKX_API_KEY + OKX_SECRET_KEY + OKX_PASSPHRASE all required (set in .env)")
        self.cli = shutil.which(cli) or cli
        if shutil.which(cli) is None:
            raise RuntimeError(
                f"onchainos CLI not found; install via "
                "curl -sSL https://raw.githubusercontent.com/okx/onchainos-skills/main/install.sh | sh")

    def _run(self, *args: str) -> dict:
        """Run onchainos memepump subcommand, return parsed JSON."""
        env = dict(os.environ)
        cmd = [self.cli, "memepump", *args]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                                  env=env, check=False)
        except (subprocess.TimeoutExpired, OSError) as e:
            raise FetchError(f"onchainos {args[0]} failed: {e}") from e
        if proc.returncode != 0:
            raise FetchError(f"onchainos {args[0]} exited {proc.returncode}: "
                             f"{proc.stderr.strip()[:300] or proc.stdout.strip()[:300]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise FetchError(f"onchainos {args[0]} non-JSON output: {proc.stdout[:200]}") from e
        if not data.get("ok"):
            raise FetchError(f"onchainos {args[0]} returned ok=false: {proc.stdout[:300]}")
        return data

    # --- universe ---
    def universe(self, chain: str = "solana", stage: str = "NEW") -> list[dict]:
        """Fetch memepump token list for a stage (NEW/MIGRATING/MIGRATED).

        Returns the raw token dicts (address, name, symbol, createdTimestamp,
        market, tags, etc). Stage NEW = newborn tokens (insider signals mostly 0);
        MIGRATING/MIGRATED = tokens further along their lifecycle (richer
        devHoldingsPercent / insidersPercent / top10HoldingsPercent signals).
        """
        data = self._run("tokens", "--chain", chain, "--stage", stage)
        return data.get("data") or []

    # --- dev reputation / rug ---
    def token_dev_info(self, address: str) -> dict:
        """Fetch dev reputation + rugPullCount for a token.

        Returns dict with:
          devLaunchedInfo.rugPullCount / migratedCount / goldenGemCount / totalTokens
          devHoldingInfo.devHoldingPercent / devAddress / fundingAddress / devBalance
        May return {} if the token has no dev record.
        """
        try:
            data = self._run("token-dev-info", "--address", address)
        except FetchError:
            return {}
        return data.get("data") or {}

    # --- token details -> holder-composition tags (per-address) ---
    def token_tags_by_address(self, address: str) -> dict:
        """Fetch the holder-composition `tags` for a single address.

        `memepump token-details --address <addr>` returns the SAME `tags`
        structure as the list endpoint (bundlersPercent, devHoldingsPercent,
        freshWalletsPercent, insidersPercent, snipersPercent,
        suspectedPhishingWalletPercent, top10HoldingsPercent, totalHolders).

        This is the per-token path to holder composition that `insider_signals`
        (token-dev-info) does NOT carry. Returns {} (safe degradation) when the
        address is not a memepump token (`data:null`) or the call fails.
        """
        try:
            data = self._run("token-details", "--address", address)
        except FetchError:
            return {}
        tok = data.get("data")
        if not isinstance(tok, dict):
            return {}
        return self.tags_signals(tok)

    # --- bundle / sniper ---
    def token_bundle_info(self, address: str) -> dict:
        """Fetch bundler/sniper analysis (totalBundlers, bundledValueNative)."""
        try:
            data = self._run("token-bundle-info", "--address", address)
        except FetchError:
            return {}
        return data.get("data") or {}

    # --- insider label assembly ---
    def tags_signals(self, token: dict) -> dict:
        """Extract the holder-composition tags from a `memepump tokens` row.

        These tags (insidersPercent, snipersPercent, bundlersPercent,
        top10HoldingsPercent, devHoldingsPercent, freshWalletsPercent) come in
        the TOKEN LIST response, not from token-dev-info. Returns keys prefixed
        `okx_` (empty defaults when absent)."""
        t = token.get("tags") or {}
        return {
            "okx_insiders_percent": _f(t.get("insidersPercent")),
            "okx_snipers_percent": _f(t.get("snipersPercent")),
            "okx_bundlers_percent": _f(t.get("bundlersPercent")),
            "okx_top10_holdings_percent": _f(t.get("top10HoldingsPercent")),
            "okx_dev_holding_percent": _f(t.get("devHoldingsPercent")),
            "okx_fresh_wallets_percent": _f(t.get("freshWalletsPercent")),
            "okx_suspected_phishing_percent": _f(t.get("suspectedPhishingWalletPercent")),
            "okx_total_holders": _f(t.get("totalHolders")),
        }

    def insider_signals(self, address: str) -> dict:
        """Combine the OKX dev/bundle/tags signals into one insider-label dict.

        Keys follow the `backtest.insider_labels.label_from_okx` contract:
          okx_rug_pull_count, okx_dev_total_tokens, okx_dev_holding_percent,
          okx_insiders_percent, okx_snipers_percent, okx_bundlers_percent,
          okx_top10_holdings_percent, okx_fresh_wallets_percent,
          okx_suspected_phishing_percent, okx_total_holders, okx_dev_address,
          okx_funding_address
        """
        dev = self.token_dev_info(address)
        launched = dev.get("devLaunchedInfo") or {}
        holding = dev.get("devHoldingInfo") or {}

        sig = {
            "okx_rug_pull_count": _f(launched.get("rugPullCount")),
            "okx_dev_total_tokens": _f(launched.get("totalTokens")),
            "okx_dev_migrated_count": _f(launched.get("migratedCount")),
            "okx_dev_golden_gem_count": _f(launched.get("goldenGemCount")),
            "okx_dev_holding_percent": _f(holding.get("devHoldingPercent")),
            "okx_dev_address": holding.get("devAddress") or "",
            "okx_funding_address": holding.get("fundingAddress") or "",
        }
        return sig


def _f(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default
