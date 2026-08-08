#!/usr/bin/env python3
"""Telegram notifier for the SFC Memecoin screener.

Pushes the live screening ranking to a Telegram channel/DM via the Bot API.
Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from .env (or env). Uses `requests`
(already a repo dependency). Sends plain-text (no markdown parsing) to avoid
rendering/escaping pitfalls.

Usage (module):
    from scripts.telegram_notify import TelegramNotifier
    notif = TelegramNotifier()
    notif.send_ranking(snapshot, universe_size=N)
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests

# Allow running directly: add repo root to sys.path so `config` resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Trigger the repo's .env loader (config.settings calls _load_env on import),
# so TELEGRAM_BOT_TOKEN/CHAT_ID from .env are in os.environ even when this
# script is run directly from a bare shell.
from config import settings as _settings  # noqa: F401  (side-effect: loads .env)

_BOT_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _fmt_usd(v) -> str:
    """Compact USD formatting for memo-coin prices and caps.

    Prices are often sub-cent (0.00000012) -> show enough significant digits;
    caps can be millions/billions -> M/B suffix. Missing/zero -> '—'.
    """
    if v is None:
        return "—"
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if x <= 0:
        return "0"
    if x >= 1e12:
        return f"${x/1e12:.2f}T"
    if x >= 1e9:
        return f"${x/1e9:.2f}B"
    if x >= 1e6:
        return f"${x/1e6:.2f}M"
    if x >= 1:
        if x >= 1000:
            return f"${x:,.0f}"
        return f"${x:,.4f}"
    if x >= 1e-4:
        return f"${x:.6f}"
    return f"${x:.8f}"


_CONTRACT_EMOJI = {
    "VERIFIED": "🛡️ VERIFIED",
    "LOCKED": "🔒 LOCKED",
    "RISKY": "⚠️ RISKY",
    "CRITICAL": "🚨 CRITICAL",
    "UNKNOWN": "❔ UNKNOWN",
}


def _contract_badge(status: str) -> str:
    """Emoji + label for contract status, so the secure coin is obvious."""
    return _CONTRACT_EMOJI.get(status, f"❔ {status}")


class TelegramNotifier:
    """Sends screener results to a Telegram chat. No-op-safe when unconfigured."""

    def __init__(self, token: str | None = None, chat_id: str | None = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self.enabled = bool(self.token and self.chat_id)

    def send_text(self, text: str, *, timeout: float = 20) -> bool:
        """Send a plain-text message. Returns True on success (or when disabled)."""
        if not self.enabled:
            print("[telegram] disabled (token/chat missing); message not sent.")
            return True
        try:
            r = requests.post(
                _BOT_URL.format(token=self.token),
                data={"chat_id": self.chat_id, "text": text}, timeout=timeout)
            ok = r.json().get("ok", False) if r.status_code == 200 else False
            if not ok:
                print(f"[telegram] send failed: HTTP {r.status_code} {r.text[:200]}")
            return ok
        except requests.RequestException as e:
            print(f"[telegram] send error: {e}")
            return False

    def format_ranking(self, snapshot: dict, *, universe_size: int = 0,
                       ts_label: str = "", explanations: dict | None = None) -> str:
        """Build a readable ranking message with a clear legend/definitions.

        Plain text (no markdown markers) so it renders cleanly in Telegram's
        default parse mode — avoids bold/escape rendering pitfalls.

        `explanations`: optional {token_addr: natural-language explanation}
        from the LLM Explainer. Shown as a compact "why" section for the top
        tokens. The LLM explains only; it never changes the ranking here.
        """
        sep = "──────────────────────────────"
        lines = []
        lines.append("🧿 SFC MEME SCREENER" + (f" — {ts_label}" if ts_label else ""))
        lines.append(sep)

        admitted = snapshot.get("admitted", 0)
        total = snapshot.get("count", universe_size)
        lines.append(f"📊 Universe: {total} token | ✅ Admitted: {admitted} | "
                     f"🚫 Blocked: {total - admitted}")
        lines.append("")

        items = snapshot.get("ranking") or []
        if not items:
            lines.append("⚠️ Tidak ada token yang lolos filter (semua diblok / gagal).")
        for i, r in enumerate(items[:10], 1):
            symbol = (r.get("symbol") or r.get("token") or "?")[:14]
            tok = (r.get("token") or "?")
            raa = r.get("risk_adjusted_alpha", 0)
            conf = r.get("confidence", 0)
            ins = r.get("insider_probability", 0)
            conf_label = r.get("confluence_label", "NEUTRAL")
            price = r.get("price_usd", 0)
            mcap = r.get("mcap")
            dev_rep = r.get("dev_reputation_risk", "LOW")
            cstat = r.get("contract_status", "UNKNOWN")
            alpha = r.get("alpha", 0)
            organic = r.get("organic", 0)
            safety = r.get("safety", 0)
            smart = r.get("smart_money", 0)
            lines.append(f"{i}. {symbol}")
            lines.append(f"   💰 {_fmt_usd(price)} | Cap {_fmt_usd(mcap)}")
            lines.append(f"   🎯 RAA={raa:.1f} | Alpha={alpha:.0f} | Organic={organic:.0f} "
                         f"| Safety={safety:.0f} | Smart={smart:.0f}")
            lines.append(f"   🧠 Insider={ins:.0%} | Conf={conf:.2f} | DevRisk={dev_rep} | "
                         f"{conf_label}")
            lines.append(f"   {_contract_badge(cstat)} | 🔗 {tok}")
            lines.append("")

        # LLM Explainer "why" section for the top tokens (explain-only).
        if explanations:
            glossed = []
            for r in items[:3]:
                txt = explanations.get(r.get("token") or "")
                if txt:
                    sym = (r.get("symbol") or r.get("token") or "?")[:14]
                    glossed.append(f"{sym}: {txt.strip()}")
            if glossed:
                lines.append(sep)
                lines.append("🧠 Kenapa token teratas ini? (penjelasan, bukan "
                             "rekomendasi beli/jual)")
                lines.extend(f"• {g}" for g in glossed)
                lines.append("")

        lines.append(sep)
        lines.append(f"⏱ {time.strftime('%Y-%m-%d %H:%M')} | @SfcMeme_bot")
        return "\n".join(lines)

    def send_ranking(self, snapshot: dict, *, universe_size: int = 0,
                     ts_label: str = "", explanations: dict | None = None) -> bool:
        return self.send_text(self.format_ranking(snapshot, universe_size=universe_size,
                                                  ts_label=ts_label,
                                                  explanations=explanations))


def main() -> int:
    """CLI: send a snapshot file to Telegram.

    Usage: .venv/bin/python scripts/telegram_notify.py <snapshot.json>
    """
    import json

    if len(sys.argv) < 2:
        print("Usage: telegram_notify.py <snapshot.json>")
        return 2
    snap = json.loads(Path(sys.argv[1]).read_text())
    notif = TelegramNotifier()
    ok = notif.send_ranking(snap, universe_size=snap.get("count", 0))
    print(f"[telegram] sent={ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
