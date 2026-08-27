"""Baseline bots. Neither of these is trying to be good -- they exist to give
the search bot something to beat, and to keep the harness honest."""

from __future__ import annotations

from ..actions import Build, Develop, Loan, Network, Pass, Scout, Sell
from ..gamedata import Era, Industry
from .base import Bot


class RandomBot(Bot):
    """Uniform over legal actions. The floor."""

    name = "random"

    def choose(self, state, actions):
        return self.rng.choice(actions)


class GreedyBot(Bot):
    """Fixed action priorities with one piece of real judgement: get connected
    early. Without a network nothing sells, nothing flips, and income never
    starts, which is the trap uniform-random play falls into."""

    name = "greedy"

    PRIORITY = {Sell: 100, Build: 60, Network: 55, Develop: 20, Scout: 15,
                Loan: -1, Pass: 0}

    def choose(self, state, actions):
        player = state.current
        own_links = sum(1 for owner in state.links.values() if owner == player.idx)

        def score(action):
            base = self.PRIORITY[type(action)]
            if isinstance(action, Sell):
                base += 10 * len(action.sales)
            elif isinstance(action, Network) and own_links < 3:
                base = 80
            elif isinstance(action, Loan):
                base = 70 if player.money < 8 and player.income > -6 else -1
            return base

        best = max(score(a) for a in actions)
        return self.rng.choice([a for a in actions if score(a) == best])
