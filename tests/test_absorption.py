"""Test Absorption Engine (Phase 4)."""
import pytest

from engines.absorption import AbsorptionEngine, AbsorptionInputs


eng = AbsorptionEngine()


def test_strong_demand_weak_response_detects_absorption():
    inp = AbsorptionInputs(demand=0.9, liquidity=0.8, smart_money=0.8,
                           holder_growth=0.7, buy_pressure=0.9, social_attention=0.8,
                           price_response=0.2, whale_selling=0.1,
                           liquidity_stress=0.1, insider_supply=0.0)
    r = eng.compute("TOK", inp)
    assert r.absorption_detected
    assert r.absorption_score >= 0.6


def test_false_momentum_no_absorption():
    # price already ran (high price_response) with weak demand
    inp = AbsorptionInputs(demand=0.3, liquidity=0.3, smart_money=0.2,
                           holder_growth=0.2, buy_pressure=0.3, social_attention=0.9,
                           price_response=0.9, whale_selling=0.8,
                           liquidity_stress=0.5, insider_supply=0.5)
    r = eng.compute("TOK", inp)
    assert not r.absorption_detected
    assert r.absorption_score < 0.3


def test_neutral_balanced():
    inp = AbsorptionInputs(demand=0.5, liquidity=0.5, smart_money=0.5,
                           holder_growth=0.5, buy_pressure=0.5, social_attention=0.5,
                           price_response=0.5, whale_selling=0.5,
                           liquidity_stress=0.5, insider_supply=0.5)
    r = eng.compute("TOK", inp)
    assert r.absorption_score == pytest.approx(0.0)  # net zero
    assert not r.absorption_detected


def test_insider_supply_reduces_absorption():
    clean = AbsorptionInputs(demand=0.8, liquidity=0.8, smart_money=0.8,
                             holder_growth=0.8, buy_pressure=0.8, social_attention=0.8,
                             price_response=0.3, whale_selling=0.2,
                             liquidity_stress=0.2, insider_supply=0.0)
    leaky = AbsorptionInputs(demand=0.8, liquidity=0.8, smart_money=0.8,
                             holder_growth=0.8, buy_pressure=0.8, social_attention=0.8,
                             price_response=0.3, whale_selling=0.2,
                             liquidity_stress=0.2, insider_supply=0.8)
    rc = eng.compute("TOK", clean)
    rl = eng.compute("TOK", leaky)
    assert rc.absorption_score > rl.absorption_score


def test_summary_shape():
    r = eng.compute("TOK", AbsorptionInputs(demand=0.7, liquidity=0.7))
    s = r.summary()
    for k in ["token", "absorption_score", "absorption_detected",
              "demand_index", "supply_index"]:
        assert k in s
