"""Live data wiring: fetchers -> TokenFeatures -> pipeline.

Builds a TokenFeatures (the pipeline input contract) from REAL API data using
the fetcher layer. This replaces manual/synthetic TokenFeatures construction
with live ingestion:

  discovery (DexScreener)  -> universe of token addresses
  token_detail (DexScreener)-> market snapshot -> alpha_raw/safety_raw inputs
  token_security (GMGN)    -> ContractFacts -> EV-002 (honeypot/risk)
  wallet_stats (GMGN)      -> WalletAnalytics -> classification features
  funding trace (Helius)   -> FundingEdge -> EV-021 (insider cluster)

Each source is optional and independent: if a key is missing, that component is
skipped (degraded but functional) rather than failing the whole pipeline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pipeline import TokenFeatures
from fetchers.dex_screener import DexScreenerFetcher, TokenMarketInfo

log = logging.getLogger("sfc_memecoin.wiring")


@dataclass
class LiveUniverse:
    """Universe of tokens fetched from real discovery."""
    tokens: list[TokenMarketInfo] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.tokens)

    def summaries(self) -> list[dict]:
        return [t.summary() for t in self.tokens]


class LiveSourceBundle:
    """Holds optional fetcher instances; each may be None if unavailable."""

    def __init__(self, *, dex_screener: DexScreenerFetcher | None = None,
                 gmgn=None, helius=None, okx=None) -> None:
        self.dex_screener = dex_screener
        self.gmgn = gmgn
        self.helius = helius
        self.okx = okx

    @classmethod
    def from_env(cls) -> "LiveSourceBundle":
        """Instantiate fetchers from .env; missing keys -> None (degraded)."""
        from fetchers.gmgn import GmgnFetcher
        bundle = cls()

        # DexScreener: always available (public, no key)
        try:
            bundle.dex_screener = DexScreenerFetcher(cache_ttl=300)
        except Exception as e:  # pragma: no cover
            log.warning("DexScreener unavailable: %s", e)

        # GMGN: needs GMGN_API_KEY
        try:
            bundle.gmgn = GmgnFetcher()
        except (ValueError, RuntimeError) as e:
            log.warning("GMGN unavailable (skip security/wallet): %s", e)

        # Helius: needs HELIUS_API_KEY
        try:
            from fetchers.helius import HeliusRpcFetcher
            bundle.helius = HeliusRpcFetcher(cache_ttl=300)
        except (ValueError, RuntimeError) as e:
            log.warning("Helius unavailable (skip funding trace): %s", e)

        # OKX Onchain OS: needs OKX_API_KEY + SECRET + PASSPHRASE
        try:
            from fetchers.okx import OkxFetcher
            bundle.okx = OkxFetcher()
        except (ValueError, RuntimeError) as e:
            log.warning("OKX unavailable (skip OKX memepump insider labels): %s", e)

        return bundle

    @property
    def available(self) -> list[str]:
        return [name for name, src in [("dex_screener", self.dex_screener),
                                       ("gmgn", self.gmgn),
                                       ("helius", self.helius),
                                       ("okx", self.okx)] if src is not None]


class LivePipelineWire:
    """Connects fetchers to the ScreeningPipeline via TokenFeatures."""

    def __init__(self, sources: LiveSourceBundle | None = None,
                 sources_from_env: bool = True) -> None:
        from pipeline import ScreeningPipeline
        self.sources = sources or (LiveSourceBundle.from_env() if sources_from_env
                                   else LiveSourceBundle())
        self.pipeline = ScreeningPipeline()

    # --- discovery ---
    def fetch_universe(self, limit: int = 20) -> LiveUniverse:
        """Fetch recent token profiles from DexScreener."""
        if self.sources.dex_screener is None:
            raise RuntimeError("DexScreener unavailable; cannot discover universe")
        profs = self.sources.dex_screener.token_profiles(limit=limit)
        return LiveUniverse(tokens=profs)

    # --- token -> TokenFeatures ---
    def enrich_market(self, info: TokenMarketInfo) -> TokenMarketInfo:
        """Fetch full market detail for a token (price/liq/vol/mcap).

        `token_profiles` only returns symbol+volume; `token_detail` adds the
        liquidity/price/mcap that drive the raw scores. Enrich when available.
        """
        if self.sources.dex_screener is None:
            return info
        try:
            detail = self.sources.dex_screener.token_detail(info.address, info.chain)
        except Exception as e:
            log.warning("token_detail failed for %s: %s", info.address, e)
            return info
        if detail is None:
            return info
        return detail

    def build_features(self, info: TokenMarketInfo) -> TokenFeatures:
        """Assemble a TokenFeatures from real data for one token."""
        f = TokenFeatures(token=info.address, chain=info.chain)
        now = datetime.now(timezone.utc)

        # market snapshot -> raw score inputs (normalized to 0-100)
        liq = max(0.0, info.liquidity_usd)
        vol = max(0.0, info.volume_24h)
        # liquidity + volume proxy for safety/alpha raw (illustrative scaling)
        f.safety_raw = min(100.0, 50.0 + liq / 1_000_000 * 30)
        f.alpha_raw = min(100.0, 40.0 + vol / 1_000_000 * 40)
        f.smart_money_raw = 50.0
        f.organic_raw = 50.0
        f.effective_circulating_supply = info.mcap or 0.0

        # GMGN token market microstructure -> measured Organic/Smart Money/Safety
        # (weight audit: core weights were hardcoded 50; now driven by real data).
        if self.sources.gmgn is not None:
            try:
                ms = self.sources.gmgn.market_stats(info.address, info.chain)
                f.market_stats = ms.summary()
                org, sm, safe = _map_core_weights(f.market_stats)
                f.organic_raw, f.smart_money_raw = org, sm
                f.safety_raw = safe
                f.alpha_raw = _map_alpha_raw(f.market_stats, volume=vol,
                                             liquidity=liq)
            except Exception as e:
                log.warning("GMGN market_stats failed for %s: %s", info.address, e)

        # GMGN security -> EV-002 + contract-security facts (renounced/LP)
        if self.sources.gmgn is not None:
            try:
                cf = self.sources.gmgn.token_security(info.address, info.chain)
                f.contract_risk_level = _risk_level(cf.buy_tax_pct, cf.sell_tax_pct,
                                                    cf.sell_sellable)
                f.is_honeypot = not cf.sell_sellable
                # capture LP/renounce facts so the screener can label a token
                # "verified/secure" (renounced + LP locked/burned + not honeypot)
                f.contract_sell_sellable = cf.sell_sellable
                f.contract_lp_locked_pct = cf.lp_locked_pct
                f.contract_lp_burned = cf.lp_burned
                f.contract_renounced = _gmgn_renounced_from_notes(cf.notes or [])
                f.deployer = info.address  # placeholder until dev lookup wired
            except Exception as e:
                log.warning("GMGN security failed for %s: %s", info.address, e)

        # Helius funding trace -> EV-021 (insider cluster).
        # Master wallet = the token's dev wallet (GMGN), funded sub-wallets
        # detected via on-chain transfers from that master. Only Solana (Helius
        # is Solana RPC). Degrades gracefully if no dev wallet / no edges.
        if self.sources.helius is not None and info.chain in ("solana", "sol"):
            try:
                master = None
                if self.sources.gmgn is not None:
                    master = self.sources.gmgn.find_dev_wallet(info.address, info.chain)
                if master:
                    edges = self.sources.helius.fetch_funding_edges(
                        master, token_mint=info.address, chain=info.chain, max_tx=60)
                    if edges:
                        f.funding_clusters = edges
                        f.deployer = master
            except Exception as e:
                log.warning("Helius funding trace failed for %s: %s", info.address, e)

        # GMGN wallet_stats -> classification features (dev wallet).
        # Populates the dev wallet's behavioral analytics (win rate, frequency,
        # fresh-wallet, early-entry) so WalletClassifier can use real signals.
        if self.sources.gmgn is not None and f.deployer:
            try:
                wa = self.sources.gmgn.wallet_stats(f.deployer, info.chain)
                if wa is not None:
                    f.wallet_analytics = [wa]
            except Exception as e:
                log.warning("GMGN wallet_stats failed for %s: %s", info.address, e)

        # OKX dev-reputation -> direct insider evidence (separate source from
        # GMGN/Helius). Fetches rugPullCount / devHoldingsPercent / holder
        # composition, which InsiderIntelligenceEngine consumes as insider
        # evidence. Solana only (memepump universe). Degrades gracefully.
        if self.sources.okx is not None and info.chain in ("solana", "sol"):
            try:
                okx_sig = self.sources.okx.insider_signals(info.address)
                # holder-composition tags (snipers/insiders/bundlers/top10) come
                # from token-details, not token-dev-info — merge them so the
                # engine sees the full OKX signal set per token.
                okx_sig.update(self.sources.okx.token_tags_by_address(info.address))
                if okx_sig:
                    f.okx_signals = okx_sig
            except Exception as e:
                log.warning("OKX insider signals failed for %s: %s", info.address, e)

        return f

    def score_from_market(self, info: TokenMarketInfo):
        """Full path: enrich with market detail -> build features -> run pipeline."""
        enriched = self.enrich_market(info)
        f = self.build_features(enriched)
        return self.pipeline.score_token(f)


def _risk_level(buy_tax: float, sell_tax: float, sellable: bool) -> str:
    """Map GMGN tax/sellability to a contract risk level (EV-002)."""
    if not sellable:
        return "CRITICAL"
    max_tax = max(buy_tax, sell_tax)
    if max_tax >= 20:
        return "CRITICAL"
    if max_tax >= 10:
        return "RISKY"
    if max_tax >= 5:
        return "WATCH"
    return "SAFE"


def _map_core_weights(ms: dict | None) -> tuple[float, float, float]:
    """Map GMGN token-market microstructure onto Organic / Smart Money / Safety.

    This is what makes the core weights MEASURED rather than constants (weight
    audit, docs/WEIGHT_AUDIT.md). All scaling is ILLUSTRATIVE (calibration
    doctrine) and returns baseline 50 when no market data is present (degraded,
    not a signal).

    Organic (quality of demand): high holder count + low sniper/bundler/fresh
    wallet share = organic demand. Organic = 50 + holders/1e5*10 - sniper_share*40
      - bundler_share*40 - fresh_share*20, clipped to [20,100].

    Smart Money (quality of wallet flow): high smart/renowned/whale wallet
    counts = sophisticated flow. SmartMoney = 50 + smart/1e3*30 + renowned/1e2*10
      - rat_share*30, clipped to [20,100].

    Safety (structural): higher LP locked = safer. Safety = 50 + locked_ratio*50,
      clipped to [20,100] (kept conservative vs the security gate).
    """
    if not ms:
        return 50.0, 50.0, 50.0
    holders = float(ms.get("holder_count", 0) or 0)
    smart = float(ms.get("smart_wallets", 0) or 0)
    sniper = float(ms.get("sniper_wallets", 0) or 0)
    bundler = float(ms.get("bundler_wallets", 0) or 0)
    fresh = float(ms.get("fresh_wallets", 0) or 0)
    whale = float(ms.get("whale_wallets", 0) or 0)
    renowned = float(ms.get("renowned_wallets", 0) or 0)
    rat = float(ms.get("rat_trader_wallets", 0) or 0)
    locked = float(ms.get("locked_ratio", 0) or 0)

    total_tagged = max(1.0, smart + sniper + bundler + fresh + whale + renowned + rat)
    sniper_share = sniper / total_tagged
    bundler_share = bundler / total_tagged
    fresh_share = fresh / total_tagged
    rat_share = rat / total_tagged

    organic = 50.0 + (holders / 1e5) * 10.0 - sniper_share * 40.0 \
        - bundler_share * 40.0 - fresh_share * 20.0
    smart_money = 50.0 + (smart / 1e3) * 30.0 + (renowned / 1e2) * 10.0 \
        + (whale / 1e3) * 10.0 - rat_share * 30.0
    safety = 50.0 + locked * 50.0

    return (min(100.0, max(20.0, organic)),
            min(100.0, max(20.0, smart_money)),
            min(100.0, max(20.0, safety)))


def _map_alpha_raw(ms: dict | None, *, volume: float, liquidity: float) -> float:
    """Map volume + liquidity + GMGN momentum/buy-pressure onto Alpha (0-100).

    Alpha = raw opportunity. Previously just `40 + vol/1M*40`; now also rewards
    price momentum (price_24h) and buy pressure (buy_volume_24h share) from
    GMGN market stats, so a token that is moving on strong demand scores higher
    than one moving on thin volume. Falls back to volume+liquidity only when no
    market data is present. All scaling ILLUSTRATIVE (calibration doctrine).
    """
    base = min(100.0, 40.0 + max(0.0, volume) / 1_000_000 * 40.0)
    if not ms:
        return base
    # price_24h is a fraction (e.g. 0.41 = +41%); clip momentum contribution
    momentum = float(ms.get("price_24h", 0) or 0)
    # buy pressure: buy_volume_24h / volume_24h, 0.5 = balanced -> ~no effect
    buy_vol = float(ms.get("buy_volume_24h", 0) or 0)
    tot_vol = float(ms.get("volume_24h", 0) or 0)
    buy_share = (buy_vol / tot_vol) if tot_vol > 0 else 0.5
    liq_bonus = min(10.0, max(0.0, liquidity) / 1_000_000 * 2.0)
    alpha = base + max(-15.0, min(15.0, momentum * 30.0)) \
        + (buy_share - 0.5) * 20.0 + liq_bonus
    return min(100.0, max(20.0, alpha))


def _gmgn_renounced_from_notes(notes: list) -> bool:
    """Parse GMGN `gmgn_is_renounced=...` from ContractFacts.notes.

    GMGN may serialize renounced as a bool (repr `True`) or string (`"True"`),
    so match the value case-insensitively rather than expecting a fixed string.
    Returns False when absent/unparseable (safe default).
    """
    for n in notes or []:
        if "gmgn_is_renounced=" in str(n):
            val = str(n).partition("gmgn_is_renounced=")[2].strip().lower()
            return val in ("true", "1", "yes")
    return False
