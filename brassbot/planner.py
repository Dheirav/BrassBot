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
from .engine import apply_action, legal_actions, legal_sells, link_icons_at
from .gamedata import Era
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
                 quiesce: int = 2, vp_blend: float = 1.0, roots: int = 0):
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
        # pair_search=0 deliberately. The shipped heuristic now searches both
        # actions of its turn, which is right for the real bot and ruinous here:
        # this model is invoked for 645 opponent decisions a game, inside every
        # plan step, so a two-ply search per reply multiplies a run that already
        # takes over three hours. The opponent model has always been an
        # approximation; this keeps it the one that was measured.
        self.opponent = HeuristicBot(pair_search=0)
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
        # How much of a plan's score is an actual VP projection rather than the
        # hand-tuned evaluation.
        #
        # The evaluation is ~60% proxy: at one node it read 112.6 where banked VP
        # was 45. Those proxies -- income x rounds, merchant_access at 2.4 a
        # town, beer_capacity at 3, liquidity at 8 -- move in units of 2 to 6,
        # while the VP differences they decide are 1 to 5. So the proxy wins the
        # comparison, and a beam then optimises the proxy for eight plies. It
        # also means the Canal-Era double is invisible as a reason to build,
        # because the evaluation only applies it once a tile has flipped.
        #
        # Projecting what the scoring rules would actually pay makes the real
        # objective the thing being searched, with the evaluation left as a
        # tie-breaker for everything VP cannot see yet (money, income, unflipped
        # tiles).
        self.vp_blend = vp_blend
        # Search this many candidate first actions in SEPARATE beams, and take
        # whichever reaches the best line. 0 keeps the single shared beam.
        #
        # A shared beam prunes globally by value, so one first action's
        # continuations sweep the whole width: measured over 26 decisions, the
        # distinct first actions alive fall 8 -> 5.0 -> 2.7 -> 1.9 by ply four,
        # and 57% of searches have committed to one by then. Everything after
        # that refines a choice already made, which is why horizon 14 plays
        # move-identically to horizon 8.
        #
        # This is NOT keep_per_root, which reserved slots inside one width-12
        # beam and so left each root one plan deep (115.4 against 132.2). Each
        # root here gets a beam of its own.
        self.roots = roots

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
        # Apply the same commitment filter the heuristic uses. It lives in
        # HeuristicBot.choose, which the beam never calls -- so the shipped
        # commitment was being applied to the planner's OPPONENTS (through
        # _opponent_move) and not to the planner itself. It touched 5.17
        # industries a game against the supposedly-uncommitted heuristic's 4.52.
        actions = self.ev._committed(state, actions)
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
        return self._grow(Plan(state=root, seat=self.seat), horizon)

    def _grow(self, start, horizon: int | None):
        beam = [start]
        steps = len(start.actions)

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

    def projected_vp(self, state) -> float:
        """What the remaining scorings would pay on this board, as it stands.

        Links score at the end of the era they are in -- canal links are removed
        at the boundary and never score again. A flipped level 2+ tile in the
        Canal Era scores at BOTH scorings, which is what makes building one worth
        twice its face and is exactly what the evaluation cannot express until
        after the tile has already flipped.
        """
        data = state.data
        total = float(state.players[self.seat].vp)
        for link_id, owner in state.links.items():
            if owner == self.seat:
                for end in data.link_by_id[link_id].ends:
                    total += link_icons_at(state, end)
        for _town, _slot, tile in state.all_tiles():
            if tile.owner != self.seat or not tile.flipped:
                continue
            vp = data.tile(tile.industry, tile.level).vp
            if state.era is Era.CANAL and tile.level >= 2:
                vp *= 2
            total += vp
        return total

    def _potential(self, plan) -> float:
        """Rank plans by what they would actually score, with the evaluation as
        a tie-breaker for what VP cannot see yet."""
        state = plan.state
        if state.finished:
            return float(plan.score)
        self.ev.w = self.ev.weights_for(state.n_players)
        heur = self.ev.position_value(state, self.seat)
        if not self.vp_blend:
            return heur
        return self.vp_blend * self.projected_vp(state) + (1 - self.vp_blend) * heur
