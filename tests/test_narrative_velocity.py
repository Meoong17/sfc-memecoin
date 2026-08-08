"""Test Narrative Velocity Engine (Phase 3)."""
import pytest

from engines.narrative_velocity import NarrativeDomain, NarrativeInputs, NarrativeVelocityEngine


eng = NarrativeVelocityEngine()


def test_spec_example_series_accelerates():
    # spec §6.12: 120 -> 190 -> 340 -> 720 -> 1450
    inp = NarrativeInputs(token="TOK", mention_series=[120, 190, 340, 720, 1450])
    r = eng.analyze(inp)
    assert r.mention_growth > 1.0
    assert r.velocity_label == "ACCELERATING"


def test_cross_domain_confirmation_raises_velocity():
    inp = NarrativeInputs(
        token="TOK",
        mention_series=[100, 300],
        domains=[
            NarrativeDomain("social", current=300, prev=100),
            NarrativeDomain("dex_flow", current=200, prev=50),
            NarrativeDomain("wallets", current=150, prev=60),
            NarrativeDomain("liquidity", current=120, prev=100),
        ],
    )
    r = eng.analyze(inp)
    # social(2.0), dex_flow(3.0), wallets(1.5), liquidity(0.2) all >= 0.2 -> 4
    assert r.cross_domain_confirmations == 4
    assert r.velocity >= 0.7


def test_flat_no_growth():
    inp = NarrativeInputs(token="TOK", mention_series=[100, 100])
    r = eng.analyze(inp)
    assert r.velocity_label == "FLAT"
    assert r.cross_domain_confirmations == 0


def test_single_point_zero():
    inp = NarrativeInputs(token="TOK", mention_series=[100])
    r = eng.analyze(inp)
    assert r.mention_growth == 0.0
    assert r.velocity == 0.0


def test_declining_label():
    inp = NarrativeInputs(token="TOK", mention_series=[1000, 500])
    r = eng.analyze(inp)
    assert r.velocity_label == "DECLINING"


def test_summary_shape():
    r = eng.analyze(NarrativeInputs(token="TOK", mention_series=[50, 100]))
    s = r.summary()
    for k in ["token", "velocity", "velocity_label", "mention_growth",
              "cross_domain_confirmations", "confirming_domains"]:
        assert k in s
