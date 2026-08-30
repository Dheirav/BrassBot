"""Causal pricing of one action.

At one randomly chosen decision of seat 0 we override the bot's choice: either
with a Pass (spend the action on nothing) or with the best action of a named
type. Everything else -- the same seed, the same three baseline opponents, the
same bot -- is identical, and the game is deterministic, so the difference in
seat 0's final score is caused by the override.

This prices a *marginal* action: what the bot gives up by committing one of its
31 to type T instead of to whatever it wanted.
"""
from __future__ import annotations

import pickle
import random
from concurrent.futures import ProcessPoolExecutor

from brassbot.actions import Build, Develop, Loan, Network, Pass, Scout, Sell
from brassbot.bots.heuristic import HeuristicBot
from brassbot.engine import apply_action, legal_actions
from brassbot.network import connected_locations
from brassbot.state import new_game

TYPES = {"Build": Build, "Network": Network, "Sell": Sell, "Develop": Develop,
         "Loan": Loan, "Scout": Scout, "Pass": Pass}


class ProbeBot(HeuristicBot):
    """Heuristic bot that can report the value it gives every candidate, and be
    forced onto a chosen type at a chosen decision index."""

    def __init__(self, seed=0, force_at=None, force_type=None, **w):
        super().__init__(seed, **w)
        self.force_at = force_at          # set of decision indices
        self.force_type = force_type      # type name, or None for Pass
        self.n_decisions = 0
        self.log = []                     # (index, era, values...)

    def ranked(self, state, actions):
        """(action, value) for every candidate, in generation order.

        A copy of HeuristicBot.choose's loop; `test_matches_parent` below pins
        that its argmax is the parent's move.
        """
        self.w = self.weights_for(state.n_players)
        actions = self._committed(state, actions)
        me = state.current.idx
        base_links = set(state.links)
        base_reachable = connected_locations(state, list(state.merchants))
        base_owned, _sig = self.scan_board(state)
        base_context = self._sale_context(state, base_reachable)
        base_rivals = [self.player_value(state, i, base_context, base_owned[i])
                       for i in range(state.n_players) if i != me]
        shared = (self.shared_signature(state, me, base_owned),
                  max(base_rivals) if base_rivals else 0.0)
        out = []
        for action in actions:
            probe = state.clone()
            apply_action(probe, action)
            reachable = base_reachable if set(probe.links) == base_links else None
            value = self.position_value(probe, me, reachable, shared)
            if isinstance(action, Pass):
                value += self.w["pass_bias"]
            out.append((action, value))
        return out

    def choose(self, state, actions):
        i = self.n_decisions
        self.n_decisions += 1
        if self.force_at is None or i not in self.force_at:
            return super().choose(state, actions)

        ranked = self.ranked(state, actions)
        best_a, best_v = max(ranked, key=lambda t: t[1])
        if self.force_type in ("SECOND", "WORST", "RANDOM"):
            order = sorted(ranked, key=lambda t: -t[1])
            if self.force_type == "SECOND":
                f_a, f_v = order[1] if len(order) > 1 else order[0]
            elif self.force_type == "WORST":
                f_a, f_v = order[-1]
            else:
                f_a, f_v = self.rng.choice(ranked)
            self.log.append({"i": i, "era": state.era.value, "available": True,
                             "best_type": type(best_a).__name__,
                             "best_v": best_v, "forced_v": f_v,
                             "deficit": best_v - f_v,
                             "n_cands": len(ranked), "n_pool": len(ranked)})
            return f_a
        cls = TYPES[self.force_type] if self.force_type else Pass
        pool = [(a, v) for a, v in ranked if isinstance(a, cls)]
        if not pool:
            self.log.append({"i": i, "era": state.era.value, "available": False,
                             "best_type": type(best_a).__name__})
            return best_a
        f_a, f_v = max(pool, key=lambda t: t[1])
        self.log.append({"i": i, "era": state.era.value, "available": True,
                         "best_type": type(best_a).__name__,
                         "best_v": best_v, "forced_v": f_v,
                         "deficit": best_v - f_v,
                         "n_cands": len(ranked), "n_pool": len(pool)})
        return f_a


def play(seed, n_players, force_at, force_type):
    bots = [ProbeBot(seed=seed * 1000 + s) for s in range(n_players)]
    bots[0].force_at = force_at
    bots[0].force_type = force_type
    state = new_game(n_players, seed=seed)
    while not state.finished:
        acts = legal_actions(state)
        seat = state.current.idx
        apply_action(state, bots[seat].choose(state, acts))
    return {"vp": [p.vp for p in state.players], "log": bots[0].log}


def _job(args):
    seed, n_players, force_at, force_type = args
    return (seed, force_type, tuple(sorted(force_at)) if force_at else None,
            play(seed, n_players, force_at, force_type))


def main(games, seed0, n_players, workers, out, arms):
    rng = random.Random(12345)
    picks = {}
    for g in range(games):
        seed = seed0 + g
        total = 31 if n_players == 4 else (35 if n_players == 3 else 39)
        picks[seed] = rng.randrange(0, total)
    jobs = []
    for g in range(games):
        seed = seed0 + g
        d = picks[seed]
        for arm in arms:
            if arm == "control":
                jobs.append((seed, n_players, None, None))
            elif arm in ("second", "worst", "random"):
                jobs.append((seed, n_players, {d}, arm.upper()))
            elif arm.startswith("pass"):
                k = int(arm[4:]) if len(arm) > 4 else 1
                idxs = {min(d + j, 30) for j in range(k)}
                jobs.append((seed, n_players, idxs, "Pass"))
            else:
                jobs.append((seed, n_players, {d}, arm))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(_job, jobs, chunksize=4))
    pickle.dump({"picks": picks, "res": res, "arms": arms}, open(out, "wb"))
    print(f"{len(res)} games -> {out}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("-s", type=int, default=0)
    ap.add_argument("-p", type=int, default=4)
    ap.add_argument("-w", type=int, default=8)
    ap.add_argument("-o", default="forced.pkl")
    ap.add_argument("--arms", default="control,pass1,Build,Network,Sell,Develop,Loan,Scout")
    a = ap.parse_args()
    main(a.n, a.s, a.p, a.w, a.o, a.arms.split(","))
