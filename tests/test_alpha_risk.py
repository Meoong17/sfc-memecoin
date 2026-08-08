"""Test Alpha / Risk Engine (Phase 2, spec §8 risk-adjusted alpha)."""
import pytest

from engines.alpha_risk import AlphaInputs, AlphaRiskEngine
from engines.insider_intel import InsiderResult
from engines.sybil_score import SybilResult


eng = AlphaRiskEngine()


def test_no_insider_no_discount():
    r = eng.compute(AlphaInputs(alpha=92, organic=87, safety=83, smart_money=91))
    assert r.risk_penalty == 0.0
    assert r.risk_adjusted_alpha == pytest.approx(92.0)
    assert r.downside_factors == []


def test_bullish_but_high_insider_risk_crashes_alpha():
    """Spec §8 example: ALPHA 92 but insider high -> RAA drops sharply."""
    insider = InsiderResult(token="X", exit_liquidity_risk="HIGH",
                            insider_distribution=True, ihr_class="HIGH", ihr=0.18)
    r = eng.compute(AlphaInputs(alpha=92, organic=87, safety=83, smart_money=91,
                                insider=insider))
    # 0.30 (exit high) + 0.20 (IHR high) + 0.15 (distribution) = 0.65
    assert r.risk_penalty == pytest.approx(0.65)
    assert r.risk_adjusted_alpha == pytest.approx(92.0 * 0.35)
    assert "exit_liquidity_high" in r.downside_factors


def test_lower_alpha_but_healthier_ranks_better_after_risk():
    """Spec §8: raw 84 with LOW insider is more attractive than 92 with HIGH insider."""
    healthy = AlphaInputs(alpha=84, organic=91, safety=94, smart_money=86,
                          insider=InsiderResult(token="Y", exit_liquidity_risk="LOW",
                                                insider_distribution=False, ihr_class="LOW"))
    risky = AlphaInputs(alpha=92, organic=87, safety=83, smart_money=91,
                        insider=InsiderResult(token="X", exit_liquidity_risk="HIGH",
                                              insider_distribution=True, ihr_class="HIGH"))
    rh = eng.compute(healthy)
    rr = eng.compute(risky)
    assert rh.risk_adjusted_alpha > rr.risk_adjusted_alpha


def test_sybil_high_penalty():
    sybil = SybilResult(token="X", sybil_risk=85.0)
    r = eng.compute(AlphaInputs(alpha=70, organic=70, safety=70, smart_money=70,
                                sybil=sybil))
    assert r.risk_penalty == pytest.approx(0.15)
    assert "sybil_high" in r.downside_factors


def test_alpha_heavily_penalized_not_fully_wiped():
    # 0.30 (exit high) + 0.30 (IHR critical) + 0.15 (distribution) = 0.75
    insider = InsiderResult(token="X", exit_liquidity_risk="HIGH",
                            insider_distribution=True, ihr_class="CRITICAL")
    r = eng.compute(AlphaInputs(alpha=20, organic=50, safety=50, smart_money=50,
                                insider=insider))
    assert r.risk_penalty == pytest.approx(0.75)
    assert r.risk_adjusted_alpha == pytest.approx(20.0 * 0.25)  # 5.0, not 0


def test_summary_shape():
    r = eng.compute(AlphaInputs(alpha=80, organic=80, safety=80, smart_money=80))
    s = r.summary()
    for k in ["alpha", "organic", "safety", "smart_money", "risk_adjusted_alpha",
              "risk_penalty", "downside_factors"]:
        assert k in s


def test_okx_dev_reputation_high_penalty():
    """OKX serial-rugger (dev_reputation_risk=HIGH) must discount alpha."""
    insider = InsiderResult(token="X", dev_reputation_risk="HIGH")
    r = eng.compute(AlphaInputs(alpha=60, organic=60, safety=60, smart_money=60,
                                insider=insider))
    assert r.risk_penalty == pytest.approx(0.30)
    assert r.risk_adjusted_alpha == pytest.approx(60.0 * 0.70)
    assert "okx_dev_reputation_HIGH" in r.downside_factors


def test_okx_dev_reputation_med_penalty():
    """OKX dev-sold-off / coordinated (dev_reputation_risk=MED) = 0.15."""
    insider = InsiderResult(token="X", dev_reputation_risk="MED")
    r = eng.compute(AlphaInputs(alpha=60, organic=60, safety=60, smart_money=60,
                                insider=insider))
    assert r.risk_penalty == pytest.approx(0.15)
    assert "okx_dev_reputation_MED" in r.downside_factors


def test_okx_low_dev_reputation_no_penalty():
    insider = InsiderResult(token="X", dev_reputation_risk="LOW")
    r = eng.compute(AlphaInputs(alpha=60, organic=60, safety=60, smart_money=60,
                                insider=insider))
    assert r.risk_penalty == 0.0
    assert not any(f.startswith("okx_") for f in r.downside_factors)
