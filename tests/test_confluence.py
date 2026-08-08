"""Test Confluence Engine (Phase 5, spec §6.15)."""
from engines.confluence import ConfluenceEngine, ConfluenceInput, EvidenceSignal
from evidence.registry import build_canonical_registry


def test_high_confluence():
    inp = ConfluenceInput(
        token="TOK",
        signals=[
            EvidenceSignal("Liquidity", "liquidity_up", "opportunity", 0.9),
            EvidenceSignal("Smart Money", "sm_up", "opportunity", 0.8),
            EvidenceSignal("Social", "social_up", "opportunity", 0.7),
            EvidenceSignal("Absorption", "absorption", "opportunity", 0.8),
            EvidenceSignal("Security Gate", "no_dev_risk", "opportunity", 0.9),
        ],
    )
    r = ConfluenceEngine().analyze(inp)
    assert r.label == "HIGH_CONFLUENCE"
    assert r.net_confluence > 0.5
    assert r.risk_score == 0.0


def test_false_momentum():
    inp = ConfluenceInput(
        token="TOK",
        signals=[
            EvidenceSignal("Price", "price_up", "opportunity", 0.9),
            EvidenceSignal("Social", "social_up", "opportunity", 0.9),
            EvidenceSignal("Smart Money", "sm_down", "risk", 0.9),
            EvidenceSignal("Whale", "whale_selling", "risk", 0.8),
            EvidenceSignal("Security Gate", "larp", "risk", 0.9),
            EvidenceSignal("Insider Intel", "insider_distribution", "risk", 0.9),
        ],
    )
    r = ConfluenceEngine().analyze(inp)
    assert r.label == "FALSE_MOMENTUM"
    assert r.risk_score > r.opportunity_score  # risks dominate the facade
    assert "whale_selling" in r.independent_risks


def test_shared_evidence_dedup():
    """Signals from engines sharing EV-021 must not both count (anti-double-count)."""
    inp = ConfluenceInput(
        token="TOK",
        signals=[
            EvidenceSignal("Wallet Graph", "cluster", "opportunity", 0.9),
            EvidenceSignal("Sybil Score", "organic_holders", "opportunity", 0.5),
            EvidenceSignal("Liquidity", "liq", "opportunity", 0.6),
        ],
        shared_evidence_pairs={("Wallet Graph", "Sybil Score")},
    )
    r = ConfluenceEngine().analyze(inp)
    # weaker (Sybil 0.5) dropped as dependent; only 2 independent opps counted
    assert r.dropped_dependent == ["organic_holders"]
    assert "organic_holders" not in r.independent_opportunities
    assert len(r.independent_opportunities) == 2


def test_registry_based_dedup_ev021():
    """EV-021 shared by Wallet Graph + Sybil + Insider -> dedup applies."""
    reg = build_canonical_registry()
    inp = ConfluenceInput(
        token="TOK",
        signals=[
            EvidenceSignal("Wallet Graph", "wg", "opportunity", 0.8),
            EvidenceSignal("Insider Intel", "insider", "opportunity", 0.9),
            EvidenceSignal("Liquidity", "liq", "opportunity", 0.7),
        ],
        shared_evidence_pairs={
            ("Wallet Graph", "Sybil Score"), ("Wallet Graph", "Insider Intel"),
            ("Sybil Score", "Insider Intel"),
        },
    )
    r = ConfluenceEngine().analyze(inp)
    assert "insider" in r.dropped_dependent or "wg" in r.dropped_dependent
    assert len(r.independent_opportunities) <= 2


def test_summary_shape():
    r = ConfluenceEngine().analyze(ConfluenceInput(
        token="TOK", signals=[EvidenceSignal("X", "a", "opportunity", 0.5)]))
    s = r.summary()
    for k in ["token", "opportunity_score", "risk_score", "net_confluence",
              "label", "independent_opportunities", "independent_risks"]:
        assert k in s
