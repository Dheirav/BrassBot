"""A bot that plans a line, plays one action of it, and re-plans.

The perfect-information beam in `brassbot/planner.py` scores 143.7 at 4p against
the 1-ply bot's 115.2. This is the honest version of it, and the difference is
the whole question: it samples what it cannot see, looks a bounded distance
ahead instead of to the end of the game, and re-plans every turn as the board
moves under it.

What we are NOT blind to matters here, and keeps the sampling cheap. The deck
composition is fixed and known per player count, discards are face up, and hand
sizes are public -- so `determinize` redeals only the genuinely unseen pool
rather than guessing the whole game. The uncertainty is which unseen card sits
where, not what exists.
"""

from __future__ import annotations

from ..engine import apply_action
from ..planner import BeamPlanner
from .base import Bot
from ..state import determinize


class PlannerBot(Bot):
    name = "planner"

    DEFAULTS = {
        # How far ahead one plan reaches. Eight actions is four of our own turns
        # at 4p, which is enough to hold a whole build -> connect -> beer -> sell
        # chain in view -- the chain a one-ply evaluator cannot see the start of.
        "horizon": 8,
        "width": 12,
        "branch": 8,
        # Sampled worlds per decision. Each one costs a full search, so this is
        # the expensive dial; 1 means plan in a single guessed world.
        "worlds": 1,
        # Beam slots reserved per distinct first action. Zero: measured at
        # 115.4 VP against 132.2 for plain value pruning. See planner.py.
        "keep_per_root": 0,
        # Extra actions spent finishing a pending sale before a line is scored.
        "quiesce": 2,
        # Candidate first actions searched in separate beams.
        #
        # ON, purely for speed: play is identical and it runs 21% faster (24
        # games, same mean 137.7, same 96% win rate; and 0 of 31 own moves differ
        # on each of two full games). Each root beam starts from one plan and
        # grows, which expands fewer nodes than one beam that immediately has
        # branch x width children.
        #
        # It was built expecting a strength gain, on the theory that a shared
        # beam collapsing to one first action by ply 4 was cutting good lines.
        # It is not: given its own beam, each root reaches the same conclusion.
        # The collapse is convergence, not loss.
        "roots": 4,
        # 1.0 scores plans by projected VP, 0.0 by the hand-tuned evaluation.
        #
        # 0.0, and 1.0 was shipped for an hour by mistake. Measured over 24
        # games: 133.7 at 0.0, 131.7 at 0.5, and an agent's five games at 1.0
        # averaged 116. At 1.0 the heuristic is multiplied by zero, so the whole
        # objective is link icons plus tiles ALREADY flipped -- which means an
        # unflipped tile is worth nothing, a level-2 tile is worth exactly what a
        # level-1 is until it flips, a brewery is worth nothing until someone
        # drinks it, and a second sellable lined up for the same Sell scores 0.
        # Every one of those is a reason the bot stopped doing the thing.
        #
        # The projection is not wrong, it is incomplete: it needs a term for
        # tiles not yet flipped but still flippable, carrying the Canal-Era
        # double, before it can replace the evaluation rather than blind it.
        "vp_blend": 0.0,
    }

    def __init__(self, seed: int = 0, **params):
        super().__init__(seed)
        unknown = set(params) - set(self.DEFAULTS)
        if unknown:
            raise KeyError(f"unknown params: {sorted(unknown)}")
        self.p = {**self.DEFAULTS, **params}

    def choose(self, state, actions):
        if len(actions) == 1:
            return actions[0]
        me = state.current.idx
        planner = BeamPlanner(seat=me, width=int(self.p["width"]),
                              branch=int(self.p["branch"]),
                              keep_per_root=int(self.p["keep_per_root"]),
                              quiesce=int(self.p["quiesce"]),
                              vp_blend=float(self.p["vp_blend"]),
                              roots=int(self.p["roots"]))

        # Each sampled world votes for the first action of its best line, scored
        # by what that line reaches. Summing scores rather than counting votes
        # keeps a single strong line from being outvoted by several weak ones.
        tally: dict = {}
        for i in range(int(self.p["worlds"])):
            world = determinize(state, me, self.rng)
            plan = planner.search(world, horizon=int(self.p["horizon"]))
            if not plan or not plan.actions:
                continue
            first = plan.actions[0]
            key = repr(first)
            score, _ = tally.get(key, (0.0, None))
            tally[key] = (score + planner._potential(plan), first)
        if not tally:
            return actions[0]

        best_key = max(tally, key=lambda k: tally[k][0])
        chosen = tally[best_key][1]
        # The plan was made in a sampled world, so the chosen action must be
        # matched back to a real legal one -- card indices refer to a hand that
        # only existed in that world.
        for action in actions:
            if repr(action) == best_key:
                return action
        for action in actions:
            if type(action) is type(chosen):
                return action
        return actions[0]
