"""Pipeline orchestrator (spec §5 architecture).

MEME UNIVERSE -> DISCOVERY -> DQI -> SECURITY GATE -> VETO -> WALLET GRAPH ->
WALLET CLASSIFY -> INSIDER INTELLIGENCE -> MICROSTRUCTURE/SOCIAL/ABSORPTION/
REGIME -> CONFLUENCE -> ALPHA/RISK -> RISK-ADJUSTED ALPHA -> CONFIDENCE ->
FINAL RANKING -> LLM EXPLAINER

Phase 5 wires the components built across Phases 0-4 into one `score_token`
path. A `TokenFeatures` dataclass carries all evidence a token needs; each
engine consumes it (Measurement Contract: engines read evidence, never recompute
producers). The pipeline is deliberately declarative so it can be tested and
extended.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engines.absorption import AbsorptionEngine, AbsorptionInputs
from engines.alpha_risk import AlphaInputs, AlphaRiskEngine
from engines.confluence import ConfluenceEngine, ConfluenceInput, EvidenceSignal
from engines.insider_intel import InsiderInputs, InsiderIntelligenceEngine
from engines.regime import RegimeEngine, SeriesInput
from engines.sybil_score import SybilInputs, SybilScoreEngine
from engines.wallet_classify import WalletClassifier, WalletSignals
from engines.wallet_graph import WalletGraphEngine
from evidence.registry import EvidenceRegistry, build_canonical_registry
from scoring.confidence import EngineScores, compute_confidence


@dataclass
class TokenFeatures:
    """All evidence for one token, fed through the pipeline (spec §3)."""
    token: str
    chain: str
    # producers' outputs (evidence)
    funding_clusters: list = field(default_factory=list)     # EV-021
    swaps: list = field(default_factory=list)                # EV-001
    contract_risk_level: str = "SAFE"                        # EV-002
    contract_risk_score: float = 0.0
    is_honeypot: bool = False
    deployer: str = ""
    # contract-security facts (from GMGN token_security -> ContractFacts) used
    # to label a token as "verified/secure" (renounced + LP locked/burned +
    # not honeypot). Empty/None = unknown (degraded).
    contract_sell_sellable: bool = True
    contract_lp_locked_pct: float = 0.0    # fraction [0,1]
    contract_lp_burned: bool = False
    contract_renounced: bool = False
    # insider
    entry_events: list = field(default_factory=list)
    launch_minute: float = 0.0
    info_expansion_minute: float = 0.0
    suspected_insider_holdings: float = 0.0
    effective_circulating_supply: float = 0.0
    insider_cluster_supply: float = 0.0
    # social
    mention_series: list = field(default_factory=list)
    domains: list = field(default_factory=list)
    # wallet analytics (GMGN wallet_stats) -> classification features
    wallet_analytics: list = field(default_factory=list)
    # OKX dev-reputation signals (rugPullCount, devHoldingsPercent, holder
    # composition) -> direct insider evidence. keys `okx_` prefixed from
    # fetchers/okx.py. Empty = no OKX data (degraded, not an insider signal).
    okx_signals: dict = field(default_factory=dict)
    # GMGN token market microstructure (holder/smart/sniper/bundler wallet
    # counts + buy/sell microstructure) -> drives Organic/Smart Money weights.
    # None = no GMGN market data (degraded, weights fall back to baseline).
    market_stats: dict = field(default_factory=dict)
    # raw scores (could come from other producers)
    alpha_raw: float = 50.0
    organic_raw: float = 50.0
    safety_raw: float = 50.0
    smart_money_raw: float = 50.0


@dataclass
class TokenScore:
    token: str
    chain: str
    admitted: bool = True
    hard_block_reasons: list[str] = field(default_factory=list)
    risk_adjusted_alpha: float = 0.0
    confidence: float = 0.0
    insider_probability: float = 0.0
    confluence_label: str = "NEUTRAL"
    regime: str = "NORMAL"
    contract_status: str = "UNKNOWN"   # VERIFIED / LOCKED / RISKY / CRITICAL
    outputs: dict = field(default_factory=dict)

    def summary(self) -> dict:
        dev_rep = "LOW"
        ins = self.outputs.get("insider") or {}
        if isinstance(ins, dict):
            dev_rep = ins.get("dev_reputation_risk", "LOW")
        # core measured weights (from alpha_risk producer) so ranking/Telegram
        # can show Alpha/Organic/Safety/Smart Money, not just Risk-Adjusted Alpha.
        ar = self.outputs.get("alpha_risk") or {}
        alpha = round(float(ar.get("alpha", 0) or 0), 1)
        organic = round(float(ar.get("organic", 0) or 0), 1)
        safety = round(float(ar.get("safety", 0) or 0), 1)
        smart_money = round(float(ar.get("smart_money", 0) or 0), 1)
        return {
            "token": self.token,
            "chain": self.chain,
            "admitted": self.admitted,
            "risk_adjusted_alpha": round(self.risk_adjusted_alpha, 1),
            "alpha": alpha,
            "organic": organic,
            "safety": safety,
            "smart_money": smart_money,
            "confidence": round(self.confidence, 3),
            "insider_probability": round(self.insider_probability, 3),
            "dev_reputation_risk": dev_rep,
            "confluence_label": self.confluence_label,
            "regime": self.regime,
            "contract_status": self.contract_status,
            "outputs": list(self.outputs.keys()),
        }


class ScreeningPipeline:
    """Wires engines in spec order and scores one token."""

    def __init__(self, registry: EvidenceRegistry | None = None) -> None:
        self.registry = registry or build_canonical_registry()

    def score_token(self, f: TokenFeatures) -> TokenScore:
        s = TokenScore(token=f.token, chain=f.chain)
        from data_sources.dex_flow import aggregate_swaps
        from data_sources.wallet_funding import build_funding_graph
        from datetime import datetime
        from evidence.contracts import ContractRiskInput
        from engines.security_gate import SecurityGate

        # --- SECURITY GATE (hard filter) ---
        ev002 = ContractRiskInput(source="honeypot_sim", risk_level=f.contract_risk_level,
                                  risk_score=f.contract_risk_score, is_honeypot=f.is_honeypot)
        gate = SecurityGate()
        g = gate.evaluate(f.token, f.chain, ev002, deployer=f.deployer or None)
        s.outputs["security"] = g.summary()
        s.contract_status = _contract_status(f)
        if g.blocked:
            s.admitted = False
            s.hard_block_reasons = g.hard_reasons
            return s

        # --- build evidence objects ---
        fg = build_funding_graph(f.token, f.chain, f.funding_clusters)
        t0 = datetime(2026, 8, 1)
        flow = aggregate_swaps(f.token, f.chain, f.swaps, t0, t0)
        flow.window_start, flow.window_end = t0, t0

        # --- WALLET GRAPH (EV-021) ---
        wg = WalletGraphEngine(fg, flow).build()
        s.outputs["wallet_graph"] = wg.summary()

        # --- SYBIL (EV-021) ---
        syb = SybilScoreEngine(fg, flow).score(SybilInputs(
            holder_count=len(flow.trades_per_wallet),
            wallet_creation_proximity_ratio=0.1, identical_trade_size_ratio=0.1,
            repeated_dex_ratio=0.1))
        s.outputs["sybil"] = syb.summary()

        # --- WALLET CLASSIFY ---
        clf = WalletClassifier()
        # classification features from GMGN wallet_stats (when wired), else
        # empty-signal default for each trading wallet.
        wallet_sigs: dict[str, WalletSignals] = {}
        for wa in (f.wallet_analytics or []):
            wa_sig = wa.to_wallet_signals() if hasattr(wa, "to_wallet_signals") else wa
            wallet_sigs[wa_sig.wallet] = wa_sig
        classified = []
        for w in flow.trades_per_wallet:
            sig = wallet_sigs.get(w, WalletSignals(wallet=w))
            classified.append(clf.classify(sig).summary())
        s.outputs["wallet_classify"] = classified

        # --- INSIDER INTELLIGENCE (EV-021 + EV-001 + OKX dev-reputation) ---
        ins = InsiderIntelligenceEngine(fg, flow).analyze(f.token, InsiderInputs(
            entry_events=f.entry_events, launch_minute=f.launch_minute,
            info_expansion_minute=f.info_expansion_minute,
            suspected_insider_holdings=f.suspected_insider_holdings,
            effective_circulating_supply=f.effective_circulating_supply,
            insider_cluster_supply=f.insider_cluster_supply,
            okx_signals=f.okx_signals))
        s.insider_probability = ins.insider_probability
        s.outputs["insider"] = ins.summary()

        # --- ABSORPTION ---
        abs_r = AbsorptionEngine().compute(f.token, AbsorptionInputs(
            demand=f.organic_raw / 100.0, liquidity=0.5, smart_money=f.smart_money_raw / 100.0,
            holder_growth=0.5, buy_pressure=0.5, social_attention=0.5,
            price_response=0.3, whale_selling=0.2, liquidity_stress=0.2,
            insider_supply=ins.ihr))
        s.outputs["absorption"] = abs_r.summary()

        # --- REGIME ---
        reg_r = RegimeEngine().analyze(f.token, [
            SeriesInput("price", [x for x in f.mention_series or [0]] or [0, 0])])
        s.regime = reg_r.regime
        s.outputs["regime"] = reg_r.summary()

        # --- CONFLUENCE (independent evidence only) ---
        signals = [
            EvidenceSignal("Absorption", "absorption", "opportunity", abs_r.absorption_score),
            EvidenceSignal("Smart Money", "sm_quality", "opportunity", f.smart_money_raw / 100.0),
            EvidenceSignal("Insider Intel", "insider_risk", "risk", ins.insider_probability),
            EvidenceSignal("Sybil Score", "sybil_risk", "risk", syb.sybil_risk / 100.0),
        ]
        conf = ConfluenceEngine().analyze(ConfluenceInput(token=f.token, signals=signals))
        s.confluence_label = conf.label
        s.outputs["confluence"] = conf.summary()

        # --- ALPHA / RISK -> RISK-ADJUSTED ALPHA ---
        ar = AlphaRiskEngine().compute(AlphaInputs(
            alpha=f.alpha_raw, organic=f.organic_raw, safety=f.safety_raw,
            smart_money=f.smart_money_raw, insider=ins, sybil=syb))
        s.risk_adjusted_alpha = ar.risk_adjusted_alpha
        s.outputs["alpha_risk"] = ar.summary()

        # --- CONFIDENCE (multiplicative x DQI, shared-evidence discount) ---
        # Derived from REAL data presence on TokenFeatures (not hardcoded): a
        # token scored with GMGN+OKX+Helius evidence gets higher confidence
        # than one with only Dex. Engines sharing EV-021 (Insider, Sybil) are
        # discounted by the registry.
        engine_scores, dqi = _confidence_from_data(f)
        conf_res = compute_confidence(self.registry, engine_scores, dqi=dqi)
        s.confidence = conf_res.final_confidence
        s.outputs["confidence"] = conf_res.summary()
        return s


# ILLUSTRATIVE LP threshold for "secure" contract labeling (calibration doctrine).
_LP_SECURE_MIN = 0.5


def _contract_status(f: TokenFeatures) -> str:
    """Label a token's contract as VERIFIED / LOCKED / RISKY / CRITICAL.

    VERIFIED = not honeypot, sellable, renounced, AND LP secured (burned OR
    locked >= threshold) — the "safe/verified smart-contract coin" badge.
    LOCKED   = sellable, LP secured, but not renounced (ownership still held).
    RISKY    = sellable but LP unsecured (low/no lock, not burned).
    CRITICAL = honeypot (cannot sell) — should be hard-blocked anyway.
    UNKNOWN  = no GMGN contract facts available (degraded).
    """
    if f.is_honeypot:
        return "CRITICAL"
    if not f.contract_sell_sellable:
        return "CRITICAL"
    lp_secure = f.contract_lp_burned or f.contract_lp_locked_pct >= _LP_SECURE_MIN
    if f.contract_renounced and lp_secure:
        return "VERIFIED"
    if lp_secure:
        return "LOCKED"
    if f.contract_renounced or f.contract_lp_locked_pct > 0 or f.contract_lp_burned:
        return "RISKY"
    return "UNKNOWN"


# ILLUSTRATIVE data-presence weights for confidence components (calibration
# doctrine). Completeness/quality/DQI are derived from REAL data presence on the
# TokenFeatures, not hardcoded — so confidence reflects how much evidence was
# actually collected for this token.
def _has_data(v) -> bool:
    """True if a feature carries real data (non-empty)."""
    if v is None:
        return False
    if isinstance(v, dict):
        return bool(v)
    if isinstance(v, (list, tuple, set)):
        return len(v) > 0
    try:
        return bool(float(v))
    except (TypeError, ValueError):
        return bool(v)


def _confidence_from_data(f: TokenFeatures) -> tuple[list, float]:
    """Derive per-engine confidence inputs + DQI from real data presence.

    Returns (engine_scores, dqi). Each engine's completeness/quality tracks
    whether its actual evidence sources returned data:

      Insider Intel  <- okx_signals OR funding_clusters (EV-021) OR entry_events
      Sybil          <- funding_clusters (EV-021)
      Absorption     <- swaps (EV-001) OR market_stats (demand/liquidity)

    DQI reflects how many independent sources contributed, so a token scored
    with GMGN+OKX+Helius data has higher confidence than one with only Dex.
    This replaces the previous hardcoded (0.8/0.9/0.8) components — the 0.39
    confidence was constant across all tokens regardless of data quality.
    """
    # per-engine completeness: did its sources return real data?
    insider_src = any([_has_data(f.okx_signals), _has_data(f.funding_clusters),
                       _has_data(f.entry_events)])
    sybil_src = _has_data(f.funding_clusters)
    abs_src = any([_has_data(f.swaps), _has_data(f.market_stats)])
    # wallet analytics + market stats add to overall data richness
    wallet_src = _has_data(f.wallet_analytics)
    market_src = _has_data(f.market_stats)

    def engine_scores(name: str, src: bool) -> EngineScores:
        # completeness: 1.0 if source present, 0.4 if absent (degraded)
        completeness = 1.0 if src else 0.4
        # evidence_quality: modest bonus when multiple independent sources
        quality = 0.85 if src else 0.5
        # stability: better with richer data (market + wallet), else neutral
        stability = 0.9 if (src and market_src) else 0.8
        return EngineScores(name, evidence_quality=quality,
                            completeness=completeness, stability=stability)

    scores = [
        engine_scores("Insider Intel", insider_src),
        engine_scores("Sybil Score", sybil_src),
        engine_scores("Absorption", abs_src),
    ]
    # DQI = fraction of tracked sources actually present
    present = sum([insider_src, sybil_src, abs_src, wallet_src, market_src])
    dqi = 0.4 + 0.12 * present   # 0.4 (all missing) .. 1.0 (all present)
    dqi = max(0.4, min(1.0, dqi))
    return scores, dqi
