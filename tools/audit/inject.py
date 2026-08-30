"""Exogenous grant experiments: what is a pound / an income level actually paid?

Plays ordinary 4p heuristic games, but hands ONE seat a gift of money or income
at a chosen point in the game.  Everything else is identical, so the paired
difference in that seat's final VP is the outcome value of the gift.

Nothing in the repo is modified; this replicates evaluate.play_game.
"""
from __future__ import annotations

import statistics
import sys
from concurrent.futures import ProcessPoolExecutor

from brassbot.bots import make
from brassbot.engine import apply_action, legal_actions
from brassbot.gamedata import Era, highest_space_of_level
from brassbot.state import new_game


def _at(state, era_name: str, rnd: int) -> bool:
    era = Era.CANAL if era_name == "canal" else Era.RAIL
    return state.era is era and state.round >= rnd


def play(seed: int, seat: int, n_players: int, money: int, income: int,
         era: str, rnd: int, bot: str = "heuristic", vp: int = 0):
    bots = [make(bot, seed=seed * 1000 + s) for s in range(n_players)]
    state = new_game(n_players, seed=seed)
    granted = (money == 0 and income == 0 and vp == 0)
    moves = 0
    while not state.finished:
        if not granted and _at(state, era, rnd):
            p = state.players[seat]
            if money:
                p.money += money
            if income:
                p.income_space = highest_space_of_level(p.income + income)
            if vp:
                p.vp += vp
            granted = True
        actions = legal_actions(state)
        cur = state.current.idx
        apply_action(state, bots[cur].choose(state, actions))
        moves += 1
        if moves > 5000:
            raise RuntimeError("runaway")
    return (tuple(p.vp for p in state.players),
            tuple(p.income for p in state.players),
            tuple(p.money for p in state.players))


def _job(args):
    seed, seat, n, money, income, era, rnd, bot, vp = args
    return seed, seat, play(seed, seat, n, money, income, era, rnd, bot, vp)


def run(seeds, n_players=4, money=0, income=0, era="canal", rnd=1,
        workers=8, bot="heuristic", vp=0):
    jobs = [(s, s % n_players, n_players, money, income, era, rnd, bot, vp)
            for s in seeds]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        out = list(pool.map(_job, jobs, chunksize=2))
    return {(seed, seat): res for seed, seat, res in out}


def paired(a, b):
    """Mean of a[seat] - b[seat] over shared keys, with a paired stderr."""
    diffs = [a[k][0][k[1]] - b[k][0][k[1]] for k in a if k in b]
    m = statistics.fmean(diffs)
    se = statistics.stdev(diffs) / len(diffs) ** 0.5 if len(diffs) > 1 else 0.0
    return m, se, len(diffs)


def subject_mean(a):
    vals = [a[k][0][k[1]] for k in a]
    return statistics.fmean(vals), statistics.stdev(vals) / len(vals) ** 0.5


if __name__ == "__main__":
    import json
    cfg = json.loads(sys.argv[1])
    seeds = range(cfg["seed0"], cfg["seed0"] + cfg["games"])
    base = run(seeds, **{k: v for k, v in cfg.items()
                         if k in ("n_players", "workers", "bot")})
    print("baseline", subject_mean(base))
