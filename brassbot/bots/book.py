"""A Canal Era opening book, handing off to another bot for the Rail Era.

Built to test one hypothesis and nothing else: **that our gap is sequencing.**

Measured, our bot reaches the Rail Era on 33.9 VP where an expert reaches 70-80,
and it gets there by building more tiles than an expert (10.1 vs ~6) worth less
each (4.2 VP vs ~9.5). The expert shape is a handful of level 2+ tiles flipped
*inside the Canal Era*, so they survive the era wipe and score a second time,
with links laid afterwards around industry that is already flipped.

So this forces the expert's Canal Era plan and then gets out of the way. The
Rail Era is played by the ordinary bot, unchanged. If VP entering rail rises and
the final score rises with it, sequencing explains the gap. If VP entering rail
rises and the final score does not, the Canal Era is not where our points are
being lost, and that is worth knowing too.

**RESULT: this failed, and failed at its own objective.** Measured against the
plain heuristic over 60 games:

    seat 0       mean VP   VP entering rail   flipped in canal   links
    heuristic       99.1               32.7               3.33    12.4
    book            93.9               13.9               2.03     9.7

VP entering rail more than halved. The plan is kept because knowing this was
tried is worth more than the file costs, and because the failure is informative:
a fixed priority list fires its develops immediately, spending two early actions
on zero VP and zero income, and it never builds coal, so it starves before it can
afford the level 2+ tiles the whole plan depends on. The expert game interleaves
instead -- loan, link, cheap level-1 iron for the income, and only then develop,
once iron is cheap or already flipped. "Develop when iron happens to be cheap" is
not something a priority list can say.

The plan, from `docs/expert-strategy.md` (4 players):

1. Develop both level-1 breweries -- every line starts here.
2. Develop one level-1 manufacturer, plus a level-1 coal or iron.
3. Build iron at every opportunity; it is cheap for its VP and flips with no
   Sell action when anyone consumes it. Overbuild your own level-1 iron rather
   than opening a new site that would need a link first.
4. Secure brewery sites; an unflipped brewery still denies the site.
5. Build two level-2 manufacturers -- they need no coal, so they need no link.
6. One Sell action, flipping everything at once with your own beer.
7. Build canals only when something needs them.
"""

from __future__ import annotations

from ..actions import Build, Develop, Loan, Network, Pass, Scout, Sell
from ..gamedata import Era, Industry
from .base import Bot
from .heuristic import HeuristicBot


class BookBot(Bot):
    name = "book"

    #: money below which the plan will borrow rather than stall
    LOAN_FLOOR = 8

    def __init__(self, seed: int = 0, base: str = "heuristic"):
        super().__init__(seed)
        self._base_name = base
        self.base = HeuristicBot(seed=seed) if base == "heuristic" else None
        if self.base is None:  # any other registered bot
            from . import make
            self.base = make(base, seed=seed)

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _level(state, action: Build) -> int | None:
        return state.players[state.current.idx].lowest_level(action.industry)

    @staticmethod
    def _on_mat(player, industry: Industry, level: int) -> bool:
        return player.mat[industry][level - 1] > 0

    def _develops(self, actions, industry: Industry):
        return [a for a in actions
                if isinstance(a, Develop) and industry in a.industries]

    def _builds(self, state, actions, industry: Industry, min_level: int = 1):
        out = []
        for a in actions:
            if not isinstance(a, Build) or a.industry is not industry:
                continue
            level = self._level(state, a)
            if level is not None and level >= min_level:
                out.append(a)
        return out

    # -- the plan ------------------------------------------------------------

    def choose(self, state, actions):
        if state.era is not Era.CANAL:
            return self.base.choose(state, actions)

        p = state.current
        pick = self._canal_plan(state, actions, p)
        # Anything the plan cannot express falls through to ordinary play, so the
        # book only ever *adds* structure rather than removing options.
        return pick if pick is not None else self.base.choose(state, actions)

    def _canal_plan(self, state, actions, p):
        # 1. Sell everything at once, as late as possible but never miss it.
        sells = [a for a in actions if isinstance(a, Sell)]
        if sells:
            best = max(sells, key=lambda a: len(a.sales))
            rounds_left = state.rounds_this_era - state.round
            if len(best.sales) >= 2 or rounds_left <= 1:
                return best

        # 2. Clear both level-1 breweries first.
        if self._on_mat(p, Industry.BREWERY, 1):
            got = self._develops(actions, Industry.BREWERY)
            if got:
                # prefer a develop that clears two tiles at once
                return max(got, key=lambda a: len(a.industries))

        # 3. Then one manufacturer level 1, paired with a coal or iron level 1.
        if self._on_mat(p, Industry.MANUFACTURER, 1):
            got = self._develops(actions, Industry.MANUFACTURER)
            if got:
                return max(got, key=lambda a: len(a.industries))

        # 4. Iron at every opportunity, highest level available.
        iron = self._builds(state, actions, Industry.IRON_WORKS)
        if iron:
            return max(iron, key=lambda a: self._level(state, a) or 0)

        # 5. Secure brewery sites, level 2+ once the level 1s are gone.
        beer = self._builds(state, actions, Industry.BREWERY,
                            min_level=1 if self._on_mat(p, Industry.BREWERY, 1) else 2)
        if beer:
            return max(beer, key=lambda a: self._level(state, a) or 0)

        # 6. Two level-2 manufacturers -- no coal, so no link needed.
        manu = self._builds(state, actions, Industry.MANUFACTURER, min_level=2)
        if manu:
            return max(manu, key=lambda a: self._level(state, a) or 0)

        # 7. Borrow rather than stall.
        if p.money < self.LOAN_FLOOR:
            loans = [a for a in actions if isinstance(a, Loan)]
            if loans:
                return loans[0]

        return None
