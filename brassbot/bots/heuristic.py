"""A bot that actually evaluates the board.

`greedy` picks by action type. This one applies each legal action to a clone and
scores the resulting position, which is the first point at which the bot can
answer questions like "is this sale worth more than that mine?".

The evaluation is built around what actually banks points in Brass:

* **Nothing scores until it flips.** An unflipped tile is worth no VP, no
  income, and lights up no links. It gets partial credit here as a promise, not
  an asset.
* **Income compounds.** A point of income is worth every remaining round of the
  game, so the same income is worth far more in the Canal Era than late in the
  Rail Era. The weight scales with rounds left rather than being flat.
* **Links score off flipped neighbours**, plus a guaranteed 2 from any merchant.
* **Canal-only tiles stranded on the mat in the Rail Era are dead weight** --
  level 1 tiles cannot be built after the era turns, so they block every higher
  level of that industry until developed away.

The opponent term matters more here than in most games: draining a rival's mine
or drinking their beer flips *their* tile and pays *them* income. A bot that
only maximised its own score would happily do an opponent a large favour.
"""

from __future__ import annotations

import math

from ..actions import Build, Loan, Pass
from ..engine import apply_action, link_icons_at
from ..gamedata import Era, Industry, income_level
from ..network import connected_locations
from .base import Bot


# The three sellable industries, in a fixed order so a numeric setting names the
# same one every run.
MAIN_INDUSTRIES = (Industry.COTTON_MILL, Industry.MANUFACTURER, Industry.POTTERY)


class HeuristicBot(Bot):
    name = "heuristic"

    # Weights are instance data so they can be tuned by playing rather than by
    # argument -- see tools/tune.py.
    DEFAULTS = {
        # Which main industry to commit to, as an index into MAIN_INDUSTRIES;
        # -1 commits to nothing. Builds of the other two are struck off the
        # move list entirely rather than merely discouraged, because a weight
        # lets the bot buy its way out of the commitment whenever a position
        # looks tempting, which is the behaviour being prevented.
        #
        # Manufacturer at every player count. Measured on the report seeds
        # against an uncommitted control: 4p +1.53, 3p +2.71, 2p +2.17, pooled
        # +2.14 +- 0.85. Cotton and pottery both lose everywhere, pottery
        # heavily -- so this is worth about 2 VP, and picking the right industry
        # matters far more than committing at all. The guide names cotton for
        # 2p; that does not transfer here, because reaching cotton's payoff at
        # level 3 costs five cleared tiles and a 1-ply bot will not spend them.
        "commit": 1,
        "unflipped": 0.375,   # odds we actually realise an unflipped tile's payoff
        # Money is worth ZERO victory points -- it is only the second tiebreak.
        # So cash has purely instrumental value: what it buys before the game
        # ends. Held low deliberately; the liquidity term carries "can I still
        # act", and leftover cash at the final whistle is wasted.
        "money": 0.045,
        "income": 0.1125,      # per income level, per remaining round
        "blocked": 6,      # per industry blocked by a stranded canal-only tile
        "rival": 0.225,        # how much the best opponent's position counts against us
        "links_held": 0.3,  # mild preference for link tiles still in reserve
        # Being broke is not just "less money": it removes almost every action
        # from the list. This term is steep near zero and flat once solvent, so
        # it buys liquidity without rewarding hoarding.
        "liquidity": 8,
        "liquidity_scale": 8.438,
        # Negative income is not merely less money. If you cannot pay it you
        # sell industry tiles at half cost and lose their VP outright, and if
        # you still cannot pay you lose a VP per pound. It compounds, so it is
        # charged on top of the linear income term rather than folded into it.
        "debt": 0.0633,
        "pass_bias": -0.5,   # only to break ties between equal-looking positions
        # A sellable tile is worth almost nothing until it can actually be sold,
        # and nearly its full value once it can. Without this split the bot
        # never starts the build -> connect -> beer -> sell chain, because every
        # step before the last one looks like a pure loss. See docs/diagnosis.md.
        "sell_ready": 0.3187,
        # Credit for merchant connectivity itself, so building *toward* a sale
        # registers as progress rather than as spending money for nothing.
        "merchant_access": 2.4,
        # Cash is only worth what it buys before the game ends, and it scores
        # nothing at the final whistle. So its value has to decay to zero as the
        # actions run out -- otherwise the bot happily finishes holding money it
        # can never spend. Ramps down over this many remaining rounds.
        "money_horizon": 4,
        # A pound early is worth more than a pound late, for the same reason a
        # point of income is: it compounds. Cash in the Canal Era buys tiles that
        # flip, score TWICE (level 2+ survives the wipe and scores again), and
        # pay income for the rest of the game.
        #
        # Without this the loan arithmetic runs backwards: a loan costs 3 income
        # levels, priced at 3 * rounds * income -- large early, small late -- while
        # +30 pounds was priced flat. So the bot refused to borrow in canal and
        # borrowed freely in rail, the inverse of expert play.
        #
        # DEFAULTED OFF, because raising it works and costs 25 VP. At 0.02 the bot
        # reaches the expert band of 4-6 canal loans and meets 7 of 11 profile
        # dimensions instead of 4 -- while its mean score falls from 94.6 to 70.0.
        # Every loan spends an action. Experts can afford 4-6 of their 16 canal
        # actions on borrowing because the remaining ones convert at ~5 VP each;
        # ours convert at ~3, so the trade is simply bad for us. Borrowing is a
        # symptom of being able to use money well, not a cause of it.
        #
        # Left as a tunable so it can be revisited once action productivity
        # improves, at which point the trade should flip.
        "money_compounding": 0.0,
        # You may only ever build the LOWEST tile left on your mat, so the
        # expensive tiles are gated behind clearing the cheap ones. Iron runs
        # 3 VP at level I and 9 at level IV; pottery 10 and 20. A bot that never
        # climbs plays the bottom of every stack and caps itself near half an
        # expert score. Develop pays nothing immediately -- it spends a card and
        # an iron to REMOVE a tile -- so its whole value is what it unlocks.
        #
        # Priced as the VP of the next tile available in each industry.
        #
        # This has a known perverse edge: pottery I is worth 10 VP and cannot be
        # developed, so building it *lowers* this term, and the bot duly stops
        # building pottery. A "count the blockers" formulation was written to
        # fix exactly that, and measured worse -- mirror 95.1 against 98.8, and
        # 100.4 against 104.8 versus greedy. Skipping pottery turns out to cost
        # less than the iron climb gains, which matches the expert view that the
        # full pottery line eats 10 of your 16 rail actions. Kept on the
        # measurement, against the theory.
        "mat_potential": 0.25,
        # How many rounds a tile realistically needs in order to flip. An
        # unflipped tile is a promise, and a promise is only worth something if
        # there is still time to collect on it.
        #
        # Level 1 tiles are REMOVED at the end of the Canal Era, so one built
        # late in canal and not yet flipped is deleted having scored nothing --
        # measured at 1.36 tiles per player per game, mostly brewery I. Level 2+
        # tiles survive the wipe and have the whole Rail Era to flip in.
        "flip_horizon": 3.0,
        # Beer you own, per barrel still on your own breweries.
        #
        # A Sell action can flip several tiles at once, but every tile needs its
        # own beer. Merchant beer gives one barrel per merchant tile, so without
        # breweries of your own each Sell flips exactly one tile. Measured: 0.2
        # own barrels, 2.5 tiles sellable, 0.9 of them fundable together -- 80
        # sell actions flipped 83 tiles, and 73% of the time sellable tiles were
        # left stranded.
        #
        # The brewery tile itself is already credited as an unflipped tile. This
        # prices the barrels on top, because their value is not the brewery's VP
        # but the other tiles they let you flip.
        # Score gain NOT established: +1.1 +-1.2 over 100 paired games. Kept at
        # 3.0 because three measurements agree in sign, tiles-per-sell rises
        # monotonically 0.92 -> 1.06 -> 1.15, and nothing showed harm. Treat it as
        # directionally right and statistically unproven; ~400 games per arm would
        # settle it.
        "beer_capacity": 3.0,
        # The hand was invisible to this evaluation entirely, which made a wild
        # card worth zero. Scout then read as: three cards gone (0), two wilds
        # gained (0), one action spent -- a pure loss. The bot scouted 0.2 times
        # a game and never planned around what it could actually play.
        #
        # Both DEFAULTED OFF. Measured:
        #
        #   wild  breadth   mean VP   scouts/game
        #   0.0     0.0        98.6          0.20   <- baseline
        #   2.0     0.15       93.4          3.60   <- farms wilds
        #   1.0     0.05       98.2          3.05
        #   1.0     0.15      100.5          3.05   <- +1.9, only ~1.2 sigma
        #
        # At 2.0 the bot farms cards: an action is worth ~3 VP, and two wilds
        # paid +4.0, so Scout was always profitable and it looped. Below the
        # price of an action that pathology goes away, but nothing then clears
        # the noise floor either.
        #
        # The conclusion is about the proxy, not the idea. Counting cards is not
        # what makes a hand good -- what those cards LET YOU DO is, and that
        # depends on how scarce each one is and what the board looks like. See
        # the card-scarcity note in NEXT.md for the formulation worth trying.
        "wild_card": 0.0,
        "hand_breadth": 0.0,
        # How contested a site is, per copy of its location card in the deck.
        #
        # Experts count the deck rather than the hand. A town whose card appears
        # ONCE per era is effectively reserved for whoever holds it -- there is no
        # rush. A town with three copies can be reached by a rival at any moment,
        # so you take it first. Same card in hand, opposite urgency, decided
        # entirely by how many copies exist.
        #
        # This prices the board rather than the hand: claiming a contested town
        # is worth more than claiming a safe one, because the safe one will still
        # be there later. Spending an action is what earns it, which is the shape
        # that has worked here -- unlike counting cards you are holding.
        # DEFAULTED OFF. Measured: 99.1 at 0.0, 88.5 at 0.3, 89.5 at 0.8.
        #
        # The bug this went through first is instructive on its own: scoring the
        # claim per TILE rather than per town paid the bot to pile tiles into the
        # same contested town, and it duly built 11.9 tiles instead of 10.8 and
        # lost 11.3 VP. Counting once per town is verified correct -- a second
        # tile in Birmingham adds its own value and no claim.
        #
        # But it still costs ~10 VP, and the reason is conceptual. This encodes
        # "contested is more VALUABLE". The real principle is "contested is more
        # URGENT". Nuneaton, at one card copy, is just as good a site to own; you
        # can simply take it later because nobody can race you there. A static
        # state evaluation naturally expresses value, and urgency is a property of
        # sites you have NOT claimed yet -- the risk of losing them before you
        # act. That is the other side of the board from where this sits.
        "site_urgency": 0.0,
    }

    # Per-player-count overrides layered on DEFAULTS. The formats are genuinely
    # different games -- 39 / 35 / 31 actions each, different decks, different
    # numbers of merchants -- so one weight vector does not fit all three. Filled
    # in by tuning each format separately; an empty entry just means DEFAULTS.
    PROFILES: dict[int, dict] = {
        2: {"sell_ready": 0.478, "unflipped": 0.1875},
        3: {"unflipped": 0.2812},
    }

    def __init__(self, seed: int = 0, **weights):
        super().__init__(seed)
        unknown = set(weights) - set(self.DEFAULTS)
        if unknown:
            raise KeyError(f"unknown weights: {sorted(unknown)}")
        # Explicit overrides beat the per-format profile, so that a tuning run
        # can pin every weight it is testing.
        self._explicit = dict(weights)
        self._resolved: dict[int, dict] = {}
        self.w = {**self.DEFAULTS, **weights}

    def weights_for(self, players: int) -> dict:
        if players not in self._resolved:
            self._resolved[players] = {
                **self.DEFAULTS,
                **self.PROFILES.get(players, {}),
                **self._explicit,
            }
        return self._resolved[players]

    def choose(self, state, actions):
        """Strictly deterministic: the same position always yields the same move.

        Ties are broken by generation order rather than randomly, so a game is
        reproducible from its seed alone and repeated runs cannot drift. That
        also makes a regression in play visible instead of hiding inside
        run-to-run noise.
        """
        self.w = self.weights_for(state.n_players)
        actions = self._committed(state, actions)
        me = state.current.idx
        best_value = None
        best_action = None

        # Placing a link is the only thing that changes what is reachable, so
        # every other candidate can reuse this one search instead of repeating
        # it. Compared by key set rather than by count, so that an era boundary
        # -- which wipes canal links -- can never be mistaken for no change.
        base_links = set(state.links)
        base_reachable = connected_locations(state, list(state.merchants))

        # The opponents' half of the evaluation, computed once for the position
        # we are moving from. Any candidate that leaves the shared state alone
        # reuses it.
        base_owned, base_board_sig = self.scan_board(state)
        base_context = self._sale_context(state, base_reachable)
        base_rivals = [self.player_value(state, i, base_context, base_owned[i])
                       for i in range(state.n_players) if i != me]
        shared = (self.shared_signature(state, me, base_owned),
                  max(base_rivals) if base_rivals else 0.0)

        for action in actions:
            probe = state.clone()
            apply_action(probe, action)
            reachable = base_reachable if set(probe.links) == base_links else None
            value = self.position_value(probe, me, reachable, shared)
            if isinstance(action, Pass):
                value += self.w["pass_bias"]
            if best_value is None or value > best_value + 1e-9:
                best_value, best_action = value, action

        return best_action

    def _committed(self, state, actions):
        """Drop builds of main industries we are not committed to."""
        index = int(self.w.get("commit", -1))
        if not 0 <= index < len(MAIN_INDUSTRIES):
            return actions
        mine = MAIN_INDUSTRIES[index]
        allowed = [
            a for a in actions
            if not (isinstance(a, Build) and a.industry.is_sellable
                    and a.industry is not mine)
        ]
        # Never return nothing: a position offering only off-plan builds still
        # has to produce a move, and passing there would be worse than building
        # the wrong thing.
        return allowed or actions

    # --- evaluation ---------------------------------------------------------

    def position_value(self, state, me: int, reachable=None, shared=None) -> float:
        """Our position, net of what the strongest opponent holds.

        ``shared`` is ``(signature, best_rival)`` from a position whose shared
        state this one may match. Three of the four seats we evaluate are
        opponents, and our own move usually cannot change what any of them is
        worth -- so when the signature agrees, their value is carried over
        instead of recomputed. That is three quarters of the evaluation skipped.
        """
        context = self._sale_context(state, reachable)
        # One walk of the board, split by owner. Each player_value used to scan
        # every tile to pick out the handful it owns, so evaluating four seats
        # meant four full scans to extract four disjoint subsets.
        owned, board_sig = self.scan_board(state)
        mine = self.player_value(state, me, context, owned[me])

        best_rival = None
        if shared is not None:
            base_sig, base_rival = shared
            if base_sig == self.shared_signature(state, me, owned):
                best_rival = base_rival
        if best_rival is None:
            rivals = [self.player_value(state, i, context, owned[i])
                      for i in range(state.n_players) if i != me]
            best_rival = max(rivals) if rivals else 0.0
        return mine - self.w["rival"] * best_rival

    @classmethod
    def _contest(cls, state) -> dict:
        """Copies of each town's location card in this game's deck.

        A farm brewery has no location card at all, so it scores 0 -- correctly,
        since it can only be reached with an industry or wild card and no
        opponent can race you there with a location card.
        """
        n = state.n_players
        cache = cls.__dict__.get("_contest_cache")
        if cache is None:
            cache = {}
            setattr(cls, "_contest_cache", cache)
        if n not in cache:
            cache[n] = dict(state.data.decks[n]["locations"])
        return cache[n]

    @staticmethod
    def _sale_context(state, reachable=None):
        """What a sale needs, computed once per position instead of per tile.

        Deliberately an approximation: "connected to some merchant, and some
        merchant in this game accepts this good". None of it depends on the
        seat, so it is computed once rather than once per player. Checking the exact merchant-by-merchant reachability
        would mean a search per merchant per candidate action, which move
        generation cannot afford.
        """
        # ``reachable`` is a breadth-first search over the link graph and the
        # single most expensive part of the context. It depends only on which
        # links are placed, so a caller evaluating many candidate moves can
        # compute it once and hand it back for every candidate that did not
        # place a link. The rest is a walk of ten merchant slots and is cheaper
        # to redo than to invalidate.
        if reachable is None:
            reachable = connected_locations(state, list(state.merchants))
        accepted = {slot.kind for slots in state.merchants.values() for slot in slots}
        merchant_beer = any(slot.beer > 0 for slot in state.merchant_slots())
        return reachable, accepted, merchant_beer

    @staticmethod
    def tiles_by_owner(state) -> list[list]:
        """Every placed tile, bucketed by owner, in one pass."""
        buckets, _sig = HeuristicBot.scan_board(state)
        return buckets

    @staticmethod
    def scan_board(state):  # noqa: D401 - see tiles_by_owner
        """One walk of the board: tiles bucketed by owner, and a signature of
        everything shared that *another* seat's value can depend on.

        The signature is what makes rival values reusable across candidate
        moves. Walking the board separately to compute it would cost more than
        the recomputation it saves, so it rides along with the bucketing.

        The signature records tile *identity*, not counts. Counting was tried
        and is wrong: overbuilding replaces a flipped tile with an unflipped
        one, so the flipped total is not monotone. A build that overbuilt a
        flipped tile while its coal draw flipped another left the count at 8
        both sides, and every rival holding a link into that town silently lost
        icons -- worth 3 VP to one of them. Counts can cancel; identities cannot.
        """
        buckets: list[list] = [[] for _ in range(state.n_players)]
        board = []
        for town, slot, tile in state.all_tiles():
            buckets[tile.owner].append((town, tile))
            board.append((town, slot, tile.owner, tile.industry, tile.level,
                          tile.flipped, tile.resources))
        return buckets, tuple(board)

    @staticmethod
    def shared_signature(state, me: int, buckets) -> tuple:
        """Exactly what an *opponent's* value reads, and nothing else.

        Narrowed twice, and both narrowings mattered:

        Not the acting player's money, income, hand or mat. Those change on
        nearly every move and no opponent's value reads them.

        Not the acting player's unflipped tiles either. Including every tile on
        the board was correct but far too strict -- a Build always changes the
        board, so the reuse fired on only 30% of candidates. An opponent reads
        our tiles solely through ``link_icons_at``, which counts flipped tiles,
        so an unflipped tile of ours is invisible to them.

        Opponents' own tiles are compared in full: we can overbuild one, and we
        can drain a barrel out of one.
        """
        others = tuple(
            (town, t.industry, t.level, t.flipped, t.resources)
            for seat, bucket in enumerate(buckets) if seat != me
            for town, t in bucket
        )
        # Ours matter to them only as link icons, which unflipped tiles do not
        # contribute.
        mine_flipped = tuple((town, t.industry, t.level)
                             for town, t in buckets[me] if t.flipped)
        merchant_beer = tuple(slot.beer for slot in state.merchant_slots())
        return (state.round, state.era, state.rounds_this_era,
                others, mine_flipped, merchant_beer, len(state.links))

    def player_value(self, state, seat: int, context=None, mine=None) -> float:
        data = state.data
        p = state.players[seat]
        value = float(p.vp)
        reachable, accepted, merchant_beer = context or self._sale_context(state)
        contest = self._contest(state)

        # ONE pass over the board. Each term added to this evaluation used to
        # bring its own scan -- tiles, own beer, sellables waiting, brewery beer
        # for the sale check -- four walks of every tile, four times over (once
        # per player). That reached 4,800 board scans per decision and cost most
        # of the evaluation's runtime.
        own = mine if mine is not None else [
            (town, tile) for town, _slot, tile in state.all_tiles()
            if tile.owner == seat
        ]
        own_beer = 0
        waiting = 0
        connected_towns: set = set()
        claimed_towns: set = set()
        for town, tile in own:
            claimed_towns.add(town)
            if town in reachable:
                connected_towns.add(town)
            if tile.industry is Industry.BREWERY and tile.resources > 0:
                own_beer += tile.resources
            if not tile.flipped and tile.industry.is_sellable:
                waiting += 1

        # Beer for a sale may come from a merchant or from a brewery of our own.
        beer_available = merchant_beer or own_beer > 0

        # Tiles: what era scoring would pay right now, plus a discounted promise
        # on the rest. The promise has to include the tile's INCOME, not just its
        # VP -- a coal mine is worth 1 VP and 4 income spaces, so valuing only
        # the VP makes every build look like a waste of money.
        rounds = self.rounds_left(state)
        for town, tile in own:
            spec = data.tile(tile.industry, tile.level)
            if tile.flipped:
                # A level 2+ tile flipped during the Canal Era survives the
                # era-end wipe and scores AGAIN at the end of the Rail Era. So
                # an early flip on a level 2+ tile is worth double, which is
                # most of why experts push to enter rail at 70-80 VP.
                scores_twice = state.era is Era.CANAL and tile.level >= 2
                value += spec.vp * (2 if scores_twice else 1)
                continue

            levels = income_level(p.income_space + spec.income) - p.income
            promise = spec.vp + levels * rounds * self.w["income"]

            # Discount by how long this tile has left to flip before it is
            # either wiped (level 1, at the end of the Canal Era) or the game
            # simply ends.
            left_in_era = max(0, state.rounds_this_era - state.round)
            if state.era is Era.CANAL and tile.level >= 2:
                horizon = left_in_era + state.rounds_this_era  # survives the wipe
            else:
                horizon = left_in_era
            urgency = (min(1.0, horizon / self.w["flip_horizon"])
                       if self.w["flip_horizon"] else 1.0)
            promise *= urgency

            # A sellable tile only pays out through a Sell action, so it is
            # worth what it is worth *if that sale is reachable*. Resource tiles
            # flip on their own as the board consumes them, so they keep the
            # ordinary discount.
            if tile.industry.is_sellable:
                ready = (town in reachable
                         and (tile.industry.value in accepted or "any" in accepted)
                         and beer_available)
                value += promise * (self.w["sell_ready"] if ready
                                    else self.w["unflipped"])
            else:
                value += promise * self.w["unflipped"]

        # Links: icons in adjacent locations, exactly as they would score.
        for link_id, owner in state.links.items():
            if owner == seat:
                for end in data.link_by_id[link_id].ends:
                    value += link_icons_at(state, end)

        # Credit for sites others could have raced us to -- counted ONCE per town.
        #
        # Scoring it per tile paid the bot to pile tiles into the same contested
        # town for a repeated bonus: at weight 0.3 it built 11.9 tiles instead of
        # 10.8, reached the Rail Era on 26.6 VP instead of 33.9, and lost 11.3 VP.
        # The claim is worth something once. A second tile in a town you already
        # hold races nobody, because the town is already yours. (The Canal Era
        # forbids it outright; only the Rail Era allows the stacking.)
        if self.w["site_urgency"]:
            value += sum(contest.get(t, 0)
                         for t in claimed_towns) * self.w["site_urgency"]

        # Merchant access is the gateway to every sale, so it is worth something
        # in its own right, before any particular tile is ready to sell.
        value += len(connected_towns) * self.w["merchant_access"]

        # Beer on our own breweries: each barrel is one more tile a Sell action
        # can flip. Own beer needs no connection, which is what makes it the
        # thing that turns a one-tile sale into a three-tile one.
        # Capped at the number of tiles actually waiting to be sold. Pricing the
        # barrels alone rewarded HOLDING them: breweries rose from 1.9 to 2.8
        # while tiles-per-sell fell from 1.00 to 0.83 and the score dropped 22 VP.
        # Beer is worth what it lets you flip, so it is worth nothing beyond the
        # tiles there are to flip.
        value += min(own_beer, waiting) * self.w["beer_capacity"]

        # What the hand still lets us do. Both weights ship at 0, so this is
        # skipped entirely rather than computed and multiplied away -- it was
        # 261,000 wasted is_wild calls a game.
        if self.w["wild_card"] or self.w["hand_breadth"]:
            wilds = sum(1 for c in p.hand if c.is_wild)
            distinct = len({(c.kind, c.town, c.industries)
                            for c in p.hand if not c.is_wild})
            value += wilds * self.w["wild_card"] + distinct * self.w["hand_breadth"]

        # Money and liquidity both decay to nothing as the game closes: cash you
        # cannot spend is dead weight, and being liquid on the last turn buys
        # you nothing at all.
        spendable = min(1.0, rounds / self.w["money_horizon"]) if self.w["money_horizon"] else 1.0
        per_pound = self.w["money"] + self.w["money_compounding"] * rounds
        value += p.money * per_pound * spendable
        value += self.w["liquidity"] * spendable * (
            1.0 - math.exp(-max(0, p.money) / self.w["liquidity_scale"]))

        value += p.income * rounds * self.w["income"]
        if p.income < 0:
            value += p.income * rounds * self.w["debt"]
        value += p.links_left * self.w["links_held"]

        # What the mat can still produce: the VP of the next tile available in
        # each industry. Developing raises it; building spends it onto the
        # board, where it is credited separately.
        # One lookup per industry, shared with the blocked term below: both used
        # to walk all six independently, 207,000 lowest_level calls a game.
        # Decayed by the same ramp as cash, because it is the same kind of claim:
        # worth something only while there are actions left to spend it. Without
        # the decay the bot pays to improve a mat it can never build from -- it
        # spent its LAST action of a game on a develop worth +0.5 of pure mat
        # potential over passing, and took 1.5 Rail Era develops a game against
        # an expert 0.
        lowest = {i: p.lowest_level(i) for i in Industry}
        for industry, level in lowest.items():
            if level is not None:
                value += (data.tile(industry, level).vp
                          * self.w["mat_potential"] * spendable)

        # Stranded canal-only tiles block an entire industry in the Rail Era.
        if state.era is Era.RAIL:
            for industry, level in lowest.items():
                if level is not None and not data.tile(industry, level).rail_era:
                    value -= self.w["blocked"]

        return value

    @staticmethod
    def rounds_left(state) -> int:
        """Rounds of income still to come, across both eras."""
        this_era = max(0, state.rounds_this_era - state.round)
        return this_era + (state.rounds_this_era if state.era is Era.CANAL else 0)
