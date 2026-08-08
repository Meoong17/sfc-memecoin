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
    outputs: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "chain": self.chain,
            "admitted": self.admitted,
            "risk_adjusted_alpha": round(self.risk_adjusted_alpha, 1),
            "confidence": round(self.confidence, 3),
            "insider_probability": round(self.insider_probability, 3),
            "confluence_label": self.confluence_label,
            "regime": self.regime,
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
        # engines used: Insider, Sybil share EV-021; Absorption uses EV-001
        conf_res = compute_confidence(self.registry, [
            EngineScores("Insider Intel", evidence_quality=0.8, completeness=0.9, stability=0.8),
            EngineScores("Sybil Score", evidence_quality=0.8, completeness=0.9, stability=0.8),
            EngineScores("Absorption", evidence_quality=0.9, completeness=0.8, stability=0.8),
        ], dqi=0.9)
        s.confidence = conf_res.final_confidence
        s.outputs["confidence"] = conf_res.summary()
        return s
