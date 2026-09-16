"""The VP-by-source trace behind `review.py --against-bot`.

The one thing that can go quietly wrong here is the bookkeeping: a source the
trace forgets (merchant bonuses, the first time) makes the table not add up to
the scoreboard, and a table that does not add up is worse than none because it
looks like an answer. So the trace asserts its own total, and this pins that
the assertion holds on a whole game and that the table reads back the same
numbers the trace holds.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import brassbot.engine as engine  # noqa: E402
from brassbot.bots import make  # noqa: E402
from brassbot.engine import legal_actions  # noqa: E402
from brassbot.state import new_game  # noqa: E402
from seatswap import SOURCES, Sources, play, table  # noqa: E402


def test_the_trace_adds_up_to_the_scoreboard_and_restores_the_engine():
    real = engine.score_era
    st, src = play(seed=11, players=2, opponent="random", seat_seed=5, seat=1)
    assert st.finished
    assert engine.score_era is real
    for i, p in enumerate(st.players):
        assert sum(src.vp[i].values()) == p.vp
    # Every credited source has a row in the table, so nothing is scored
    # into a name the reader never sees.
    for c in src.vp:
        assert set(c) <= set(SOURCES)


def test_the_table_is_the_trace():
    st, a = play(seed=11, players=2, opponent="random", seat_seed=5, seat=0)
    _, b = play(seed=11, players=2, opponent="random", seat_seed=6, seat=0)
    out = table("Test", a, 0, b)
    rows = {ln.split()[0]: ln for ln in out.splitlines()[1:]}
    total = rows["total"].split()
    assert int(total[1]) == st.players[0].vp == sum(a.vp[0].values())
    assert int(total[2]) == sum(b.vp[0].values())
    assert int(total[3]) == sum(a.vp[0].values()) - sum(b.vp[0].values())


def test_a_probe_scoring_is_not_credited():
    """The bot's search scores cloned states; only the game's own count."""
    st = new_game(2, seed=3)
    bot = make("heuristic", seed=0)
    with Sources(st, 2) as src:
        acts = legal_actions(st)
        bot.choose(st, acts)          # searches, scoring probes along the way
    assert all(not c for c in src.vp)
