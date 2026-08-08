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
        """Build a readable ranking message from a board.snapshot()."""
        header = "🧿 SFC Meme Screening"
        if ts_label:
            header += f" — {ts_label}"
        header += "\n" + "=" * 32
        lines = [header]

        admitted = snapshot.get("admitted", 0)
        total = snapshot.get("count", universe_size)
        lines.append(f"Universe: {total} | Admitted: {admitted}")

        items = snapshot.get("ranking") or []
        if not items:
            lines.append("No admitted tokens this run.")
        for i, r in enumerate(items[:10], 1):
            lines.append(
                f"{i}. {r.get('token', '?')[:16]}\n"
                f"   RAA={r.get('risk_adjusted_alpha', 0):.1f} "
                f"conf={r.get('confidence', 0):.2f} "
                f"insider={r.get('insider_probability', 0):.2f} "
                f"({r.get('confluence_label', '?')})")
        lines.append("=" * 32)
        lines.append(f"generated {time.strftime('%Y-%m-%d %H:%M')} by SFC Memecoin bot")
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
