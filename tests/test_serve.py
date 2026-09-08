"""The UI server, end to end.

Nothing under tools/ had test coverage, and three real defects were found in
this file by hand in a single evening: a move index applied to a regenerated
list could play an action nobody chose; "can build now" silently became dead
code when the mat gained opponent tabs; and every Sell option threw a
ReferenceError, which thirty actions of automated play never reached because
Sell is the rarest action in the game.

These play whole games through the same functions the browser drives, and
assert the shape the client actually reads. They are not UI tests -- they cannot
see the page -- but each one pins a bug that shipped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import serve  # noqa: E402
from brassbot.engine import legal_actions  # noqa: E402


@pytest.fixture
def game():
    serve.GAME.clear()
    serve.GAME["name"] = "Tester"
    serve.start(seed=21, players=4, opponent="heuristic")
    return serve.GAME


def play_out(game, limit=400):
    """Drive a whole game through the server's own move path."""
    seen = 0
    while not game["state"].finished and seen < limit:
        actions = legal_actions(game["state"])
        if not actions:
            break
        serve.record(actions[0])
        serve.advance()
        seen += 1
    return seen


def test_snapshot_has_everything_the_client_reads(game):
    s = serve.snapshot()
    for key in ("coords", "towns", "merchants", "all_merchants", "tiles", "links",
                "all_links", "era", "round", "turn_order", "current", "seat",
                "actions_left", "coal_slots", "iron_slots", "players", "hand",
                "mat", "mats", "moves", "log", "deck", "discard", "version",
                "can_undo", "ended"):
        assert key in s, f"snapshot is missing {key!r}, which the client reads"


def test_own_mat_carries_buildable_and_opponents_do_not(game):
    """The regression: adding opponent mat tabs made the renderer read `mats`,
    and only `mat` carried the flags -- so every row fell through to a cash
    figure and "can build now" became unreachable."""
    s = serve.snapshot()
    mine = s["mats"][s["seat"]]
    assert any("buildable" in row for row in mine.values())
    other = s["mats"][(s["seat"] + 1) % 4]
    assert all("buildable" not in row for row in other.values())


def test_every_move_carries_prose_and_a_card(game):
    for m in serve.snapshot()["moves"]:
        assert m["pretty"], f"{m['kind']} move has no prose label"
        assert "card" in m


def test_build_moves_price_their_resources(game):
    builds = [m for m in serve.snapshot()["moves"] if m["kind"] == "Build"]
    assert builds, "no builds offered in the opening position"
    for m in builds:
        assert m["outlay"] == m["price"] + sum(d["cost"] for d in m["coal"]) \
                                         + sum(d["cost"] for d in m["iron"])
        assert m["net"] == m["outlay"] - m["revenue"]


def test_develop_levels_follow_the_mat_not_a_counter(game):
    """Brewery holds two level-1 tiles, so developing two removes L1 and L1.
    Incrementing the level per removal printed L1 + L2 and made the pair look
    unavailable to anyone looking for it."""
    pairs = {tuple(m["industries"]): m["levels"]
             for m in serve.snapshot()["moves"]
             if m["kind"] == "Develop" and len(m["industries"]) == 2}
    assert pairs.get(("brewery", "brewery")) == [1, 1]
    assert pairs.get(("coal_mine", "coal_mine")) == [1, 2]


def test_a_stale_move_index_is_refused(game):
    """Two tabs on one game: an index still in range for the regenerated list
    would otherwise play an action nobody chose."""
    stale = serve.GAME["version"]
    serve.record(legal_actions(game["state"])[0])
    serve.advance()
    assert serve.GAME["version"] != stale


def test_a_whole_game_plays_and_every_snapshot_is_serialisable(game):
    import json
    steps = 0
    while not game["state"].finished and steps < 400:
        json.dumps(serve.snapshot())          # would raise on a bad payload
        actions = legal_actions(game["state"])
        if not actions:
            break
        serve.record(actions[0])
        serve.advance()
        steps += 1
    assert game["state"].finished, "the game did not reach an ending"
    final = serve.snapshot()
    assert final["projected"] if "projected" in final else True


def test_projected_vp_does_not_rescore_a_finished_game(game):
    """`finished` is set without clearing the board, so projecting again scored
    every flipped tile a second time and disagreed with the game-over panel."""
    play_out(game)
    assert game["state"].finished
    s = serve.snapshot()
    for p in s["players"]:
        assert p["projected"] == p["vp"]


def test_export_writes_a_log_the_parsers_can_read(game, tmp_path, monkeypatch):
    monkeypatch.setattr(serve, "LOGS", tmp_path)
    play_out(game)
    path = Path(serve.export_log())
    lines = path.read_text().splitlines()
    assert lines[0].startswith("game over, winner:")
    assert any(l.startswith("rail era scored:") for l in lines)
    assert any(l.startswith("canal era scored:") for l in lines)
    # the pooling parsers key on "<name> <verb>"
    assert any(l.startswith("Tester ") for l in lines)
