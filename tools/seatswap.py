"""Put the bot in a human's seat and see what it scores from the same deal.

The engine is deterministic from the seed, so the bot receives the human's
exact cards, seat and opponents (with the opponents' own seeds, so they are the
same bots that played the human). Where the bot's choices differ, the game
diverges and the opponents answer the new position, so this is an alternative
game from the same start, not a replay with substitutions.

    PYTHONPATH=. .venv/bin/python tools/seatswap.py logs/<game>.replay.json [n]

`n` extra runs vary only the seated bot's tie-break seed, to show how much of
its result is the deal and how much is the bot.

`review.py --against-bot` runs this too and puts the human's game beside it,
VP by source. That table is what makes the number useful: 170 against 139 says
the human won, while "cotton +27, breweries +29, links a wash" says where.
"""
from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import brassbot.engine as engine  # noqa: E402
from brassbot.actions import Build, Network, Sell  # noqa: E402
from brassbot.bots import make  # noqa: E402
from brassbot.engine import apply_action, legal_actions, link_icons_at  # noqa: E402
from brassbot.state import new_game  # noqa: E402

SERVE_KNOBS = {"MAX_DISCARD_VARIANTS": 8, "SCOUT_POOL": 8, "MAX_SCOUT_VARIANTS": 56}

# Row order of the source table; anything an industry scores lands on its own
# name, links and merchant bonuses on the two names that are not industries.
SOURCES = ["cotton_mill", "manufacturer", "pottery", "brewery",
           "coal_mine", "iron_works", "links", "bonus", "penalty"]


class Sources:
    """VP by where it came from, for every seat, in one game.

    Wraps `engine.score_era` for the life of the game, the same way
    attribution.py does: an era scoring on the game's own state is credited
    tile by tile to the owner and the industry, and link by link to the owner.
    Scorings on cloned probe states (the bot's search) are passed through
    untouched. A merchant bonus never goes through score_era, so it is the
    residual between the seat's VP and what was traced; a debt paid in VP at
    the end of a round is the engine's own `vp_penalties` counter, and it
    comes out of the residual first or a penalised seat reads as a negative
    bonus. `check` asserts the rows add up to the scoreboard for every seat.
    """

    def __init__(self, state, players: int):
        self.state = state
        self.vp = [collections.Counter() for _ in range(players)]
        self.counts = [collections.Counter() for _ in range(players)]
        self._real = engine.score_era

    def __enter__(self):
        engine.score_era = self._scoring
        return self

    def __exit__(self, *exc):
        engine.score_era = self._real

    def _scoring(self, s):
        if s is not self.state:
            return self._real(s)
        for link in s.data.links:
            owner = s.links.get(link.id)
            if owner is not None:
                self.vp[owner]["links"] += sum(link_icons_at(s, e) for e in link.ends)
        for _, _, tile in s.all_tiles():
            if tile.flipped:
                self.vp[tile.owner][tile.industry.value] += engine.spec_for(s, tile).vp
        return self._real(s)

    def step(self, seat: int, action) -> None:
        """Apply one action to the traced state and settle what it changed.

        Every seat is settled, not only the actor: the action that ends a
        round can cost another seat VP for a debt it could not pay.
        """
        if isinstance(action, Build):
            self.counts[seat][action.industry.value] += 1
        elif isinstance(action, Network):
            self.counts[seat]["links"] += len(action.lines)
        elif isinstance(action, Sell):
            self.counts[seat]["sells"] += 1
        apply_action(self.state, action)
        for i, p in enumerate(self.state.players):
            self.vp[i]["penalty"] = -p.vp_penalties
            gap = p.vp - sum(self.vp[i].values())
            self.vp[i]["bonus"] += gap

    def check(self) -> None:
        for i, p in enumerate(self.state.players):
            assert sum(self.vp[i].values()) == p.vp, (i, dict(self.vp[i]), p.vp)


def play(seed: int, players: int, opponent: str, seat_seed: int, seat: int):
    """The swapped game, returning its final state and the traced sources."""
    st = new_game(players, seed=seed)
    bots = [make(opponent, seed=seed * 10 + i) for i in range(players)]
    bots[seat] = make("heuristic", seed=seat_seed)
    with Sources(st, players) as src:
        while not st.finished:
            acts = legal_actions(st)
            if not acts:
                break
            who = st.current.idx
            src.step(who, bots[who].choose(st, acts))
    src.check()
    return st, src


def table(name: str, yours: Sources, seat: int, bot: Sources) -> str:
    """The human's game beside the bot's, VP by source, with what was built."""
    a, b = yours.vp[seat], bot.vp[seat]
    ca, cb = yours.counts[seat], bot.counts[seat]
    def cell(vp, n, src):
        return f"{vp} ({n})" if n else str(vp)

    lines = [f"  {'source':13} {name[:10]:>10} {'bot':>10} {'diff':>6}"]
    for src in SOURCES:
        lines.append(f"  {src.replace('_', ' '):13} {cell(a[src], ca[src], src):>10} "
                     f"{cell(b[src], cb[src], src):>10} {a[src] - b[src]:>+6}")
    ta, tb = sum(a.values()), sum(b.values())
    lines.append(f"  {'total':13} {ta:>10} {tb:>10} {ta - tb:>+6}")
    lines.append(f"  {'sells':13} {ca['sells']:>10} {cb['sells']:>10}")
    return "\n".join(lines)


def knobs(rep: dict) -> None:
    for k, v in rep.get("engine", SERVE_KNOBS).items():
        setattr(engine, k, v)


def main() -> None:
    rep = json.loads(Path(sys.argv[1]).read_text())
    extra = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    knobs(rep)
    seed, seat, n = rep["seed"], rep["seat"], rep["players"]
    opp = rep.get("opponent", "heuristic")
    t0 = time.time()
    runs = []
    for i in range(1 + extra):
        seat_seed = seed * 10 + seat if i == 0 else 90000 + i
        st, _ = play(seed, n, opp, seat_seed, seat)
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
