"""Monte Carlo tree search.

Three choices here follow published results on comparable games rather than
taste; `docs/research-landscape.md` carries the citations.

* **Leaves are evaluated, not rolled out** by default -- though `rollout` exists
  as a research switch to value a leaf by the real final score instead; see the
  parameter's own note for what that costs and what it measured. A Brass game is ~124 moves, and
  playing one out at random produces a signal too weak and too sparse to be
  worth its cost. TAG's Power Grid agent likewise stores full states and
  evaluates on expansion with no rollout at all. We already have a tuned
  evaluation; the search's job is to correct its horizon errors, not to replace
  it with noise.
* **Progressive widening.** In multiplayer at short budgets, vanilla MCTS
  actually *loses* to minimax baselines (46.0%), and widening is what turns that
  around (71.9%). With a branching factor around 40 and a few hundred
  iterations, a tree that fans out fully is one ply deep and useless.
* **max^n backup.** Four-player Brass is not zero-sum, so a single scalar
  cannot describe a position. Every node carries a value per player and each
  player maximises their own component.

Hidden information is handled by determinizing at the root of each iteration:
opponents' hands and the deck are redealt from the pool the searcher cannot see.
Wild cards are left in place, since they are taken openly and everyone knows who
holds them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..actions import Action
from ..engine import apply_action, legal_actions
from ..network import connected_locations
from ..state import GameState
from .base import Bot
from .heuristic import HeuristicBot


def determinize(state: GameState, observer: int, rng) -> GameState:
    """Redeal every card the observer cannot see, keeping hand sizes intact."""
    s = state.clone()
    pool: list = list(s.deck)
    for seat, p in enumerate(s.players):
        if seat != observer:
            pool.extend(c for c in p.hand if not c.is_wild)
    rng.shuffle(pool)

    for seat, p in enumerate(s.players):
        if seat == observer:
            continue
        wilds = [c for c in p.hand if c.is_wild]  # publicly known, so left alone
        need = len(p.hand) - len(wilds)
        p.hand = wilds + [pool.pop() for _ in range(min(need, len(pool)))]
    s.deck = pool
    return s


class Bounds:
    """Running min/max of observed values, so UCT's exploration term stays
    commensurate with an evaluation that has no natural scale."""

    __slots__ = ("low", "high")

    def __init__(self):
        self.low = math.inf
        self.high = -math.inf

    def update(self, value: float) -> None:
        self.low = min(self.low, value)
        self.high = max(self.high, value)

    def normalise(self, value: float) -> float:
        if self.high > self.low:
            return (value - self.low) / (self.high - self.low)
        return 0.5


@dataclass
class Node:
    state: GameState
    to_move: int
    parent: "Node | None" = None
    action: Action | None = None
    children: list["Node"] = field(default_factory=list)
    untried: list[Action] | None = None  # ordered best-first by the prior
    visits: int = 0
    totals: list[float] = field(default_factory=list)

    @property
    def terminal(self) -> bool:
        return self.state.finished


class MCTSBot(Bot):
    name = "mcts"

    DEFAULTS = {
        "iterations": 300,
        # A full tuning run (17 candidates, 57 min) moved this to 0.5 and
        # reported +3.0 VP on its validation block against a +-2.2 noise floor --
        # then measured 2.8 VP WORSE on the reporting seeds, paired against this
        # value on identical games. Two seed blocks favoured 0.5, one favoured
        # 1.0; pooled it is a wash. Not shipped: an unreplicated gain is not a
        # gain. Kept at the value the published multiplayer work suggests.
        #
        # widen_k, widen_alpha and prior_width were all left alone by that run --
        # nothing beat the noise floor. Search parameters here appear to be near
        # a flat optimum, so the remaining gap is in the evaluation, not the
        # search settings.
        "c": 1.0,           # UCT exploration, against normalised values
        "widen_k": 2.0,     # children allowed = widen_k * visits ** widen_alpha
        "widen_alpha": 0.5,
        "prior_width": 24,  # candidates the prior ranks before the tree sees them
        # Probability of valuing a leaf by playing the game out at random and
        # taking the ACTUAL final score, instead of asking the evaluation.
        #
        # The evaluation is both the prior and the leaf value, so search can only
        # ever prefer what the evaluation already likes -- measured, MCTS gained
        # +9 VP over the heuristic while changing its strategy not at all. A real
        # play-out is the one signal uncorrelated with those blind spots.
        #
        # A TRUNCATED play-out does not do this: it ends in the same evaluation,
        # so the systematic bias survives and only noise is added. It has to run
        # to the end of the game, which costs 160 ms against 0.35 ms for the
        # evaluation -- 454x. Affordable only for testing whether the signal is
        # better per iteration.
        "rollout": 0.0,
    }

    def __init__(self, seed: int = 0, **params):
        super().__init__(seed)
        unknown = set(params) - set(self.DEFAULTS)
        if unknown:
            raise KeyError(f"unknown parameters: {sorted(unknown)}")
        self.p = {**self.DEFAULTS, **params}
        # The same evaluation the heuristic bot uses, for leaves and for the
        # prior that orders which actions the tree tries first.
        self.evaluator = HeuristicBot(seed=seed)

    # -- evaluation ---------------------------------------------------------

    def _values(self, state: GameState) -> list[float]:
        """One value per player. Leaves need all of them: max^n backs up a
        vector, because a 4-player game has no single scalar score."""
        if self.p["rollout"] and self.rng.random() < self.p["rollout"]:
            return self._playout_values(state)
        self.evaluator.w = self.evaluator.weights_for(state.n_players)
        # Shared across all four seats: none of it depends on which one.
        context = self.evaluator._sale_context(state)
        owned = self.evaluator.tiles_by_owner(state)
        return [self.evaluator.player_value(state, i, context, owned[i])
                for i in range(state.n_players)]

    def _playout_values(self, state: GameState) -> list[float]:
        """Play the game out at random and return the real final scores.

        Unbiased by construction -- it never consults the evaluation, so a line
        the evaluation undervalues can still back up a good number. Expensive,
        and noisy enough that it is meant to be blended rather than used alone.
        """
        probe = state.clone()
        guard = 0
        while not probe.finished and guard < 400:
            actions = legal_actions(probe)
            if not actions:
                break
            apply_action(probe, self.rng.choice(actions))
            guard += 1
        return [p.vp for p in probe.players]

    def _seat_value(self, state: GameState, seat: int) -> float:
        """Just one player's value. The prior only ranks moves for the player to
        move, so evaluating all four and discarding three was 3/4 of the single
        largest cost in the search."""
        self.evaluator.w = self.evaluator.weights_for(state.n_players)
        return self.evaluator.player_value(state, seat)

    def _ranked_actions(self, state: GameState, actions: list[Action]) -> list[Action]:
        """Order actions by a one-ply look, best first, and keep the best few.

        This is the prior. Without it, widening would expand whatever happened to
        come first out of move generation, and at a few hundred iterations the
        tree would never reach the moves that matter.
        """
        seat = state.current.idx
        ev = self.evaluator
        ev.w = ev.weights_for(state.n_players)
        # Reachability is a search over the link graph, and only a Network
        # action changes it. Ranking candidates re-derived it for every single
        # one, which is the prior's largest cost and is paid at every node of
        # the tree.
        base_links = set(state.links)
        base_reachable = connected_locations(state, list(state.merchants))

        scored = []
        for action in actions:
            probe = state.clone()
            apply_action(probe, action)
            reachable = base_reachable if set(probe.links) == base_links else None
            context = ev._sale_context(probe, reachable)
            owned, _sig = ev.scan_board(probe)
            scored.append((ev.player_value(probe, seat, context, owned[seat]),
                           action))
        scored.sort(key=lambda pair: -pair[0])
        width = self.p["prior_width"]
        return [a for _, a in scored[:width]] if width else [a for _, a in scored]

    # -- tree ---------------------------------------------------------------

    def _expandable(self, node: Node) -> bool:
        allowed = self.p["widen_k"] * (node.visits ** self.p["widen_alpha"])
        return bool(node.untried) and len(node.children) < max(1, int(math.ceil(allowed)))

    def _select_child(self, node: Node, bounds: Bounds) -> Node:
        seat = node.to_move
        log_n = math.log(max(1, node.visits))
        best, best_score = None, -math.inf
        for child in node.children:
            exploit = bounds.normalise(child.totals[seat] / child.visits)
            explore = self.p["c"] * math.sqrt(log_n / child.visits)
            score = exploit + explore
            if score > best_score:
                best, best_score = child, score
        return best

    def _ensure_actions(self, node: Node) -> None:
        if node.untried is None:
            actions = legal_actions(node.state)
            node.untried = self._ranked_actions(node.state, actions) if actions else []

    def _iterate(self, root: Node, bounds: Bounds) -> None:
        node = root

        # descend
        while not node.terminal:
            self._ensure_actions(node)
            if self._expandable(node):
                action = node.untried.pop(0)
                child_state = node.state.clone()
                apply_action(child_state, action)
                child = Node(state=child_state,
                             to_move=child_state.current.idx if not child_state.finished else node.to_move,
                             parent=node, action=action)
                node.children.append(child)
                node = child
                break
            if not node.children:
                break
            node = self._select_child(node, bounds)

        values = self._values(node.state)
        for value in values:
            bounds.update(value)

        while node is not None:
            node.visits += 1
            if not node.totals:
                node.totals = [0.0] * len(values)
            for i, v in enumerate(values):
                node.totals[i] += v
            node = node.parent

    # -- policy -------------------------------------------------------------

    def choose(self, state: GameState, actions: list[Action]) -> Action:
        if len(actions) == 1:
            return actions[0]

        me = state.current.idx
        root = Node(state=state.clone(), to_move=me)
        root.untried = self._ranked_actions(state, actions)
        bounds = Bounds()

        for _ in range(self.p["iterations"]):
            # A fresh determinization per iteration: the tree is searched over
            # many consistent worlds rather than one guessed one.
            sampled = determinize(state, me, self.rng)
            root.state = sampled
            self._iterate(root, bounds)

        if not root.children:
            return actions[0]
        # Most-visited child, the standard robust choice.
        best = max(root.children, key=lambda c: c.visits)
        return best.action
