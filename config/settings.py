"""Chain and API configuration for SFC Memecoin."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load .env if present (simple parser; avoids a hard dotenv dep for Phase 0).
def _load_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_env()


@dataclass
class ChainConfig:
    """Per-chain discovery & RPC settings."""
    name: str
    enabled: bool
    rpc_url: str | None
    dex: str
    notes: str = ""


CHAINS: dict[str, ChainConfig] = {
    "solana": ChainConfig(
        name="solana",
        enabled=True,
        rpc_url=os.getenv("SOLANA_RPC_URL"),
        dex="Raydium",
        notes="Primary; Helius/QuickNode RPC",
    ),
    "bsc": ChainConfig(
        name="bsc",
        enabled=True,
        rpc_url=os.getenv("BSC_RPC_URL"),
        dex="PancakeSwap",
        notes="EVM honeypot sim target",
    ),
    "robinhood": ChainConfig(
        name="robinhood",
        enabled=False,  # new chain, sparse tooling — deferred (plan §9)
        rpc_url=None,
        dex="RH DEX",
        notes="DEFERRED to later phase",
    ),
}


@dataclass
class APIConfig:
    birdeye_key: str | None = field(default_factory=lambda: os.getenv("BIRDEYE_API_KEY"))
    dex_screener_key: str | None = field(default_factory=lambda: os.getenv("DEXSCREENER_API_KEY"))
    gmgn_key: str | None = field(default_factory=lambda: os.getenv("GMGN_API_KEY"))
    twitter_bearer: str | None = field(default_factory=lambda: os.getenv("TWITTER_BEARER"))


@dataclass
class RateLimit:
    max_calls_per_sec: int
    max_calls_per_min: int


RATE_LIMITS: dict[str, RateLimit] = {
    "rpc": RateLimit(max_calls_per_sec=20, max_calls_per_min=600),
    "dex_api": RateLimit(max_calls_per_sec=2, max_calls_per_min=60),
    "social": RateLimit(max_calls_per_sec=1, max_calls_per_min=30),
}


def enabled_chains() -> list[str]:
    """Return names of chains currently enabled."""
    return [c.name for c in CHAINS.values() if c.enabled]


def get_chain(name: str) -> ChainConfig:
    if name not in CHAINS:
        raise KeyError(f"Unknown chain: {name}")
    return CHAINS[name]
