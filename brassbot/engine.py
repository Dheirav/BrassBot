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
        # Industry cards build only inside your own network.
        network = player_network(state, player)
        industries = card.industries if card.kind is CardKind.INDUSTRY else set(Industry)
        for town_id in network:
            for industry in industries:
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

def _unique_hand_indices(state: GameState, player: int) -> list[int]:
    """One index per distinct card: identical cards give identical actions."""
    seen: set = set()
    out = []
    for i, card in enumerate(state.players[player].hand):
        key = (card.kind, card.town, card.industries)
        if key not in seen:
            seen.add(key)
            out.append(i)
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
    for link in lines:
        for coal in coal_plans(state, list(link.ends), 1, MAX_SOURCING_VARIANTS):
            if single + plan_cost(coal) <= p.money:
                out.append(Network(cards[0], (link.id,), coal))

    # Two rail links in one action: 15 pounds, one coal each, plus a beer that
    # must be connected to the SECOND link if it comes from an opponent.
    double = data.constants["rail_double_link_cost"]
    if p.links_left >= 2 and p.money >= double:
        # Both links must be on the board before coal and beer are checked, so
        # this needs a probe. One clone serves every pair: place, test, retract.
        probe = state.clone()
        made = 0
        for a, b in combinations(lines[:DOUBLE_RAIL_CANDIDATES], 2):
            if made >= MAX_DOUBLE_RAIL:
                break
            probe.links[a.id] = player
            probe.links[b.id] = player
            try:
                coal = coal_plans(probe, list(a.ends) + list(b.ends), 2, 1)
                beer = beer_plans(probe, player, list(b.ends), 1, None, 1)
            finally:
                del probe.links[a.id]
                del probe.links[b.id]
            if coal and beer and double + plan_cost(coal[0]) <= p.money:
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
        # depends on the first, so probe a clone.
        probe = state.clone()
        probe.players[player].mat[first][probe.players[player].lowest_level(first) - 1] -= 1
        for second in [i for i in Industry
                       if (lv := probe.players[player].lowest_level(i)) is not None
                       and state.data.tile(i, lv).can_develop]:
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
            for mslot, merchant in enumerate(slots):
                if merchant.accepts(tile.industry):
                    yield Sale(town, slot, mid, mslot)
                    break


def legal_sells(state: GameState) -> list[Sell]:
    player = state.current.idx
    cards = _unique_hand_indices(state, player)
    if not cards:
        return []

    candidates = list(sellable_tiles(state, player))
    out: list[Sell] = []
    for size in range(1, len(candidates) + 1):
        for combo in combinations(candidates, size):
            if len({(s.town, s.slot) for s in combo}) != len(combo):
                continue
            if _sell_is_feasible(state, player, combo):
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
        for industry in Industry:
            level = p.lowest_level(industry)
            if level is not None and state.data.tile(industry, level).can_develop:
                p.mat[industry][level - 1] -= 1
                break


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
    idx = _unique_hand_indices(state, p.idx)
    if len(idx) < 3:
        idx = list(range(len(p.hand)))
    return [Scout(idx[0], (idx[1], idx[2]))]


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
    if location in state.merchants:
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
        deck += [c for c in p.hand if not c.is_wild]
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
