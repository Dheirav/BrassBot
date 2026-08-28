"""Rules engine: legal move generation, application, round and era flow.

Two rules here are worth calling out because they are easy to get subtly wrong
and expensive to debug later:

* Building on an undeveloped space is *forced* onto a slot showing only that
  industry's icon when one is free. It is not a choice.
* Flipping a tile pays its owner income immediately, which regularly happens on
  an opponent's turn -- draining their mine is doing them a favour.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .actions import Action, Build, Develop, Loan, Network, Pass, Sale, Sell, Scout
from .cards import Card, CardKind
from .gamedata import Era, Industry, TileSpec
from .network import (
    buildable_lines,
    connected_locations,
    is_connected_to_merchant,
    player_network,
)
from .resources import beer_plans, coal_plans, iron_plans, apply_plan, plan_cost
from .state import HAND_SIZE, GameState, Tile

# End-of-era link scoring: "1 VP for each link icon displayed in adjacent
# locations". Settled from the component art (see docs/link-scoring.md):
#
#   * The link icon lives on the FLIPPED face only. An unflipped tile shows just
#     its level and the cubes to place -- no VP, no income, no link icon. The
#     values printed beside each mat slot belong to the mat, not the tile.
#   * Every merchant location displays 2 link icons, permanently, since merchant
#     spaces are printed on the board and never flip.
#
# This makes flipping doubly valuable: a flipped tile scores its own VP *and*
# turns on the link icons its neighbours' links are counting.
LINK_VP_COUNTS_UNFLIPPED_TILES = False
MERCHANT_LINK_ICONS: dict[str, int] = {
    "shrewsbury": 2, "gloucester": 2, "oxford": 2, "warrington": 2, "nottingham": 2,
}

# Move generation caps. Brass's raw action space explodes on resource sourcing
# and multi-target actions; these bound each family so search stays tractable.
MAX_SOURCING_VARIANTS = 3
MAX_DOUBLE_RAIL = 40
# Pairs grow quadratically in available lines. Double rail is a niche, expensive
# action (15 pounds, two coal, a beer), so it does not deserve a quadratic share
# of move generation -- only this many lines are considered for pairing.
DOUBLE_RAIL_CANDIDATES = 12
MAX_SELL_COMBOS = 24
# Distinct sets of cards a Scout may throw away. Raised from 3: Scout is a rare
# action, so widening it is nearly free in search time, and all three of the old
# sliding windows could discard the one card a plan needed -- which is what an
# agent hit in play.
MAX_SCOUT_VARIANTS = 20
# Triples are drawn from this many most-expendable cards, C(6,3) = 20 of them.
SCOUT_POOL = 6


# --- small helpers ----------------------------------------------------------

def spec_for(state: GameState, tile: Tile) -> TileSpec:
    return state.data.tile(tile.industry, tile.level)


def flip_tile(state: GameState, tile: Tile) -> None:
    """Flip a tile and pay its owner the income printed on it."""
    tile.flipped = True
    state.players[tile.owner].advance_income(spec_for(state, tile).income)


def push_to_market(state: GameState, tile: Tile, town: str) -> None:
    """Move a newly built mine's or iron works' cubes into its market.

    A coal mine only does this if connected to a merchant space; an iron works
    always does. Emptying the tile this way flips it.
    """
    if tile.industry is Industry.COAL_MINE:
        if not is_connected_to_merchant(state, town):
            return
        market, held = state.data.coal, state.coal
        revenue, placed = market.revenue_from_selling(held, tile.resources)
        state.coal += placed
    elif tile.industry is Industry.IRON_WORKS:
        market, held = state.data.iron, state.iron
        revenue, placed = market.revenue_from_selling(held, tile.resources)
        state.iron += placed
    else:
        return

    tile.resources -= placed
    state.players[tile.owner].money += revenue
    if tile.resources == 0:
        flip_tile(state, tile)


def spend(state: GameState, player: int, amount: int) -> None:
    """Money spent goes onto the character tile; it decides next round's turn
    order as well as leaving your purse."""
    p = state.players[player]
    p.money -= amount
    p.spent += amount


def discard(state: GameState, player: int, indices) -> None:
    """Discard cards by hand index. Wild cards go back to their faceup deck."""
    p = state.players[player]
    for idx in sorted(indices, reverse=True):
        card = p.hand.pop(idx)
        if card.kind is CardKind.WILD_LOCATION:
            state.wild_location += 1
        elif card.kind is CardKind.WILD_INDUSTRY:
            state.wild_industry += 1
        else:
            p.discard.append(card)


# --- build targets ----------------------------------------------------------

def _card_build_options(state: GameState, player: int, card: Card):
    """(town, industry) pairs this card permits, ignoring cost and slots."""
    data = state.data
    if card.kind is CardKind.LOCATION:
        # A location card reaches its town even outside your network.
        for industry in Industry:
            yield card.town, industry
    elif card.kind is CardKind.WILD_LOCATION:
        for town_id, town in data.towns.items():
            if town.farm_brewery:
                continue  # wild location cards explicitly exclude the farms
            for industry in Industry:
                yield town_id, industry
    else:
        # Industry cards build inside your own network -- except that with
        # nothing at all on the board you may build anywhere, which the rulebook
        # gives its own heading ("Building if you have no tiles on the board").
        # Without it the opening is far more constrained than the rules allow:
        # every game starts with an empty network, so an industry card was
        # unplayable on turn one.
        network = player_network(state, player)
        industries = card.industries if card.kind is CardKind.INDUSTRY else set(Industry)
        towns = network if network else state.data.towns
        # Sorted because both containers are sets, whose iteration order depends
        # on per-process string hash randomisation. Unsorted, the same seed
        # produced a different game in a different process -- fatal for a bot
        # that is meant to be deterministic, and for any saved move index.
        for town_id in sorted(towns):
            for industry in sorted(industries, key=lambda i: i.name):
                yield town_id, industry


def build_targets(state: GameState, player: int, town: str, industry: Industry, level: int):
    """Yield (slot index, overbuilt tile or None) for a legal placement.

    Placement on an undeveloped space is forced onto a slot showing only this
    industry's icon when one is free.
    """
    town_data = state.data.towns.get(town)
    if town_data is None:
        return

    slots = state.tiles[town]
    empty = [i for i, t in enumerate(slots) if t is None and industry in town_data.slots[i]]
    if empty:
        exclusive = [i for i in empty if town_data.slots[i] == frozenset({industry})]
        for i in (exclusive or empty):
            yield i, None

    # Overbuilding: a higher level tile of the same industry replaces one already
    # placed. Your own may be any industry; an opponent's only coal or iron, and
    # only when none of that resource is left anywhere on the board or market.
    for i, tile in enumerate(slots):
        if tile is None or tile.industry is not industry or level <= tile.level:
            continue
        if tile.owner == player:
            yield i, tile
        elif industry in (Industry.COAL_MINE, Industry.IRON_WORKS):
            if _resource_exhausted(state, industry):
                yield i, tile


def _resource_exhausted(state: GameState, industry: Industry) -> bool:
    market = state.coal if industry is Industry.COAL_MINE else state.iron
    if market > 0:
        return False
    return not any(
        t.industry is industry and t.resources > 0 for _, _, t in state.all_tiles()
    )


def _canal_era_blocked(state: GameState, player: int, town: str, overbuilt: Tile | None) -> bool:
    """In the Canal Era you may hold at most one tile per location."""
    if state.era is not Era.CANAL:
        return False
    for tile in state.tiles[town]:
        if tile is not None and tile.owner == player and tile is not overbuilt:
            return True
    return False


# --- legal moves ------------------------------------------------------------

def _expendability(state: GameState, player: int):
    """Rank hand indices by how willing we should be to spend the card.

    Loan, Develop, Network and Sell all discard a card of your choice, but the
    generators offer a single variant to keep the branching factor down -- so
    whichever card sorts first here is the one the bot gives up. It used to be
    hand[0], i.e. whatever the shuffle happened to put first, which threw away
    the exact location card the plan needed often enough to be noticed in play.
    """
    hand = state.players[player].hand
    counts: dict = {}
    for card in hand:
        key = (card.kind, card.town, card.industries)
        counts[key] = counts.get(key, 0) + 1

    def key(i: int) -> tuple:
        card = hand[i]
        k = (card.kind, card.town, card.industries)
        full = 0
        if card.town is not None:
            slots = state.tiles.get(card.town, ())
            full = 0 if any(t is None for t in slots) else 1
        # ascending sort, so most-expendable first: spend duplicates, then cards
        # naming a town with no space left, and hold wilds until last.
        return (card.is_wild, -counts[k], -full, i)

    return key


def _unique_hand_indices(state: GameState, player: int) -> list[int]:
    """One index per distinct card, most expendable first."""
    seen: set = set()
    out = []
    for i, card in enumerate(state.players[player].hand):
        key = (card.kind, card.town, card.industries)
        if key not in seen:
            seen.add(key)
            out.append(i)
    out.sort(key=_expendability(state, player))
    return out


def legal_builds(state: GameState) -> list[Build]:
    player = state.current.idx
    p = state.players[player]
    out: list[Build] = []
    seen: set = set()

    for card_idx in _unique_hand_indices(state, player):
        card = p.hand[card_idx]
        for town, industry in _card_build_options(state, player, card):
            level = p.lowest_level(industry)
            if level is None:
                continue
            spec = state.data.tile(industry, level)
            if not spec.buildable_in(state.era):
                continue
            for slot, overbuilt in build_targets(state, player, town, industry, level):
                if _canal_era_blocked(state, player, town, overbuilt):
                    continue
                key = (card_idx, town, slot, industry)
                if key in seen:
                    continue
                for coal in coal_plans(state, town, spec.coal_cost, MAX_SOURCING_VARIANTS):
                    for iron in iron_plans(state, spec.iron_cost, MAX_SOURCING_VARIANTS):
                        cost = spec.cost + plan_cost(coal) + plan_cost(iron)
                        if cost <= p.money:
                            out.append(Build(card_idx, town, slot, industry, coal, iron))
                            seen.add(key)
                if spec.coal_cost and not coal_plans(state, town, spec.coal_cost, 1):
                    continue  # no reachable coal at all
    return out


def legal_networks(state: GameState) -> list[Network]:
    player = state.current.idx
    p = state.players[player]
    data = state.data
    out: list[Network] = []
    if p.links_left <= 0:
        return out

    lines = list(buildable_lines(state, player))
    cards = _unique_hand_indices(state, player)
    if not cards:
        return out

    if state.era is Era.CANAL:
        cost = data.constants["canal_link_cost"]
        if p.money >= cost:
            for link in lines:
                out.append(Network(cards[0], (link.id,)))
        return out

    single = data.constants["rail_link_cost"]
    reachable_lines = []  # lines that can source coal on their own
    for link in lines:
        plans = coal_plans(state, list(link.ends), 1, MAX_SOURCING_VARIANTS)
        if plans:
            reachable_lines.append(link)
        for coal in plans:
            if single + plan_cost(coal) <= p.money:
                out.append(Network(cards[0], (link.id,), coal))

    # Two rail links in one action: 15 pounds, one coal each, plus a beer that
    # must be connected to the SECOND link if it comes from an opponent.
    double = data.constants["rail_double_link_cost"]
    if p.links_left >= 2 and p.money >= double:
        # Pairs are drawn only from lines that can already source coal alone.
        # Placing a second link only ever ADDS connections, so a pair of such
        # lines can still reach coal together.
        #
        # Feasibility is checked against the board as it stands rather than a
        # probe with both links placed. Mutating `links` per pair invalidated the
        # connectivity caches every time and cost 88% of this function -- around
        # 43% of the whole node -- for the rarest action in the game. The
        # approximation only ever refuses a legal move (one whose coal or beer is
        # reachable *solely* through the other new link), never invents one, and
        # sits alongside the caps below.
        made = 0
        # Ranked before truncating. C(12,2) is 66 pairs against a cap of 40, and
        # taking the first 40 in enumeration order meant a pair could be dropped
        # purely for sorting late by link id. An agent lost its best rail action
        # that way -- both links were offered singly and paired with worse
        # partners, but the 10 VP pair of the two together never appeared, which
        # is exactly the move the expert line wants and exactly when the board is
        # dense enough for it to matter.
        pairs = list(combinations(reachable_lines[:DOUBLE_RAIL_CANDIDATES], 2))
        pairs.sort(key=lambda ab: -sum(
            link_icons_at(state, end) for link in ab for end in link.ends))
        for a, b in pairs:
            if made >= MAX_DOUBLE_RAIL:
                break
            ends = list(a.ends) + list(b.ends)
            coal = coal_plans(state, ends, 2, 1)
            if not coal or double + plan_cost(coal[0]) > p.money:
                continue
            beer = beer_plans(state, player, list(b.ends), 1, None, 1)
            if beer:
                out.append(Network(cards[0], (a.id, b.id), coal[0], beer[0]))
                made += 1
    return out


def legal_develops(state: GameState) -> list[Develop]:
    player = state.current.idx
    p = state.players[player]
    out: list[Develop] = []
    cards = _unique_hand_indices(state, player)
    if not cards:
        return out

    seen_pairs: set = set()

    def developable() -> list[Industry]:
        result = []
        for industry in Industry:
            level = p.lowest_level(industry)
            if level is not None and state.data.tile(industry, level).can_develop:
                result.append(industry)
        return result

    for first in developable():
        for iron in iron_plans(state, 1, MAX_SOURCING_VARIANTS):
            if plan_cost(iron) <= p.money:
                out.append(Develop(cards[0], (first,), iron))
        # Two tiles in one action, each costing an iron. The second choice
        # depends on the first having gone, so take that tile off the mat, look,
        # and put it back -- a clone here cost more than the rest of the function.
        first_level = p.lowest_level(first)
        p.mat[first][first_level - 1] -= 1
        try:
            seconds = [i for i in Industry
                       if (lv := p.lowest_level(i)) is not None
                       and state.data.tile(i, lv).can_develop]
        finally:
            p.mat[first][first_level - 1] += 1

        for second in seconds:
            pair = tuple(sorted((first, second), key=lambda i: i.value))
            if pair in seen_pairs:
                continue
            for iron in iron_plans(state, 2, MAX_SOURCING_VARIANTS):
                if plan_cost(iron) <= p.money:
                    out.append(Develop(cards[0], pair, iron))
                    seen_pairs.add(pair)
                    break
    return out


def sellable_tiles(state: GameState, player: int):
    """Unflipped sellable tiles with a connected merchant that accepts them."""
    for town, slot, tile in state.all_tiles():
        if tile.owner != player or tile.flipped or not tile.industry.is_sellable:
            continue
        reachable = connected_locations(state, town)
        for mid, slots in state.merchants.items():
            if mid not in reachable:
                continue
            # Every accepting slot, not just the first. A merchant can hold two
            # tiles that both take your goods, each with its own beer barrel and
            # its own bonus, and the rulebook has you choose which one you sell
            # to. Breaking at the first match made the second slot's barrel
            # unreachable for a whole game -- one agent lost every cotton sale
            # to it after the first slot's barrel was spent, and had to spend
            # two extra actions to work around a sale that was legal all along.
            for mslot, merchant in enumerate(slots):
                if merchant.accepts(tile.industry):
                    yield Sale(town, slot, mid, mslot)


def _sale_key(sales) -> tuple:
    """Identity of a sale set, INCLUDING which merchant slot each goes to.

    Keying on (town, slot) alone silently undid the fix in sellable_tiles: that
    now yields one Sale per accepting merchant slot, and this collapsed them
    back together, so a tile sellable at two merchants was still only ever
    offered at the first. The merchants differ by bonus -- Gloucester develops,
    Oxford pays income, Shrewsbury pays VP, Warrington pays cash -- and each
    slot carries its own beer barrel, so they are genuinely different moves.
    """
    return tuple(sorted((s.town, s.slot, s.merchant, s.mslot) for s in sales))


def legal_sells(state: GameState) -> list[Sell]:
    player = state.current.idx
    cards = _unique_hand_indices(state, player)
    if not cards:
        return []

    candidates = list(sellable_tiles(state, player))
    out: list[Sell] = []
    seen: set = set()

    # The maximal sale, built greedily, is always offered. Enumeration below is
    # smallest-first and stops at MAX_SELL_COMBOS, so with five or more sellable
    # tiles every slot filled with one- and two-tile combos and the "flip
    # everything in one action" move -- the whole point of the expert's one-sell
    # -per-era line -- could not be generated at all. That made the bot look
    # like it was choosing to dribble sales out when it was never offered the
    # alternative.
    biggest: list = []
    for sale in candidates:
        trial = biggest + [sale]
        if len({(s.town, s.slot) for s in trial}) != len(trial):
            continue
        if _sell_is_feasible(state, player, tuple(trial)):
            biggest = trial
    if len(biggest) > 1:
        seen.add(_sale_key(biggest))
        out.append(Sell(cards[0], tuple(biggest)))

    for size in range(1, len(candidates) + 1):
        for combo in combinations(candidates, size):
            if len({(s.town, s.slot) for s in combo}) != len(combo):
                continue
            key = _sale_key(combo)
            if key in seen:
                continue
            if _sell_is_feasible(state, player, combo):
                seen.add(key)
                out.append(Sell(cards[0], combo))
            if len(out) >= MAX_SELL_COMBOS:
                return out
    return out


def _sell_is_feasible(state: GameState, player: int, sales) -> bool:
    """Beer is shared across the sales in one action, so feasibility has to be
    checked by simulating the whole sequence."""
    probe = state.clone()
    for sale in sales:
        if not _resolve_sale(probe, player, sale, commit=True):
            return False
    return True


def _resolve_sale(state: GameState, player: int, sale: Sale, commit: bool) -> bool:
    """Flip one tile by selling it. Beer is taken greedily: merchant beer first
    (it carries a bonus), then whatever else is legal."""
    tile = state.tiles[sale.town][sale.slot]
    if tile is None or tile.flipped:
        return False
    spec = spec_for(state, tile)
    need = spec.beer_to_sell or 0
    plans = beer_plans(state, player, sale.town, need, (sale.merchant, sale.mslot), 1)
    if not plans:
        return False
    if not commit:
        return True

    plan = plans[0]
    apply_plan(state, player, plan)
    for draw in plan:
        if draw.is_merchant_beer:
            _merchant_bonus(state, player, draw.merchant)
    flip_tile(state, tile)
    return True


def _merchant_bonus(state: GameState, player: int, merchant_id: str) -> None:
    merchant = state.data.merchants[merchant_id]
    p = state.players[player]
    if merchant.bonus_type == "vp":
        p.vp += merchant.bonus_amount
    elif merchant.bonus_type == "income":
        p.advance_income(merchant.bonus_amount)
    elif merchant.bonus_type == "money":
        p.money += merchant.bonus_amount
    elif merchant.bonus_type == "develop":
        # Free develop of one lowest-level tile, no iron. Lightbulb potteries
        # are still excluded.
        #
        # The rulebook lets you remove a tile of ANY industry, so this takes the
        # one that uncovers the most valuable next tile. Walking Industry in
        # enum order instead always ate a coal mine, since COAL_MINE is first --
        # which is precisely backwards for a player routing a sale through this
        # merchant in order to clear a step off their main industry's track.
        # Prefer a removal that actually uncovers the next level. Removing one
        # of two identical tiles unlocks nothing at all -- an agent watched this
        # eat one of its two coal L2s and gain literally nothing, when clearing
        # its manufacturer L3 would have opened the cheap L4. Among removals
        # that do uncover something, take the most valuable next tile.
        best = None
        for industry in Industry:
            level = p.lowest_level(industry)
            if level is None or not state.data.tile(industry, level).can_develop:
                continue
            uncovers = p.mat[industry][level - 1] == 1
            gain = 0
            if uncovers:
                try:
                    gain = state.data.tile(industry, level + 1).vp
                except Exception:
                    gain = 0
            # Ties break on enum order, so the choice stays deterministic.
            rank = (uncovers, gain)
            if best is None or rank > best[0]:
                best = (rank, industry, level)
        if best is not None:
            _rank, industry, level = best
            p.mat[industry][level - 1] -= 1


def legal_loans(state: GameState) -> list[Loan]:
    p = state.current
    cards = _unique_hand_indices(state, p.idx)
    if not cards:
        return []
    penalty = state.data.constants["loan_income_penalty_levels"]
    if p.income - penalty < state.data.constants["min_income_level"]:
        return []
    return [Loan(cards[0])]


def legal_scouts(state: GameState) -> list[Scout]:
    p = state.current
    if len(p.hand) < 3 or state.wild_location < 1 or state.wild_industry < 1:
        return []
    if any(c.is_wild for c in p.hand):
        return []  # cannot Scout while already holding a wild
    # Which three cards you give up is a real decision -- an expert scouts away
    # duplicates and cards for sites already taken, and holds the ones naming a
    # location they still want. Offering a single arbitrary triple made Scout a
    # move the bot could not use well, and it scouted 0.2 times a game.
    #
    # Cards are ranked cheapest-first: duplicates in hand are the cheapest thing
    # to spend, then location cards whose town has no slot left.
    order = sorted(range(len(p.hand)), key=_expendability(state, p.idx))
    # Every triple among the most expendable few, rather than three sliding
    # windows over them. The windows could only ever offer consecutive runs of
    # the ranking, so a card ranked mid-table was in all of them or none.
    out = []
    for pick in combinations(order[:SCOUT_POOL], 3):
        out.append(Scout(pick[0], (pick[1], pick[2])))
        if len(out) >= MAX_SCOUT_VARIANTS:
            break
    return out


def legal_actions(state: GameState) -> list[Action]:
    if state.finished:
        return []
    out: list[Action] = []
    out += legal_builds(state)
    out += legal_networks(state)
    out += legal_develops(state)
    out += legal_sells(state)
    out += legal_loans(state)
    out += legal_scouts(state)
    # Passing is always available, but still costs a card.
    cards = _unique_hand_indices(state, state.current.idx)
    if cards:
        out.append(Pass(cards[0]))
    return out


# --- applying ---------------------------------------------------------------

def apply_action(state: GameState, action: Action) -> None:
    player = state.current.idx
    p = state.players[player]

    if isinstance(action, Build):
        _apply_build(state, player, action)
    elif isinstance(action, Network):
        _apply_network(state, player, action)
    elif isinstance(action, Develop):
        discard(state, player, [action.card])
        spend(state, player, apply_plan(state, player, action.iron))
        for industry in action.industries:
            level = p.lowest_level(industry)
            if level is not None:
                p.mat[industry][level - 1] -= 1
    elif isinstance(action, Sell):
        discard(state, player, [action.card])
        for sale in action.sales:
            _resolve_sale(state, player, sale, commit=True)
    elif isinstance(action, Loan):
        discard(state, player, [action.card])
        p.money += state.data.constants["loan_amount"]
        p.lose_income_levels(state.data.constants["loan_income_penalty_levels"])
    elif isinstance(action, Scout):
        discard(state, player, [action.card, *action.extra])
        from .cards import WILD_INDUSTRY, WILD_LOCATION
        p.hand.append(WILD_LOCATION)
        p.hand.append(WILD_INDUSTRY)
        state.wild_location -= 1
        state.wild_industry -= 1
    elif isinstance(action, Pass):
        discard(state, player, [action.card])
    else:  # pragma: no cover
        raise AssertionError(f"unknown action {action!r}")

    state.actions_left -= 1
    if state.actions_left == 0:
        _end_turn(state)


def _apply_build(state: GameState, player: int, action: Build) -> None:
    p = state.players[player]
    level = p.lowest_level(action.industry)
    spec = state.data.tile(action.industry, level)

    discard(state, player, [action.card])
    spend(state, player, spec.cost)
    spend(state, player, apply_plan(state, player, action.coal))
    spend(state, player, apply_plan(state, player, action.iron))

    # An overbuilt tile leaves the game entirely; its owner keeps whatever VP
    # and income it already earned.
    if state.tiles[action.town][action.slot] is not None:
        state.tiles[action.town][action.slot] = None

    p.mat[action.industry][level - 1] -= 1
    tile = Tile(owner=player, industry=action.industry, level=level, era_built=state.era)
    if action.industry is Industry.BREWERY:
        tile.resources = spec.beer_produced(state.era)
    else:
        tile.resources = spec.resource_produced
    state.tiles[action.town][action.slot] = tile

    push_to_market(state, tile, action.town)


def _apply_network(state: GameState, player: int, action: Network) -> None:
    p = state.players[player]
    data = state.data
    discard(state, player, [action.card])

    if state.era is Era.CANAL:
        spend(state, player, data.constants["canal_link_cost"])
    elif len(action.lines) == 1:
        spend(state, player, data.constants["rail_link_cost"])
    else:
        spend(state, player, data.constants["rail_double_link_cost"])

    for line in action.lines:
        state.links[line] = player
        p.links_left -= 1

    spend(state, player, apply_plan(state, player, action.coal))
    apply_plan(state, player, action.beer)


# --- turn, round and era flow ----------------------------------------------

def _end_turn(state: GameState) -> None:
    p = state.current
    while len(p.hand) < HAND_SIZE and state.deck:
        p.hand.append(state.deck.pop())
    state.turn_pos += 1
    _advance_to_next_actor(state)


def _advance_to_next_actor(state: GameState) -> None:
    """Hand the turn to the next player who can actually act.

    Once the draw deck is exhausted hands shrink, so a player may have only one
    card left -- and so only one action -- or none at all, in which case they are
    skipped entirely. The first round of the Canal Era is a single action.
    """
    while not state.finished:
        if state.turn_pos >= state.n_players:
            _end_round(state)
            continue  # _end_round resets the position, or finishes the game
        limit = 1 if (state.era is Era.CANAL and state.round == 1) else 2
        state.actions_left = min(limit, len(state.current.hand))
        if state.actions_left > 0:
            return
        state.turn_pos += 1


def _end_round(state: GameState) -> None:
    final_round = state.round >= state.rounds_this_era

    # Turn order: least spent goes first, ties keep their relative order.
    order = sorted(state.turn_order, key=lambda i: state.players[i].spent)
    for p in state.players:
        p.spent = 0

    if not (final_round and state.era is Era.RAIL):
        for p in state.players:
            _collect_income(state, p)

    if final_round:
        _end_era(state)
        return

    state.turn_order = order
    state.turn_pos = 0
    state.round += 1


def _collect_income(state: GameState, p) -> None:
    """Pay or collect income. Negative income can force tile sales, and if even
    that is not enough, costs a VP per pound still owed."""
    amount = p.income
    if amount >= 0:
        p.money += amount
        return

    owed = -amount
    if p.money >= owed:
        p.money -= owed
        return
    owed -= p.money
    p.money = 0

    # Sell industry tiles for half their cost, rounded down, stopping as soon as
    # the debt is covered; any excess is kept. Which tiles is a player choice --
    # cheapest-first is a stand-in until the bot chooses deliberately.
    owned = sorted(
        ((town, slot, tile) for town, slot, tile in state.all_tiles() if tile.owner == p.idx),
        key=lambda x: spec_for(state, x[2]).cost // 2,
    )
    for town, slot, tile in owned:
        if owed <= 0:
            break
        gain = spec_for(state, tile).cost // 2
        state.tiles[town][slot] = None
        if gain >= owed:
            p.money += gain - owed
            owed = 0
        else:
            owed -= gain

    if owed > 0:
        lost = min(p.vp, owed)
        p.vp -= lost
        p.vp_penalties += lost


def link_icons_at(state: GameState, location: str) -> int:
    # data.merchants, not state.merchants: the icons are printed on the board at
    # the location and are there whether or not this player count puts a tile on
    # it -- see docs/link-scoring.md, settled from photographs of the components.
    # Keying on the filtered dict scored derby-nottingham and
    # stoke_on_trent-warrington as 0 instead of 2 at low player counts.
    if location in state.data.merchants:
        return MERCHANT_LINK_ICONS.get(location, 0)
    total = 0
    for tile in state.tiles.get(location, ()):
        if tile is None:
            continue
        if LINK_VP_COUNTS_UNFLIPPED_TILES or tile.flipped:
            total += spec_for(state, tile).link_vp
    return total


@dataclass(frozen=True, slots=True)
class EraScoring:
    """What each player got out of one era's scoring, and what they left on the
    table. Purely a record -- the rules never read it back."""

    era: Era
    link_vp: tuple[int, ...]
    industry_vp: tuple[int, ...]
    links_scored: tuple[int, ...]
    tiles_flipped: tuple[int, ...]
    tiles_stranded: tuple[int, ...]  # built, never flipped, scored nothing


def score_era(state: GameState) -> EraScoring:
    """Score links, then flipped tiles. Links are removed as they score."""
    n = state.n_players
    link_vp = [0] * n
    industry_vp = [0] * n
    links_scored = [0] * n
    flipped = [0] * n
    stranded = [0] * n

    for link in state.data.links:
        owner = state.links.get(link.id)
        if owner is None:
            continue
        gained = sum(link_icons_at(state, end) for end in link.ends)
        state.players[owner].vp += gained
        state.players[owner].links_left += 1
        link_vp[owner] += gained
        links_scored[owner] += 1
    state.links.clear()

    for _town, _slot, tile in state.all_tiles():
        if tile.flipped:
            gained = spec_for(state, tile).vp
            state.players[tile.owner].vp += gained
            industry_vp[tile.owner] += gained
            flipped[tile.owner] += 1
        else:
            stranded[tile.owner] += 1

    record = EraScoring(state.era, tuple(link_vp), tuple(industry_vp),
                        tuple(links_scored), tuple(flipped), tuple(stranded))
    state.era_scores.append(record)
    return record


def _end_era(state: GameState) -> None:
    score_era(state)

    if state.era is Era.RAIL:
        # Money is NOT victory points in Brass: Birmingham. The rulebook is
        # explicit: after Rail Era scoring the most VP wins, and money is only
        # the *second* tiebreak, after income. Leftover cash is dead weight.
        state.finished = True
        return

    # Canal era teardown.
    for town, slots in state.tiles.items():
        for i, tile in enumerate(slots):
            if tile is not None and tile.level == 1:
                slots[i] = None

    for merchant in state.merchant_slots():
        if merchant.kind != "blank":
            merchant.beer = 1

    deck: list[Card] = []
    for p in state.players:
        deck += p.discard
        p.discard = []
        # Wilds go back to their faceup decks, exactly as discard() does. They
        # used to be dropped here and the counters never incremented, so every
        # wild held across the boundary vanished from the game permanently --
        # and since Scout needs both piles non-empty, enough leaks make Scout
        # illegal for everyone for the rest of the game.
        for card in p.hand:
            if card.kind is CardKind.WILD_LOCATION:
                state.wild_location += 1
            elif card.kind is CardKind.WILD_INDUSTRY:
                state.wild_industry += 1
            else:
                deck.append(card)
        p.hand = []
    state.rng.shuffle(deck)
    state.deck = deck

    for p in state.players:
        p.hand = [state.deck.pop() for _ in range(min(HAND_SIZE, len(state.deck)))]

    state.era = Era.RAIL
    state.round = 1
    state.turn_pos = 0


def final_scores(state: GameState) -> list[int]:
    return [p.vp for p in state.players]


def final_standings(state: GameState) -> list[int]:
    """Seats best to worst. Ties break on VP, then income, then money."""
    return sorted(
        range(state.n_players),
        key=lambda i: (-state.players[i].vp, -state.players[i].income,
                       -state.players[i].money),
    )


def winners(state: GameState) -> list[int]:
    """Seats sharing first place. More than one is a genuine draw -- the rules
    exhaust their tiebreaks and let those players share the win."""
    best = max((p.vp, p.income, p.money) for p in state.players)
    return [i for i, p in enumerate(state.players)
            if (p.vp, p.income, p.money) == best]
