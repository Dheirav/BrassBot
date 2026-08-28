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
from .actions import Sell
from .engine import apply_action, legal_actions, legal_sells
from .network import connected_locations


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
                 evaluator: HeuristicBot | None = None,
                 cheap_opponents: bool = False, keep_per_root: int = 0,
                 quiesce: int = 2):
        self.seat = seat
        self.width = width
        self.branch = branch
        self.ev = evaluator or HeuristicBot()
        # Opponents reply while we search our own line, and profiling put 56%
        # of runtime in 645 opponent decisions a game.
        #
        # The obvious inference -- make the opponent model cheaper -- was tried
        # and is OFF by default because it does not pay. Ranking opponent replies
        # by the acting seat's value alone saved 10% of the time (286s -> 256s)
        # and cost 3.3 VP and eight points of win rate (132.2/79% -> 128.9/71%).
        # The profile was read wrong: the cost inside an opponent decision is the
        # clone and apply per candidate, not the four-seat evaluation, so cutting
        # three quarters of the evaluation cut a small slice of the total.
        #
        # Anything faster here has to remove clones, not arithmetic.
        self.opponent = HeuristicBot()
        self.cheap_opponents = cheap_opponents
        # Slots reserved per distinct FIRST action. OFF, because it was tried
        # and it is badly wrong: 115.4 VP at a 46% win rate against 132.2 at 79%
        # for plain value pruning, over the same 24 seeds.
        #
        # The idea was that the beam kills a first action at level two or three
        # because its early steps score worse, even when the payoff lands inside
        # the horizon -- the shape a tempo play has. The measurement says the
        # cost of the cure exceeds the disease: reserving a slot for each of
        # ~12 distinct first actions leaves a width-12 beam one plan deep per
        # line. That is not a fairer search, it is a shallower one, and this
        # beam needs its depth more than its breadth.
        #
        # It also means the pruning function is NOT why the planner fails to
        # find turn-order management. That explanation is unsupported.
        self.keep_per_root = keep_per_root
        # Quiescence, borrowed from chess: never score a position in the middle
        # of a transaction. Measured at +1.1 VP (132.8 -> 133.9 over 24 report
        # seeds, win rate 83% either way), which is 0.3 sigma and therefore NOT
        # a demonstrated gain. Kept at 2 because the point estimate is positive,
        # it costs about 1% of runtime, and it is the right thing on principle --
        # but it should not be cited as an improvement. quiesce=4 scores
        # identically to quiesce=2, so the extension rarely wants more than two
        # actions.
        #
        # A line that has built a manufacturer and not yet sold it looks like a
        # pure loss -- money gone, tile unflipped -- which is the exact failure
        # docs/diagnosis.md records for the one-ply bot, reappearing at the
        # beam's horizon instead of at ply one. Chess does not evaluate a
        # position with a capture pending; this does not evaluate one with a
        # sale pending. "Quiet" here means no unflipped tile of ours that a Sell
        # action could cash in right now.
        self.quiesce = quiesce

    def _opponent_move(self, state, actions):
        if not self.cheap_opponents:
            return self.opponent.choose(state, actions)
        seat = state.current.idx
        self.opponent.w = self.opponent.weights_for(state.n_players)
        best_value = None
        best_action = actions[0]
        base_links = set(state.links)
        reachable = connected_locations(state, list(state.merchants))
        for action in actions:
            probe = state.clone()
            apply_action(probe, action)
            ctx = self.opponent._sale_context(
                probe, reachable if set(probe.links) == base_links else None)
            owned, _sig = self.opponent.scan_board(probe)
            value = self.opponent.player_value(probe, seat, ctx, owned[seat])
            if best_value is None or value > best_value + 1e-9:
                best_value, best_action = value, action
        return best_action

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
            apply_action(state, self._opponent_move(state, actions))

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
            beam = self._select(children)
            for plan in beam:
                self._advance_opponents(plan.state)
            steps += 1

        for plan in beam:
            self._quiesce(plan)
        beam.sort(key=lambda p: -self._potential(p))
        return beam[0] if beam else None

    def _quiesce(self, plan) -> None:
        """Cash in pending sales before scoring, up to `quiesce` extra actions.

        Greedy rather than a second beam: sells are few, and the point is to
        finish the transaction, not to search it.
        """
        for _ in range(self.quiesce):
            state = plan.state
            if state.finished or state.current.idx != self.seat:
                return
            sells = legal_sells(state)
            if not sells:
                return
            best, best_value = None, None
            for action in sells:
                probe = state.clone()
                apply_action(probe, action)
                value = self._potential_state(probe)
                if best_value is None or value > best_value + 1e-9:
                    best, best_value = action, value
            if best is None:
                return
            apply_action(state, best)
            plan.actions.append(best)
            self._advance_opponents(state)

    def _potential_state(self, state) -> float:
        self.ev.w = self.ev.weights_for(state.n_players)
        return self.ev.position_value(state, self.seat)

    def best_actions(self, state, horizon: int | None = None) -> list:
        """Just the action sequence.

        Note it cannot be replayed onto a fresh state: a card index means a
        position in a hand that opponents' turns have since changed. Only the
        first action is safe to use, which is exactly how a re-planning bot
        should use it.
        """
        plan = self.search(state, horizon)
        return plan.actions if plan else []

    def _select(self, children: list) -> list:
        """Best `keep_per_root` plans for each distinct first action, then the
        best of whatever is left. `children` arrives already sorted by value."""
        if self.keep_per_root <= 0:
            return children[:self.width]
        chosen, taken = [], {}
        for plan in children:
            root = repr(plan.actions[0]) if plan.actions else None
            if taken.get(root, 0) < self.keep_per_root:
                taken[root] = taken.get(root, 0) + 1
                chosen.append(plan)
                if len(chosen) >= self.width:
                    return chosen
        picked = {id(p) for p in chosen}
        for plan in children:
            if id(plan) not in picked:
                chosen.append(plan)
                if len(chosen) >= self.width:
                    break
        return chosen[:self.width]

    def _potential(self, plan) -> float:
        """Rank partial plans. Final VP once the game is over, and the
        evaluation's estimate while it is still running."""
        if plan.state.finished:
            return float(plan.score)
        self.ev.w = self.ev.weights_for(plan.state.n_players)
        return self.ev.position_value(plan.state, self.seat)
