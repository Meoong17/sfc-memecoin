"""Test LLM Explainer stub (deterministic rule-based; LLM is optional gloss)."""
import pytest

from llm_explainer import LLMExplainer, explain_ranking, explain_token
from pipeline import TokenScore


def _score(**kw) -> TokenScore:
    base = dict(
        token="TOKEN", chain="solana", admitted=True, risk_adjusted_alpha=42.0,
        confidence=0.5, insider_probability=0.6, confluence_label="NEUTRAL",
        contract_status="LOCKED",
        outputs={
            "insider": {"insider_probability": 0.6, "dev_reputation_risk": "HIGH",
                        "evidence": ["okx_serial_rugger_5", "okx_dev_sold_off_0.0%"]},
            "alpha_risk": {"downside_factors": ["okx_dev_reputation_HIGH",
                                                "insider_distribution"]},
        },
    )
    base.update(kw)
    return TokenScore(**base)


def test_explain_token_blocked():
    s = TokenScore(token="T", chain="sol", admitted=False,
                   hard_block_reasons=["honeypot"])
    text = explain_token(s)
    assert "DIBLOKIR" in text
    assert "honeypot" in text


def test_explain_token_reads_downside_factors():
    text = explain_token(_score())
    assert "RAA 42.0" in text
    assert "RAA terkoreksi karena" in text
    assert "reputasi dev HIGH" in text
    assert "insider terdistribusi" in text


def test_explain_token_reads_okx_evidence():
    text = explain_token(_score())
    assert "dev pernah rug-pull berulang kali" in text
    assert "dev sudah menjual posisinya" in text


def test_explain_token_contract_and_devrisk():
    text = explain_token(_score())
    assert "Contract: LP aman tapi belum renounced" in text  # LOCKED gloss
    assert "DevRisk HIGH" in text


def test_explain_ranking_uses_symbols():
    s = _score(token="AAA")
    texts = explain_ranking([s], symbols={"AAA": "TOAD"})
    assert "TOAD: RAA" in texts[0]


def test_explainer_disabled_returns_rule_text(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    ex = LLMExplainer(api_key="", model="")
    assert ex.enabled is False
    rule = explain_token(_score())
    assert ex.gloss(rule) == rule  # no-op


def test_explainer_gloss_falls_back_on_api_error(monkeypatch):
    ex = LLMExplainer(api_key="k", model="m", base_url="http://127.0.0.1:9")
    assert ex.enabled is True
    rule = explain_token(_score())
    # connection refused -> _chat returns "" -> gloss falls back to rule text
    assert ex.gloss(rule) == rule
