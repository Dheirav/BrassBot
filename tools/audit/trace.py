"""Instrument ordinary games: money at decision time, how many options money
gates, income trajectory, and how often negative income actually happens."""
from __future__ import annotations

import math
import pickle
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

from brassbot.bots import make
from brassbot.engine import apply_action, legal_actions
from brassbot.gamedata import Era
from brassbot.state import new_game

COUNTERFACTUAL_EVERY = 3  # decisions between +money option counts


def kinds(actions):
    return Counter(type(a).__name__ for a in actions)


def play(seed: int, n_players: int = 4, bot: str = "heuristic"):
    bots = [make(bot, seed=seed * 1000 + s) for s in range(n_players)]
    state = new_game(n_players, seed=seed)
    decisions = []       # per decision
    rounds = []          # per (era, round, seat) income snapshot
    neg_income_decisions = 0
    total_decisions = 0
    seen_round = set()
    moves = 0
    while not state.finished:
        actions = legal_actions(state)
        seat = state.current.idx
        p = state.players[seat]
        total_decisions += 1
        if p.income < 0:
            neg_income_decisions += 1
        key = (state.era.name, state.round)
        if key not in seen_round:
            seen_round.add(key)
            for q in state.players:
                rounds.append((state.era.name, state.round, q.idx, q.income,
                               q.money, q.vp))
        rec = {
            "era": state.era.name, "round": state.round, "seat": seat,
            "money": p.money, "income": p.income, "vp": p.vp,
            "n_actions": len(actions),
            "kinds": dict(kinds(actions)),
        }
        if total_decisions % COUNTERFACTUAL_EVERY == 0:
            for bonus in (10, 30):
                probe = state.clone()
                probe.players[seat].money += bonus
                more = legal_actions(probe)
                rec[f"n_plus{bonus}"] = len(more)
                rec[f"kinds_plus{bonus}"] = dict(kinds(more))
        decisions.append(rec)
        apply_action(state, bots[seat].choose(state, actions))
        moves += 1
        if moves > 5000:
            raise RuntimeError("runaway")
    final = [(q.idx, q.vp, q.income, q.money, q.vp_penalties)
             for q in state.players]
    return {"seed": seed, "decisions": decisions, "rounds": rounds,
            "final": final, "neg_income_decisions": neg_income_decisions,
            "total_decisions": total_decisions}


def _job(args):
    return play(*args)


if __name__ == "__main__":
    games = int(sys.argv[1])
    seed0 = int(sys.argv[2])
    out = sys.argv[3]
    workers = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    jobs = [(s, 4, "heuristic") for s in range(seed0, seed0 + games)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(_job, jobs, chunksize=2))
    with open(out, "wb") as f:
        pickle.dump(res, f)
    print("games", len(res))
