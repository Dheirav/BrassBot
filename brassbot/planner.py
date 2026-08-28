"""A planner that optimises a whole line of play, not one action at a time.

The diagnosis this exists to attack: 65% of the variance between seats in a 4p
mirror is *play*, not the deal. Identical bots on the identical board finish 28 VP
apart on average, because every decision is local -- whether the bot stumbles into
a coherent line depends on where the one-ply gradient happens to point.

So this searches over *sequences*: beam search to the end of the game, keeping the
best few partial plans at each step and scoring them by what they finish on. That
makes the action budget, the mat order, resource availability and link adjacency
all constraints on one optimisation rather than terms in a per-move score.

Beam search rather than an integer program because the constraints are not linear
and barely static -- market prices move as you spend, a link changes what is
reachable, and flipping a tile changes what every later link scores. Enumerating
real successors respects all of that by construction; an ILP would need each rule
restated as an approximation, and the approximations are where the bugs live.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .bots.heuristic import HeuristicBot
from .engine import apply_action, legal_actions


@dataclass
class Plan:
    """One line of play under construction."""
    state: object
    actions: list = field(default_factory=list)

    @property
    def score(self) -> int:
        return self.state.players[self.seat].vp

    seat: int = 0


class BeamPlanner:
    """Search sequences of actions for one seat.

    ``width`` plans are carried forward at each step; ``branch`` candidate moves
    are tried from each. Both cost time linearly, and the product is what buys
    quality.
    """

    def __init__(self, seat: int, width: int = 24, branch: int = 12,
                 evaluator: HeuristicBot | None = None):
        self.seat = seat
        self.width = width
        self.branch = branch
        self.ev = evaluator or HeuristicBot()
        # Opponents reply with the ordinary bot while we search our own line.
        self.opponent = HeuristicBot()

    def _rank(self, state, actions):
        """Order candidates by the one-ply evaluation, best first.

        The beam still needs a way to decide which moves are worth expanding --
        the evaluation is a bad *policy* but a serviceable *filter*, which is the
        same division of labour the MCTS prior uses.
        """
        self.ev.w = self.ev.weights_for(state.n_players)
        scored = []
        for action in actions:
            probe = state.clone()
            apply_action(probe, action)
            scored.append((self.ev.position_value(probe, self.seat), action, probe))
        scored.sort(key=lambda t: -t[0])
        return scored[:self.branch]

    def _advance_opponents(self, state) -> None:
        """Play opponents forward until it is our turn again, or the game ends.

        Done once per surviving plan rather than once per candidate. Advancing
        every child instead costs the beam width times the branching factor in
        opponent turns per level, which is where a first attempt at this spent
        all its time.
        """
        while not state.finished and state.current.idx != self.seat:
            actions = legal_actions(state)
            if not actions:
                break
            apply_action(state, self.opponent.choose(state, actions))

    def search(self, state, horizon: int | None = None) -> list:
        """Return the best action sequence found for this seat.

        Opponents reply with the ordinary heuristic between our actions, so this
        is not a solitaire fantasy -- it is what our seat could have scored
        against the bots it actually faced.
        """
        root = state.clone()
        self._advance_opponents(root)
        beam = [Plan(state=root, seat=self.seat)]
        steps = 0

        while beam and not all(p.state.finished for p in beam):
            if horizon is not None and steps >= horizon:
                break
            children: list[Plan] = []
            for plan in beam:
                if plan.state.finished:
                    children.append(plan)
                    continue
                actions = legal_actions(plan.state)
                if not actions:
                    continue
                for _value, action, probe in self._rank(plan.state, actions):
                    children.append(Plan(state=probe,
                                         actions=plan.actions + [action],
                                         seat=self.seat))
            if not children:
                break
            # Prune first, then let the opponents move: the survivors are the
            # only states whose futures we still care about.
            children.sort(key=lambda p: -self._potential(p))
            beam = children[:self.width]
            for plan in beam:
                self._advance_opponents(plan.state)
            steps += 1

        beam.sort(key=lambda p: -p.score)
        return beam[0] if beam else None

    def best_actions(self, state, horizon: int | None = None) -> list:
        """Just the action sequence.

        Note it cannot be replayed onto a fresh state: a card index means a
        position in a hand that opponents' turns have since changed. Only the
        first action is safe to use, which is exactly how a re-planning bot
        should use it.
        """
        plan = self.search(state, horizon)
        return plan.actions if plan else []

    def _potential(self, plan) -> float:
        """Rank partial plans. Final VP once the game is over, and the
        evaluation's estimate while it is still running."""
        if plan.state.finished:
            return float(plan.score)
        self.ev.w = self.ev.weights_for(plan.state.n_players)
        return self.ev.position_value(plan.state, self.seat)
