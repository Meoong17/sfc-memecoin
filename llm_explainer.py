"""LLM Explainer stub (spec §5 final stage: RANKING -> LLM EXPLAINER).

Architecture rule (#6): the LLM EXPLAINS why a token is ranked the way it is,
it NEVER decides ("I feel this goes up"). The ranking itself is produced by the
pipeline (Risk-Adjusted Alpha) and is never changed here.

This module:
  1. Builds a deterministic, rule-based explanation per token from the REAL
     evidence in `TokenScore.outputs` (insider evidence, alpha_risk downside
     factors, contract status, dev reputation, confluence) — no LLM needed, so
     it always works and is fully reproducible/testable.
  2. Optionally calls a real LLM (chat-completions) to rephrase the explanation
     in natural language WHEN an `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`
     is set in .env. If not configured, it returns the rule-based explanation
     (no-op safe). This keeps the LLM as an explainer-only layer.

The rule-based text is the durable contract; the LLM call is a thin gloss on top.
"""

from __future__ import annotations

import os
from typing import Any


# ---------------------------------------------------------------------------
# Rule-based explanation (deterministic, from TokenScore.outputs)
# ---------------------------------------------------------------------------
_CONFLUENCE_GLOSS = {
    "HIGH_CONFLUENCE": "banyak bukti independen searah (paling kuat)",
    "MODERATE_OPPORTUNITY": "bukti cukup, ada peluang moderat",
    "NEUTRAL": "tidak ada arah jelas",
    "FALSE_MOMENTUM": "momentum tampak bullish tapi risiko kuat membatalkannya",
}

_INSIDER_EVIDENCE_GLOSS = {
    "okx_serial_rugger": "dev pernah rug-pull berulang kali",
    "okx_dev_sold_off": "dev sudah menjual posisinya (holding ~0)",
    "okx_coordinated": "konsentrasi holder terkoordinasi (sniper/insider/bundler)",
    "okx_concentrated_top10": "top-10 holder menguasai porsi besar",
    "funding_cluster": "cluster wallet didanai dari master yang sama",
    "early_entries": "entry wallet sebelum info publik meluas",
    "timing_advantage": "wallet punya keunggulan waktu entry (ITA)",
    "insider_distribution": "insider menjual saat publik membeli (exit liquidity)",
}

_DEV_REP_GLOSS = {
    "LOW": "reputasi dev tidak menimbulkan kekhawatiran",
    "MED": "reputasi dev moderat (dev jual/koordinasi)",
    "HIGH": "reputasi dev buruk (serial rugger / jual habis)",
}

_CONTRACT_GLOSS = {
    "VERIFIED": "kontrak aman & terverifikasi (renounced + LP locked/burned)",
    "LOCKED": "LP aman tapi belum renounced",
    "RISKY": "LP tidak terjamin",
    "CRITICAL": "kontrak honeypot/rug — seharusnya diblokir",
    "UNKNOWN": "data kontrak tidak tersedia",
}


def _insider_evidence_readable(evidence: list | None) -> list[str]:
    out = []
    for e in evidence or []:
        matched = False
        for prefix, gloss in _INSIDER_EVIDENCE_GLOSS.items():
            if e.startswith(prefix):
                out.append(gloss)
                matched = True
                break
        if not matched and isinstance(e, str):
            out.append(e.replace("_", " "))
    return out


def explain_token(score: Any, *, symbol: str = "") -> str:
    """Build a plain-text (Indonesian) explanation for one TokenScore.

    Reads the actual outputs dict (insider evidence, alpha_risk downside
    factors, contract status, dev reputation, confluence) — never the LLM.
    """
    outs = score.outputs if isinstance(score.outputs, dict) else {}
    ins = outs.get("insider") or {}
    ar = outs.get("alpha_risk") or {}

    name = symbol or (getattr(score, "token", "?") or "?")
    if not getattr(score, "admitted", True):
        reasons = getattr(score, "hard_block_reasons", []) or []
        block = ", ".join(reasons) if reasons else "gagal filter keamanan"
        return f"{name}: DIBLOKIR — {block}."

    lines = [f"{name}: RAA {score.risk_adjusted_alpha:.1f} "
             f"(Conf {score.confidence:.2f}, Insider {score.insider_probability:.0%})."]

    # why RAA dropped — the concrete downside factors
    factors = ar.get("downside_factors") or []
    if factors:
        gloss = []
        for f in factors:
            if f.startswith("okx_dev_reputation_"):
                level = f.rsplit("_", 1)[-1]
                gloss.append(f"reputasi dev {level} ({_DEV_REP_GLOSS.get(level, level)})")
            elif f == "insider_distribution":
                gloss.append("insider terdistribusi/jual saat publik beli")
            elif f == "exit_liquidity_high":
                gloss.append("risiko exit-liquidity tinggi")
            elif f.startswith("insider_hold_"):
                gloss.append(f"insider hold {f.rsplit('_', 1)[-1]}")
            elif f == "sybil_high":
                gloss.append("risiko sybil tinggi")
            else:
                gloss.append(f.replace("_", " "))
        if gloss:
            lines.append(f"  RAA terkoreksi karena: {'; '.join(gloss)}.")

    # dev reputation + contract status
    dev_rep = getattr(score, "dev_reputation_risk", None) or ins.get("dev_reputation_risk", "LOW")
    cstat = getattr(score, "contract_status", "UNKNOWN")
    if cstat:
        lines.append(f"  Contract: {_CONTRACT_GLOSS.get(cstat, cstat)}.")
    if dev_rep and dev_rep != "LOW":
        lines.append(f"  DevRisk {dev_rep}: {_DEV_REP_GLOSS.get(dev_rep, dev_rep)}.")

    # insider evidence
    ev = _insider_evidence_readable(ins.get("evidence"))
    if ev:
        lines.append("  Bukti insider: " + "; ".join(ev) + ".")

    # confluence label
    label = getattr(score, "confluence_label", "NEUTRAL")
    lines.append(f"  Konfluensi: {label} ({_CONFLUENCE_GLOSS.get(label, '')}).")

    return "\n".join(lines)


def explain_ranking(scores: list, *, symbols: dict | None = None) -> list[str]:
    """Explanations for an ordered list of TokenScore (ranking order)."""
    symbols = symbols or {}
    return [explain_token(s, symbol=symbols.get(getattr(s, "token", ""), "")) for s in scores]


# ---------------------------------------------------------------------------
# Optional LLM gloss (explains only; never changes the ranking)
# ---------------------------------------------------------------------------
class LLMExplainer:
    """Optional LLM layer that rephrases the rule-based explanation.

    No-op safe: if no LLM creds are configured, `explain_token` (deterministic)
    is returned unchanged. The ranking is NEVER altered here — this only words
    the explanation differently.
    """

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None) -> None:
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv("LLM_BASE_URL",
                                              "https://api.openai.com/v1")
        self.model = model or os.getenv("LLM_MODEL", "")
        self.enabled = bool(self.api_key and self.model)

    def _chat(self, prompt: str) -> str:
        import requests
        try:
            resp = requests.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model,
                      "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.2, "max_tokens": 600},
                timeout=30)
        except requests.RequestException:
            return ""  # fall back to rule-based explanation
        if resp.status_code != 200:
            return ""  # fall back to rule-based explanation
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError):
            return ""

    def gloss(self, rule_text: str) -> str:
        """Rephrase a rule-based explanation in natural language (optional)."""
        if not self.enabled:
            return rule_text
        prompt = ("Ringkas dalam 2-3 kalimat Bahasa Indonesia, netral, kenapa token "
                  "ini mendapat skor begini. JANGAN memberi saran beli/jual, hanya "
                  "jelaskan faktanya.\n\n" + rule_text)
        glossed = self._chat(prompt)
        return glossed or rule_text
