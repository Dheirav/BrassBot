"""Put the bot in a human's seat and see what it scores from the same deal.

The engine is deterministic from the seed, so the bot receives the human's
exact cards, seat and opponents (with the opponents' own seeds, so they are the
same bots that played the human). Where the bot's choices differ, the game
diverges and the opponents answer the new position, so this is an alternative
game from the same start, not a replay with substitutions.

    PYTHONPATH=. .venv/bin/python tools/seatswap.py logs/<game>.replay.json [n]

`n` extra runs vary only the seated bot's tie-break seed, to show how much of
its result is the deal and how much is the bot.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import brassbot.engine as engine  # noqa: E402
from brassbot.bots import make  # noqa: E402
from brassbot.engine import apply_action, legal_actions  # noqa: E402
from brassbot.state import new_game  # noqa: E402

SERVE_KNOBS = {"MAX_DISCARD_VARIANTS": 8, "SCOUT_POOL": 8, "MAX_SCOUT_VARIANTS": 56}


def play(seed: int, players: int, opponent: str, seat_seed: int, seat: int):
    st = new_game(players, seed=seed)
    bots = [make(opponent, seed=seed * 10 + i) for i in range(players)]
    bots[seat] = make("heuristic", seed=seat_seed)
    while not st.finished:
        acts = legal_actions(st)
        if not acts:
            break
        apply_action(st, bots[st.current.idx].choose(st, acts))
    return st


def main() -> None:
    rep = json.loads(Path(sys.argv[1]).read_text())
    extra = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    for k, v in rep.get("engine", SERVE_KNOBS).items():
        setattr(engine, k, v)
    seed, seat, n = rep["seed"], rep["seat"], rep["players"]
    opp = rep.get("opponent", "heuristic")
    t0 = time.time()
    runs = []
    for i in range(1 + extra):
        seat_seed = seed * 10 + seat if i == 0 else 90000 + i
        st = play(seed, n, opp, seat_seed, seat)
        runs.append([p.vp for p in st.players])
        print(f"PROGRESS done={i + 1} total={1 + extra} unit=games t={time.time() - t0:.1f}",
              flush=True)
    print()
    print(f"{rep.get('name', 'you')} scored {rep.get('final', '?')} in the real game "
          f"(see the log). The bot from the same seat:")
    for i, vp in enumerate(runs):
        mine = vp[seat]
        rank = 1 + sum(1 for j, v in enumerate(vp) if j != seat and v > mine)
        print(f"  run {i}: {vp}  seat {seat} = {mine}, finished #{rank}"
              + ("   (the server's own seed for this seat)" if i == 0 else ""))
    print("total", 1 + extra, "runs")


if __name__ == "__main__":
    main()
