"""A bot that commits to one main industry and refuses to build the others.

A measurement instrument, not a candidate for shipping. The expert guide's
strongest claim is rule 6, "never mix main industries": you end up mid-level in
several and score half. Our bot touches 4.52 industries a game and gets 4.2 VP
per build against an expert 8-10, which is exactly the failure the rule
describes.

Before designing a planning mechanism to fix that, it is worth knowing whether
commitment *by itself* scores better in our engine at all. So this does the
crudest possible version: strike every build of a main industry other than the
chosen one off the list of legal moves, and otherwise play the ordinary
heuristic. If that does not beat the uncommitted bot, the rule does not transfer
to our engine and no amount of mechanism will make it.

Deliberately a hard filter rather than a weight. A weight would let the bot buy
its way out of the commitment whenever the position looked tempting, which is
the very behaviour under test.
"""

from ..actions import Build
from ..gamedata import Industry
from .heuristic import HeuristicBot

# Fixed order so a numeric spec (commit=0,1,2) names the same industry every run.
MAIN_INDUSTRIES = (Industry.COTTON_MILL, Industry.MANUFACTURER, Industry.POTTERY)


class CommitBot(HeuristicBot):
    """``commit:commit=1`` plays manufacturer only. ``commit=-1`` commits to
    nothing and must reproduce the plain heuristic exactly -- it is the control
    arm, and the test suite pins that equivalence."""

    name = "commit"
    DEFAULTS = {**HeuristicBot.DEFAULTS, "commit": -1}

    def _adaptive(self, state):
        """Commit to whichever main industry this position already supports.

        Tiles already on the board outrank the hand: they are a commitment
        already paid for, and switching away from them is what mixing *is*. The
        hand only breaks the tie before anything is built.
        """
        seat = state.current.idx
        score = dict.fromkeys(MAIN_INDUSTRIES, 0)
        for _town, _slot, tile in state.all_tiles():
            if tile.owner == seat and tile.industry in score:
                score[tile.industry] += 10
        for card in state.players[seat].hand:
            for industry in card.industries or ():
                if industry in score:
                    score[industry] += 1
            if card.town is not None:
                for slots in (state.data.towns[card.town].slots
                              if card.town in state.data.towns else ()):
                    for industry in slots:
                        if industry in score:
                            score[industry] += 1
        # Ties fall to MAIN_INDUSTRIES order, so the choice stays deterministic.
        return max(MAIN_INDUSTRIES, key=lambda i: (score[i], -MAIN_INDUSTRIES.index(i)))

    def choose(self, state, actions):
        index = int(self.weights_for(state.n_players)["commit"])
        mine = None
        if index == -2:
            mine = self._adaptive(state)
        elif 0 <= index < len(MAIN_INDUSTRIES):
            mine = MAIN_INDUSTRIES[index]
        if mine is not None:
            allowed = [
                a for a in actions
                if not (isinstance(a, Build)
                        and a.industry.is_sellable
                        and a.industry is not mine)
            ]
            # Never hand back an empty list: a position with nothing but
            # off-plan builds still has to produce a move, and passing there
            # would measure the filter's clumsiness rather than commitment.
            if allowed:
                actions = allowed
        return super().choose(state, actions)
