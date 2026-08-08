"""Confluence Engine (spec §6.15) — combine independent evidence.

Combines only INDEPENDENT evidence into an Opportunity vs Risk assessment
before the Alpha/Risk Score. Uses the Measurement Contract registry to ensure
engines sharing an Evidence ID are not treated as independent confirmations
(anti-double-counting; v5 §6.15 note).

Spec examples:
  HIGH CONFLUENCE: Liquidity up, Smart Money up, Social up, Absorption up,
                   Dev/LARP/Sybil/Insider Risk LOW
  FALSE MOMENTUM:  Price up, Social up, Smart Money DOWN, Whale Selling up,
                   LARP HIGH, Insider Distribution HIGH
"""
from __future__ import annotations

from dataclasses import dataclass, field

from evidence.registry import EvidenceRegistry


@dataclass
class EvidenceSignal:
    """One independent opportunity (+) or risk (-) signal from an engine."""
    engine: str
    name: str
    direction: str        # "opportunity" or "risk"
    strength: float = 0.5 # 0..1 magnitude


@dataclass
class ConfluenceResult:
    token: str
    opportunity_score: float = 0.0     # 0..1
    risk_score: float = 0.0            # 0..1
    net_confluence: float = 0.0        # opportunity - risk, [-1,1]
    label: str = "NEUTRAL"
    independent_opportunities: list[str] = field(default_factory=list)
    independent_risks: list[str] = field(default_factory=list)
    dropped_dependent: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "token": self.token,
            "opportunity_score": round(self.opportunity_score, 3),
            "risk_score": round(self.risk_score, 3),
            "net_confluence": round(self.net_confluence, 3),
            "label": self.label,
            "independent_opportunities": self.independent_opportunities,
            "independent_risks": self.independent_risks,
        }


@dataclass
class ConfluenceInput:
    token: str
    signals: list[EvidenceSignal] = field(default_factory=list)
    # engine pairs known to share evidence (from registry); if None, no dedup
    shared_evidence_pairs: set[tuple[str, str]] = field(default_factory=set)


class ConfluenceEngine:
    """Combines independent evidence, dropping signals that are not independent."""

    def analyze(self, inp: ConfluenceInput) -> ConfluenceResult:
        r = ConfluenceResult(token=inp.token)
        opp_total, risk_total = 0.0, 0.0
        n_opp, n_risk = 0, 0

        # Dedup: if two signals come from engines sharing evidence, keep the
        # strongest and mark the weaker as dropped-dependent (no double count).
        kept = []
        for i, sig in enumerate(inp.signals):
            dropped = False
            for j, other in enumerate(inp.signals):
                if i == j:
                    continue
                pair = (sig.engine, other.engine)
                pair_r = (other.engine, sig.engine)
                if pair in inp.shared_evidence_pairs or pair_r in inp.shared_evidence_pairs:
                    # same evidence source; keep stronger only
                    if sig.strength < other.strength:
                        r.dropped_dependent.append(sig.name)
                        dropped = True
                        break
            if not dropped:
                kept.append(sig)

        for sig in kept:
            if sig.direction == "opportunity":
                opp_total += sig.strength
                n_opp += 1
                r.independent_opportunities.append(sig.name)
            else:
                risk_total += sig.strength
                n_risk += 1
                r.independent_risks.append(sig.name)

        # Sum-based with saturation: more independent risks raise risk score.
        # (Averaging wrongly favored fewer signals; count must matter for
        # FALSE_MOMENTUM detection where many risks outweigh few opportunities.)
        r.opportunity_score = min(1.0, opp_total / 2.0)
        r.risk_score = min(1.0, risk_total / 2.0)
        r.net_confluence = max(-1.0, min(1.0, r.opportunity_score - r.risk_score))

        if r.net_confluence >= 0.5:
            r.label = "HIGH_CONFLUENCE"
        elif r.risk_score >= 0.6 and r.net_confluence < 0.15:
            # deceivingly bullish facade with strong risk (spec: price/social up
            # but smart money down + whale selling + insider distribution)
            r.label = "FALSE_MOMENTUM"
        elif r.net_confluence > 0.15:
            r.label = "MODERATE_OPPORTUNITY"
        else:
            r.label = "NEUTRAL"
        return r


def confluence_from_registry(reg: EvidenceRegistry, token: str,
                             signals: list[EvidenceSignal]) -> ConfluenceResult:
    """Build shared-evidence pairs from the registry and run confluence."""
    pairs = set()
    for eid in reg.evidence_ids():
        cons = list(reg.consumers_of(eid))
        for a in cons:
            for b in cons:
                if a != b:
                    pairs.add((a, b))
    return ConfluenceEngine().analyze(ConfluenceInput(token=token, signals=signals,
                                                      shared_evidence_pairs=pairs))
