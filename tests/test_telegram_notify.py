"""Test Telegram notifier (scripts/telegram_notify.py) — mocked network."""
import pytest

from scripts.telegram_notify import TelegramNotifier


def test_disabled_when_no_token(monkeypatch):
    # clear env so the .env loader has nothing to fall back to
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    n = TelegramNotifier(token="", chat_id="")
    assert n.enabled is False
    # sending while disabled is a safe no-op returning True
    assert n.send_text("hi") is True


def test_send_text_ok(monkeypatch):
    n = TelegramNotifier(token="t", chat_id="c")

    class _Resp:
        status_code = 200
        def json(self):
            return {"ok": True}

    def _post(url, data, timeout=20):
        assert url == "https://api.telegram.org/bott/sendMessage"
        assert data["chat_id"] == "c"
        assert data["text"] == "hello"
        return _Resp()

    import requests
    monkeypatch.setattr(requests, "post", _post)
    assert n.send_text("hello") is True


def test_send_text_api_failure(monkeypatch):
    n = TelegramNotifier(token="t", chat_id="c")

    class _Resp:
        status_code = 400
        text = '{"ok": false}'
        def json(self):
            return {"ok": False, "description": "bad request"}

    import requests
    monkeypatch.setattr(requests, "post", lambda *a, **k: _Resp())
    assert n.send_text("x") is False


def test_format_ranking():
    n = TelegramNotifier(token="t", chat_id="c")
    snap = {
        "count": 5, "admitted": 3,
        "ranking": [
            {"token": "TOKENADDR123456789", "risk_adjusted_alpha": 61.6,
             "confidence": 0.39, "insider_probability": 0.2,
             "confluence_label": "MODERATE_OPPORTUNITY"},
        ],
    }
    msg = n.format_ranking(snap, universe_size=5, ts_label="test")
    assert "SFC Meme Screening" in msg
    assert "TOKENADDR12" in msg  # truncated to 16
    assert "RAA=61.6" in msg
    assert "insider=0.20" in msg
    assert "Universe: 5 | Admitted: 3" in msg


def test_format_ranking_empty():
    n = TelegramNotifier(token="t", chat_id="c")
    msg = n.format_ranking({"count": 0, "admitted": 0, "ranking": []})
    assert "No admitted tokens" in msg
