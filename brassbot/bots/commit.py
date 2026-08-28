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
from ..network import distances_from, player_network
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
        """Pick the main industry this game's board actually rewards.

        Driven by where the demand is and what we can play, because those are
        the two things that differ between games:

        * **Merchant demand, discounted by distance.** At 4p the *set* of
          merchant tiles is always the same -- two cotton, two manufacturer, one
          pottery, two wild, two blank -- but which location each lands on is
          dealt fresh, and that decides how many link actions a sale costs.
          Pottery is structurally scarce here: one dedicated slot against two.
        * **Cards in hand** that can actually build the thing.

        Tiles already built count for little, and that is the correction. The
        first version weighted them ten apiece, so the first build settled the
        commitment for the rest of the game and the "choice" was really made by
        the ordinary greedy evaluator. It scored +0.80 VP, against +3.65 for
        simply always playing manufacturer.
        """
        seat = state.current.idx
        score = dict.fromkeys(MAIN_INDUSTRIES, 0.0)

        # Distance is measured from where we can already build; before anything
        # is on the board every merchant is equally far away.
        network = player_network(state, seat)
        dist = distances_from(state, network) if network else {}

        for slot in state.merchant_slots():
            if slot.kind == "blank":
                continue
            near = 1.0 / (1.0 + dist.get(slot.merchant, 2))
            for industry in MAIN_INDUSTRIES:
                if slot.accepts(industry):
                    # A wild slot accepts everything, so it cannot discriminate
                    # between industries and is worth less than a dedicated one.
                    score[industry] += near * (3.0 if slot.kind != "any" else 1.0)

        for card in state.players[seat].hand:
            for industry in card.industries or ():
                if industry in score:
                    score[industry] += 1.0
            town = state.data.towns.get(card.town) if card.town else None
            if town is not None:
                for slots in town.slots:
                    for industry in slots:
                        if industry in score:
                            score[industry] += 0.5

        for _town, _slot, tile in state.all_tiles():
            if tile.owner == seat and tile.industry in score:
                score[tile.industry] += 1.5

        return max(MAIN_INDUSTRIES,
                   key=lambda i: (score[i], -MAIN_INDUSTRIES.index(i)))

    def _latched(self, state):
        """The adaptive choice, made once at the start and then held.

        Re-deciding every turn is not commitment, it is mixing with extra steps.
        Unlatched, the chooser picked manufacturer for 75% of decisions -- which
        should have been worth about +2.7 VP -- and scored +0.0, because it
        changed its mind partway and finished mid-level in two industries. Only
        14 of 60 games *opened* on cotton, yet a quarter of all decisions were
        cotton.

        Latched on an empty board, so a bot instance reused for a second game
        decides again rather than inheriting the last game's plan.
        """
        empty = not any(True for _t, _s, _tile in state.all_tiles())
        if empty or getattr(self, "_commitment", None) is None:
            self._commitment = self._adaptive(state)
        return self._commitment

    def choose(self, state, actions):
        index = int(self.weights_for(state.n_players)["commit"])
        mine = None
        if index == -2:
            mine = self._latched(state)
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
