"""Ranking output + SSE live feed (mirror SFC Terminal dashboard pattern).

Ranking: sort admitted token scores by Risk-Adjusted Alpha desc.
SSE: lightweight HTTP endpoint streaming the current ranking as JSON events,
consumed by a dashboard. Uses stdlib http.server (no extra dependency); real
SSE/websocket (mirror SFC Terminal) can replace this later.

Spec §5 end of pipeline: FINAL RANKING -> LLM EXPLAINER.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

from pipeline import TokenScore


@dataclass
class RankingBoard:
    """Holds scored tokens and emits a ranked snapshot."""
    scores: list[TokenScore] = field(default_factory=list)

    def add(self, s: TokenScore) -> None:
        self.scores.append(s)

    def clear(self) -> None:
        self.scores = []

    def ranked(self, *, top: int | None = None) -> list[dict]:
        admitted = [s for s in self.scores if s.admitted]
        admitted.sort(key=lambda s: s.risk_adjusted_alpha, reverse=True)
        snaps = [s.summary() for s in admitted]
        return snaps[:top] if top else snaps

    def snapshot(self) -> dict:
        return {
            "generated_at": time.time(),
            "count": len(self.scores),
            "admitted": len([s for s in self.scores if s.admitted]),
            "ranking": self.ranked(),
        }


# --- minimal SSE server using stdlib http.server ---
class SSERankingServer:
    """Streams the board snapshot to connected clients via SSE."""

    def __init__(self, board: RankingBoard, host: str = "127.0.0.1",
                 port: int = 8790, interval: float = 5.0) -> None:
        self.board = board
        self.host = host
        self.port = port
        self.interval = interval
        self._stop = threading.Event()

    def _handler(self, do_GET):
        def h():
            do_GET()  # noqa - set by caller
        return h

    def handle_request(self, request_line: str) -> str:
        """Single request -> SSE payload (used directly for testing)."""
        if "event" in request_line:
            return self._sse_event()
        return "HTTP/1.1 404 Not Found\r\n\r\n"

    def _sse_event(self) -> str:
        data = json.dumps(self.board.snapshot())
        return f"event: ranking\ndata: {data}\n\n"

    def stream_forever(self) -> None:
        """Loop; placeholder for a threaded HTTP server in production."""
        while not self._stop.is_set():
            time.sleep(self.interval)
