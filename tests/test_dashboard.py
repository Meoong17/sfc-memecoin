"""Test RankingBoard + SSE server (Phase 5)."""
import json

from dashboard.sse_server import RankingBoard, SSERankingServer
from pipeline import TokenScore


def _score(token, raa, admitted=True, confidence=0.7, ip=0.2):
    return TokenScore(token=token, chain="solana", admitted=admitted,
                      risk_adjusted_alpha=raa, confidence=confidence,
                      insider_probability=ip, confluence_label="NEUTRAL",
                      regime="NORMAL")


def test_ranking_sorts_by_risk_adjusted_alpha_desc():
    board = RankingBoard()
    board.add(_score("A", 50.0))
    board.add(_score("B", 90.0))
    board.add(_score("C", 30.0))
    ranked = board.ranked()
    assert [r["token"] for r in ranked] == ["B", "A", "C"]
    assert ranked[0]["risk_adjusted_alpha"] == 90.0


def test_ranking_excludes_blocked():
    board = RankingBoard()
    board.add(_score("A", 90.0, admitted=False))
    board.add(_score("B", 80.0, admitted=True))
    ranked = board.ranked()
    assert [r["token"] for r in ranked] == ["B"]


def test_ranking_top_limit():
    board = RankingBoard()
    for t, raa in [("A", 90), ("B", 80), ("C", 70), ("D", 60)]:
        board.add(_score(t, float(raa)))
    assert len(board.ranked(top=2)) == 2


def test_snapshot_shape():
    board = RankingBoard()
    board.add(_score("A", 80.0))
    snap = board.snapshot()
    assert snap["count"] == 1
    assert snap["admitted"] == 1
    assert "ranking" in snap and "generated_at" in snap


def test_clear_empties_board():
    board = RankingBoard()
    board.add(_score("A", 80.0))
    board.clear()
    assert board.snapshot()["count"] == 0


def test_sse_event_emits_valid_json():
    board = RankingBoard()
    board.add(_score("A", 80.0))
    server = SSERankingServer(board)
    payload = server.handle_request("GET /stream?event=1")
    assert payload.startswith("event: ranking")
    data_line = [l for l in payload.split("\n") if l.startswith("data: ")][0]
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["count"] == 1
    assert parsed["ranking"][0]["token"] == "A"


def test_sse_404_for_unknown():
    board = RankingBoard()
    server = SSERankingServer(board)
    assert "404" in server.handle_request("GET /other")
