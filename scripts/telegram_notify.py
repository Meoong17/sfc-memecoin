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
import time

import requests

# Trigger the repo's .env loader (config.settings calls _load_env on import),
# so TELEGRAM_BOT_TOKEN/CHAT_ID from .env are in os.environ even when this
# script is run directly from a bare shell.
from config import settings as _settings  # noqa: F401  (side-effect: loads .env)

_BOT_URL = "https://api.telegram.org/bot{token}/sendMessage"


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
                       ts_label: str = "") -> str:
        """Build a readable ranking message with a clear legend/definitions.

        Plain text (no markdown markers) so it renders cleanly in Telegram's
        default parse mode — avoids bold/escape rendering pitfalls.
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
            tok = (r.get("token") or "?")[:14]
            raa = r.get("risk_adjusted_alpha", 0)
            conf = r.get("confidence", 0)
            ins = r.get("insider_probability", 0)
            conf_label = r.get("confluence_label", "NEUTRAL")
            lines.append(f"{i}. {tok}")
            lines.append(f"   • RAA={raa:.1f} | Conf={conf:.2f} | Insider={ins:.0%}")
            lines.append(f"   • Konfluensi: {conf_label}")
            lines.append("")

        lines.append(sep)
        lines.append("Cara baca skor:")
        lines.append("• RAA (Risk-Adjusted Alpha): potensi return dikurangi risiko "
                     "insider/sybil. Semakin tinggi, semakin menarik relatif terhadap risikonya.")
        lines.append("• Insider: probabilitas token terkait insider (0-100%). "
                     "Tinggi = risiko manipulasi harga tinggi.")
        lines.append("• Conf (Confidence): keyakinan model pada skor (0-1). "
                     "Tinggi = evidence lengkap & konsisten.")
        lines.append("• Konfluensi: kesepakatan antar-bukti independen — "
                     "MODERATE_OPPORTUNITY = peluang moderat.")
        lines.append("")
        lines.append("⚠️ Threshold belum terkalibrasi (ILLUSTRATIVE) — bukan rekomendasi investasi.")
        lines.append(f"⏱ {time.strftime('%Y-%m-%d %H:%M')} | @SfcMeme_bot")
        return "\n".join(lines)

    def send_ranking(self, snapshot: dict, *, universe_size: int = 0,
                     ts_label: str = "") -> bool:
        return self.send_text(self.format_ranking(snapshot, universe_size=universe_size,
                                                  ts_label=ts_label))


def main() -> int:
    """CLI: send a snapshot file to Telegram.

    Usage: .venv/bin/python scripts/telegram_notify.py <snapshot.json>
    """
    import json
    import sys
    from pathlib import Path

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
