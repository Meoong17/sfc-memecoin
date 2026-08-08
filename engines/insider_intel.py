"""Insider Intelligence Engine P0 (spec §6.6) — dedicated Insider engine.

Structure: Entry Edge -> Hold Exposure -> Exit Flow -> Insider Risk.
Consumers EV-021 (funding graph) + EV-001 (swap flow); does NOT recompute them
(Measurement Contract §3).

P0 implements the rule-based components:
  6.6.1 Insider Entry Detection       (early entry before public info)
  6.6.2 Funding cluster exposure       (coordinated insider cluster)
  6.6.3 Pre-launch accumulation        (per-role supply split)
  6.6.4 Insider Holding Risk (IHR)     (suspected insider holdings / supply)
  6.6.5 Insider Distribution Detector  (insider selling while public demand up)
  6.6.6 Exit Liquidity Detection       (public as exit liquidity)
  6.6.7 Insider Timing Advantage (ITA)
  6.6.8 Insider Confidence (probabilistic, evidence + counter-evidence)

NOTE: IHR thresholds and ITA formula are ILLUSTRATIVE (docs/CALIBRATION.md).
Insider probability model is rule-based here; learned model is P2/P3.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from config.thresholds import get
from data_sources.dex_flow import DexFlowSnapshot
from data_sources.wallet_funding import FundingGraph, FundingCluster


@dataclass
class EntryEvent:
    wallet: str
    buy_ts_minutes: float          # minutes relative to public launch (negative = before)
    amount: float


@dataclass
class InsiderInputs:
    """Raw inputs to the Insider Intelligence Engine P0."""
    entry_events: list[EntryEvent] = field(default_factory=list)
    launch_minute: float = 0.0            # T+00
    info_expansion_minute: float = 0.0    # when public info exploded
    suspected_insider_holdings: float = 0.0
    effective_circulating_supply: float = 0.0
    insider_cluster_supply: float = 0.0   # supply held by insider clusters
    supply_by_role: dict[str, float] = field(default_factory=dict)  # role -> pct of supply
    okx_signals: dict = field(default_factory=dict)  # OKX dev-reputation (rug/dev/holder)


@dataclass
class InsiderResult:
    token: str
    insider_probability: float = 0.0      # 0..1 (rule-based in P0)
    confidence: float = 0.0               # 0..1
    ihr: float = 0.0                      # Insider Holding Risk [0,1]
    ihr_class: str = "LOW"
    insider_distribution: bool = False
    distribution_level: str = "NONE"
    exit_liquidity_risk: str = "LOW"      # LOW / MED / HIGH
    ita: float = 0.0                      # Insider Timing Advantage [0,1]
    early_entry_events: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    counter_evidence: list[str] = field(default_factory=list)
    # OKX dev-reputation downside (serial rugger / dev sold-off / coordination),
    # mapped separately from IHR/exit-liquidity so RAA can discount it without
    # double-counting. LOW/MED/HIGH. ILLUSTRATIVE (docs/CALIBRATION.md).
    dev_reputation_risk: str = "LOW"

    def summary(self) -> dict:
        return {
            "token": self.token,
            "insider_probability": round(self.insider_probability, 3),
            "confidence": round(self.confidence, 3),
            "ihr": round(self.ihr, 3),
            "ihr_class": self.ihr_class,
            "insider_distribution": self.insider_distribution,
            "distribution_level": self.distribution_level,
            "exit_liquidity_risk": self.exit_liquidity_risk,
            "ita": round(self.ita, 3),
            "dev_reputation_risk": self.dev_reputation_risk,
            "evidence": self.evidence,
            "counter_evidence": self.counter_evidence,
        }


class InsiderIntelligenceEngine:
    """P0 rule-based Insider Intelligence Engine."""

    def __init__(self, funding: FundingGraph, flow: DexFlowSnapshot | None = None) -> None:
        self.funding = funding
        self.flow = flow

    # --- 6.6.1 Insider Entry Detection ---
    def _early_entries(self, ins: InsiderInputs) -> list[str]:
        early = []
        for e in ins.entry_events:
            # entry strictly before public info expansion => early access candidate
            if e.buy_ts_minutes < ins.info_expansion_minute and e.buy_ts_minutes < ins.launch_minute:
                early.append(e.wallet)
        return early

    # --- 6.6.7 Insider Timing Advantage ---
    def _compute_ita(self, ins: InsiderInputs, early: list[str]) -> float:
        if not ins.entry_events:
            return 0.0
        # average lead time of early entries relative to info expansion (positive lead)
        leads = [ins.info_expansion_minute - e.buy_ts_minutes
                 for e in ins.entry_events if e.wallet in early]
        if not leads:
            return 0.0
        avg_lead = sum(leads) / len(leads)
        coverage = len(early) / len(ins.entry_events)
        # ITA combines lead magnitude (clipped to [0,60]min) and coverage
        return min(1.0, (avg_lead / 60.0) * 0.6 + coverage * 0.4)

    # --- 6.6.4 Insider Holding Risk ---
    def _ihr_class(self, ihr: float) -> str:
        if ihr < get("ihr_low_max").value:
            return "LOW"
        if ihr < get("ihr_moderate_max").value:
            return "MODERATE"
        if ihr < get("ihr_high_max").value:
            return "HIGH"
        return "CRITICAL"

    # --- 6.6.5 + 6.6.6 distribution / exit liquidity ---
    def _distribution(self, ins: InsiderInputs) -> tuple[bool, str]:
        # P0 placeholder: insider distribution inferred from insider cluster supply
        # shrinking vs public demand; real per-wallet sell trace wired later.
        if self.flow is None:
            return False, "NONE"
        # if insider cluster holds significant supply and public net flow is BUY
        # while insider cluster is selling (placeholder signal)
        insider_share = (ins.insider_cluster_supply / ins.effective_circulating_supply
                         if ins.effective_circulating_supply else 0.0)
        if insider_share >= 0.15 and self.flow.net_flow_direction == "BUY":
            return True, "HIGH"
        if insider_share >= 0.05:
            return True, "MED"
        return False, "NONE"

    # --- main ---
    def analyze(self, token: str, ins: InsiderInputs) -> InsiderResult:
        r = InsiderResult(token=token)
        r.early_entry_events = self._early_entries(ins)
        r.ita = self._compute_ita(ins, r.early_entry_events)

        # IHR
        r.ihr = (ins.suspected_insider_holdings / ins.effective_circulating_supply
                 if ins.effective_circulating_supply else 0.0)
        r.ihr = max(0.0, min(1.0, r.ihr))
        r.ihr_class = self._ihr_class(r.ihr)

        # Distribution + exit liquidity
        r.insider_distribution, r.distribution_level = self._distribution(ins)
        # Exit liquidity HIGH when insider distribution active AND public buying
        if r.insider_distribution and self.flow is not None and self.flow.net_flow_direction == "BUY":
            r.exit_liquidity_risk = "HIGH"
        elif r.insider_distribution:
            r.exit_liquidity_risk = "MED"

        # Evidence / counter-evidence
        if r.early_entry_events:
            r.evidence.append(f"early_entries_{len(r.early_entry_events)}")
        if r.ita > 0.3:
            r.evidence.append(f"timing_advantage_{r.ita:.2f}")
        if self.funding.cluster_count > 0:
            r.evidence.append(f"funding_cluster_{self.funding.cluster_count}")
        if r.insider_distribution:
            r.evidence.append("insider_distribution")
        if r.ihr >= 0.20:
            r.counter_evidence.append("no_direct_dev_relationship_check")

        # --- OKX dev-reputation as direct insider evidence (ILLUSTRATIVE) ---
        # OKX fields are PERCENT (0-100). A serial rugger / dev sold-off / tight
        # holder composition is DIRECT on-chain insider evidence, independent of
        # the funding-cluster path. Thresholds ILLUSTRATIVE (docs/CALIBRATION.md).
        okx = ins.okx_signals or {}
        def okx_f(k, d=0.0) -> float:
            v = okx.get(k)
            if v is None:
                return d
            try:
                return float(v)
            except (TypeError, ValueError):
                return d
        okx_rug = int(okx_f("okx_rug_pull_count"))
        okx_dev_hold = okx_f("okx_dev_holding_percent")
        okx_dev_total = okx_f("okx_dev_total_tokens")
        okx_snipers = okx_f("okx_snipers_percent")
        okx_insiders = okx_f("okx_insiders_percent")
        okx_bundlers = okx_f("okx_bundlers_percent")
        okx_top10 = okx_f("okx_top10_holdings_percent")
        okx_coord = max(okx_snipers, okx_insiders, okx_bundlers)

        if okx_rug >= 1:
            r.evidence.append(f"okx_serial_rugger_{okx_rug}")
        if okx_dev_hold < 20.0 and okx_dev_total >= 1:
            r.evidence.append(f"okx_dev_sold_off_{okx_dev_hold:.1f}%")
        if okx_coord >= 30.0:
            r.evidence.append(f"okx_coordinated_{okx_coord:.1f}%")
        if okx_top10 >= 60.0:
            r.evidence.append(f"okx_concentrated_top10_{okx_top10:.1f}%")

        # OKX dev-reputation downside level (separate from IHR/exit so RAA can
        # discount it without double-counting). ILLUSTRATIVE.
        #   HIGH: serial rugger (strongest direct signal)
        #   MED : dev sold off AND/OR coordinated insider composition
        if okx_rug >= 1:
            r.dev_reputation_risk = "HIGH"
        elif (okx_dev_hold < 20.0 and okx_dev_total >= 1) or okx_coord >= 30.0:
            r.dev_reputation_risk = "MED"

        # --- 6.6.8 Insider probability (rule-based P0) ---
        score = 0.0
        if r.early_entry_events:
            score += 0.30
        if r.ita > 0.3:
            score += 0.15
        if self.funding.cluster_count > 0:
            score += 0.20
        if r.insider_distribution:
            score += 0.25
        # OKX direct dev-reputation contributions (ILLUSTRATIVE)
        if okx_rug >= 1:
            score += 0.30                       # serial rugger = strongest direct signal
        if okx_dev_hold < 20.0 and okx_dev_total >= 1:
            score += 0.20                       # dev sold off its position
        if okx_coord >= 30.0:
            score += 0.15                       # coordinated insider/sniper/bundler
        if okx_top10 >= 60.0:
            score += 0.10                       # top-heavy holder concentration
        r.insider_probability = min(1.0, round(score, 3))
        r.confidence = round(min(1.0, 0.5 + 0.1 * len(r.evidence)), 3)
        return r
