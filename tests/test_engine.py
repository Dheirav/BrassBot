"""Engine rules, exercised on constructed positions.

Playouts prove the engine terminates; these prove it is *right*. Each test sets
up the smallest position that isolates one rule.
"""

import pytest

from brassbot.actions import Build, Loan, Sale, Scout, Sell
from brassbot.cards import WILD_INDUSTRY, Card, CardKind
from brassbot.network import is_connected_to_merchant
from brassbot.engine import (
    apply_action,
    legal_actions,
    legal_builds,
    legal_scouts,
    legal_sells,
    link_icons_at,
    score_era,
    _end_era,
)
from brassbot.gamedata import Era, Industry, income_level
from brassbot.resources import beer_plans, coal_plans, iron_plans
from brassbot.state import Tile, new_game


def place(state, town, slot, owner, industry, level, *, flipped=False,
          resources=None, era=Era.CANAL):
    spec = state.data.tile(industry, level)
    if resources is None:
        resources = (spec.beer_produced(era) if industry is Industry.BREWERY
                     else spec.resource_produced)
    tile = Tile(owner=owner, industry=industry, level=level, era_built=era,
                flipped=flipped, resources=resources)
    state.tiles[town][slot] = tile
    return tile


def only_card(state, player, card):
    """Give a player a single known card, so generated actions are predictable."""
    state.players[player].hand = [card]


@pytest.fixture
def game():
    return new_game(4, seed=7)


# --- building ---------------------------------------------------------------

def test_iron_works_pushes_cubes_to_market_on_build(game):
    """An iron works sells into its market regardless of connection."""
    game.iron = 4  # plenty of room in the market
    player = game.current.idx
    game.players[player].money = 50
    # An iron works costs a coal; a mine in the same location is at distance 0.
    place(game, "coalbrookdale", 2, 1, Industry.COAL_MINE, 2)
    only_card(game, player, Card(CardKind.LOCATION, town="coalbrookdale"))

    builds = [b for b in legal_builds(game) if b.industry is Industry.IRON_WORKS]
    assert builds, "iron works should be buildable"
    before = game.players[player].money
    apply_action(game, builds[0])

    tile = game.tiles["coalbrookdale"][builds[0].slot]
    spec = game.data.tile(Industry.IRON_WORKS, 1)
    # 4 cubes produced, 6 market spaces free -> all 4 go, tile flips.
    assert game.iron == 8
    assert tile.resources == 0 and tile.flipped
    assert game.players[player].money > before - spec.cost  # market paid out


def test_coal_mine_only_reaches_the_market_when_connected_to_one(game):
    player = game.current.idx
    game.players[player].money = 50
    game.coal = 6
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))

    builds = [b for b in legal_builds(game) if b.industry is Industry.COAL_MINE]
    apply_action(game, builds[0])
    tile = game.tiles["dudley"][builds[0].slot]
    # No links anywhere, so no merchant connection: cubes stay on the tile.
    assert tile.resources == game.data.tile(Industry.COAL_MINE, 1).resource_produced
    assert not tile.flipped
    assert game.coal == 6


def test_build_is_forced_onto_a_slot_showing_only_that_industry(game):
    """Placement on an undeveloped space is not a free choice."""
    player = game.current.idx
    game.players[player].money = 50
    for town_id, town in game.data.towns.items():
        exclusive = [i for i, s in enumerate(town.slots)
                     if s == frozenset({Industry.COAL_MINE})]
        shared = [i for i, s in enumerate(town.slots)
                  if Industry.COAL_MINE in s and len(s) > 1]
        if exclusive and shared:
            only_card(game, player, Card(CardKind.LOCATION, town=town_id))
            slots = {b.slot for b in legal_builds(game)
                     if b.industry is Industry.COAL_MINE}
            assert slots <= set(exclusive), (
                f"{town_id}: must use the coal-only slot while one is free")
            return
    pytest.skip("no town with both an exclusive and a shared coal slot")


def test_canal_era_allows_only_one_tile_per_location(game):
    player = game.current.idx
    game.players[player].money = 60
    place(game, "dudley", 0, player, Industry.COAL_MINE, 1)
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))
    assert not [b for b in legal_builds(game) if b.town == "dudley"]


def test_rail_era_allows_several_tiles_per_location(game):
    player = game.current.idx
    game.era = Era.RAIL
    p = game.players[player]
    p.money = 60
    # Level 1 tiles are canal-only, so the Rail Era can only reach level 2+.
    p.mat[Industry.IRON_WORKS][0] = 0
    place(game, "dudley", 0, player, Industry.COAL_MINE, 2)  # own tile, and coal source
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))
    assert [b for b in legal_builds(game) if b.town == "dudley"]


def test_wild_location_card_cannot_reach_a_farm_brewery(game):
    player = game.current.idx
    game.players[player].money = 60
    only_card(game, player, Card(CardKind.WILD_LOCATION))
    assert not [b for b in legal_builds(game) if b.town.startswith("farm_")]


def test_industry_card_builds_only_inside_your_network(game):
    """Once you have anything on the board, an industry card is restricted to
    your network.

    This test used to assert the opposite of the rule for the empty-network case
    -- "empty network means nowhere to build" -- which is how the missing
    exception survived: the bug was pinned by a test rather than caught by one.
    The correct empty-board behaviour is covered by the test below.
    """
    player = game.current.idx
    game.players[player].money = 60
    only_card(game, player, Card(CardKind.INDUSTRY,
                                 industries=frozenset({Industry.COAL_MINE})))

    place(game, "dudley", 1, player, Industry.IRON_WORKS, 2)  # puts dudley in my network
    game.era = Era.RAIL  # sidestep the canal one-per-location rule
    game.players[player].mat[Industry.COAL_MINE][0] = 0  # level 1 is canal-only
    towns = {b.town for b in legal_builds(game)}
    assert towns == {"dudley"}


# --- resources --------------------------------------------------------------

def test_coal_comes_from_the_nearest_connected_mine(game):
    place(game, "dudley", 0, 1, Industry.COAL_MINE, 2)
    place(game, "coalbrookdale", 0, 2, Industry.COAL_MINE, 2)
    game.links["birmingham-dudley"] = 0
    game.links["dudley-kidderminster"] = 0
    game.links["coalbrookdale-kidderminster"] = 0

    plans = coal_plans(game, "birmingham", 1)
    assert {d.town for plan in plans for d in plan} == {"dudley"}, "dudley is closer"


def test_market_coal_needs_a_merchant_connection(game):
    # An isolated location cannot reach the market at all.
    assert coal_plans(game, "dudley", 1) == []
    game.links["birmingham-oxford"] = 0
    game.links["birmingham-dudley"] = 0
    plans = coal_plans(game, "dudley", 1)
    assert plans and plans[0][0].kind == "market"


def test_iron_ignores_the_network_entirely(game):
    """No links anywhere, yet iron is still obtainable."""
    plans = iron_plans(game, 1)
    assert plans and plans[0][0].kind == "market"

    place(game, "coalbrookdale", 0, 3, Industry.IRON_WORKS, 1)
    plans = iron_plans(game, 1)
    assert all(d.kind == "tile" for plan in plans for d in plan)


def test_own_breweries_need_no_connection_but_opponents_do(game):
    place(game, "leek", 0, 0, Industry.BREWERY, 1)  # mine, far away, unconnected
    assert beer_plans(game, 0, "birmingham", 1)
    assert not beer_plans(game, 1, "birmingham", 1), "opponent's brewery is unreachable"


def test_draining_a_tile_flips_it_and_pays_its_owner(game):
    """Consuming an opponent's coal hands them income -- on your turn."""
    mine = place(game, "dudley", 0, 1, Industry.COAL_MINE, 1, resources=1)
    game.links["birmingham-dudley"] = 0
    before = game.players[1].income_space

    from brassbot.resources import apply_plan
    plan = coal_plans(game, "birmingham", 1)[0]
    apply_plan(game, 0, plan)

    assert mine.flipped and mine.resources == 0
    gained = game.players[1].income_space - before
    assert gained == game.data.tile(Industry.COAL_MINE, 1).income


# --- selling ----------------------------------------------------------------

def _connect_to_merchant(state, town, merchant_link):
    state.links[merchant_link] = 0


def test_sell_flips_the_tile_and_advances_income(game):
    player = game.current.idx
    tile = place(game, "birmingham", 0, player, Industry.COTTON_MILL, 1)
    place(game, "leek", 0, player, Industry.BREWERY, 1)  # own beer, no connection needed
    game.links["birmingham-oxford"] = player
    game.merchants["oxford"][0].kind = Industry.COTTON_MILL.value
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))

    sells = legal_sells(game)
    assert sells, "a connected, accepting merchant plus beer should allow a sale"
    before = game.players[player].income_space
    apply_action(game, sells[0])

    assert tile.flipped
    assert game.players[player].income_space - before >= (
        game.data.tile(Industry.COTTON_MILL, 1).income)


def test_sell_requires_a_merchant_that_accepts_the_good(game):
    player = game.current.idx
    place(game, "birmingham", 0, player, Industry.COTTON_MILL, 1)
    place(game, "leek", 0, player, Industry.BREWERY, 1)
    game.links["birmingham-oxford"] = player
    for slot in game.merchants["oxford"]:
        slot.kind = Industry.POTTERY.value  # wrong good
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))
    assert not legal_sells(game)


def test_sell_is_impossible_without_beer(game):
    player = game.current.idx
    place(game, "birmingham", 0, player, Industry.COTTON_MILL, 1)
    game.links["birmingham-oxford"] = player
    game.merchants["oxford"][0].kind = Industry.COTTON_MILL.value
    game.merchants["oxford"][0].beer = 0
    game.merchants["oxford"][1].beer = 0
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))
    assert not legal_sells(game)


def test_merchant_beer_pays_its_bonus(game):
    """Oxford's merchant beer advances income by 2 on top of the sale."""
    player = game.current.idx
    place(game, "birmingham", 0, player, Industry.COTTON_MILL, 1)
    game.links["birmingham-oxford"] = player
    game.merchants["oxford"][0].kind = Industry.COTTON_MILL.value
    game.merchants["oxford"][0].beer = 1
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))

    before = game.players[player].income_space
    sells = legal_sells(game)
    assert sells
    apply_action(game, sells[0])
    tile_income = game.data.tile(Industry.COTTON_MILL, 1).income
    assert game.players[player].income_space - before == tile_income + 2
    assert game.merchants["oxford"][0].beer == 0


# --- other actions ----------------------------------------------------------

def test_loan_pays_thirty_and_costs_three_income_levels(game):
    player = game.current.idx
    p = game.players[player]
    only_card(game, player, Card(CardKind.LOCATION, town="dudley"))
    before_level = p.income
    before_money = p.money
    apply_action(game, Loan(0))
    assert p.money == before_money + 30
    assert p.income == before_level - 3


def test_loan_is_illegal_below_minus_ten(game):
    p = game.current
    p.income_space = 1  # level -9; another loan would reach -12
    only_card(game, p.idx, Card(CardKind.LOCATION, town="dudley"))
    assert not [a for a in legal_actions(game) if isinstance(a, Loan)]


def test_scout_is_illegal_while_holding_a_wild(game):
    p = game.current
    p.hand = [WILD_INDUSTRY,
              Card(CardKind.LOCATION, town="dudley"),
              Card(CardKind.LOCATION, town="leek")]
    assert not legal_scouts(game)


def test_scout_takes_one_of_each_wild_for_three_cards(game):
    p = game.current
    p.hand = [Card(CardKind.LOCATION, town="dudley"),
              Card(CardKind.LOCATION, town="leek"),
              Card(CardKind.LOCATION, town="derby")]
    scouts = legal_scouts(game)
    assert scouts
    apply_action(game, scouts[0])
    assert sum(1 for c in p.hand if c.is_wild) == 2
    assert game.wild_location == 3 and game.wild_industry == 3


# --- era end ----------------------------------------------------------------

def test_link_scoring_counts_flipped_tiles_regardless_of_owner(game):
    """The icon is on the flipped face, so only flipped tiles light up a link --
    but whose tiles they are does not matter."""
    game.links["birmingham-dudley"] = 0
    place(game, "birmingham", 0, 1, Industry.COTTON_MILL, 1, flipped=True)
    place(game, "dudley", 0, 2, Industry.COAL_MINE, 1, flipped=True)
    expected = (game.data.tile(Industry.COTTON_MILL, 1).link_vp
                + game.data.tile(Industry.COAL_MINE, 1).link_vp)
    assert link_icons_at(game, "birmingham") + link_icons_at(game, "dudley") == expected

    score_era(game)
    assert game.players[0].vp == expected


def test_unflipped_tiles_do_not_light_up_a_link(game):
    game.links["birmingham-dudley"] = 0
    place(game, "birmingham", 0, 1, Industry.COTTON_MILL, 1, flipped=False)
    score_era(game)
    assert game.players[0].vp == 0


def test_every_merchant_shows_two_link_icons(game):
    """Merchant spaces are printed on the board and never flip, so a link to one
    is worth a guaranteed 2 VP."""
    for merchant_id in game.data.merchants:
        assert link_icons_at(game, merchant_id) == 2

    game.links["birmingham-oxford"] = 0
    score_era(game)
    assert game.players[0].vp == 2  # birmingham is empty; oxford supplies both


def test_only_flipped_tiles_score_their_vp(game):
    place(game, "birmingham", 0, 0, Industry.COTTON_MILL, 1, flipped=True)
    place(game, "dudley", 0, 0, Industry.COTTON_MILL, 1, flipped=False)
    score_era(game)
    assert game.players[0].vp == game.data.tile(Industry.COTTON_MILL, 1).vp


def test_canal_era_end_removes_level_one_tiles_and_every_link(game):
    place(game, "birmingham", 0, 0, Industry.COTTON_MILL, 1, flipped=True)
    place(game, "dudley", 0, 0, Industry.COAL_MINE, 2)
    game.links["birmingham-dudley"] = 0

    _end_era(game)

    assert game.era is Era.RAIL
    assert game.links == {}
    assert game.tiles["birmingham"][0] is None, "level 1 tiles are removed"
    assert game.tiles["dudley"][0] is not None, "level 2+ tiles remain"
    assert all(len(p.hand) == 8 for p in game.players)


def test_canal_era_end_refills_merchant_beer(game):
    for slot in game.merchant_slots():
        slot.beer = 0
    _end_era(game)
    for slot in game.merchant_slots():
        assert slot.beer == (0 if slot.kind == "blank" else 1)


def test_money_is_not_victory_points(game):
    """Brass: Birmingham has NO money-to-VP conversion. The rulebook says the
    most VP wins and money is only the *second* tiebreak, after income.

    This was implemented wrongly once -- leftover cash was scored at a point per
    ten pounds, which made loan-farming look profitable and inflated every
    measured score. Pinned so it cannot come back.
    """
    game.era = Era.RAIL
    p = game.players[0]
    p.money = 500
    p.vp = 10
    _end_era(game)
    assert p.vp == 10, "leftover money must score nothing"


def test_money_breaks_ties_but_only_after_income(game):
    from brassbot.engine import winners
    for p in game.players:
        p.vp, p.income_space, p.money = 50, 20, 0
    game.players[1].money = 99          # richest, same VP and income
    assert winners(game) == [1]

    game.players[2].income_space = 30   # income outranks money
    assert winners(game) == [2]


def test_links_return_to_their_owner_after_scoring(game):
    p = game.players[0]
    game.links["birmingham-dudley"] = 0
    p.links_left -= 1
    before = p.links_left
    score_era(game)
    assert p.links_left == before + 1


# --- income -----------------------------------------------------------------

def test_negative_income_sells_tiles_only_until_the_debt_is_covered(game):
    from brassbot.engine import _collect_income
    p = game.players[0]
    p.income_space = 4  # level -6
    p.money = 0
    place(game, "birmingham", 0, 0, Industry.COTTON_MILL, 1)  # cost 12 -> 6
    place(game, "dudley", 0, 0, Industry.COTTON_MILL, 1)

    _collect_income(game, p)

    remaining = [t for _, _, t in game.all_tiles() if t.owner == 0]
    assert len(remaining) == 1, "must stop as soon as the debt is covered"
    assert p.money == 0
    assert p.vp == 0


def test_unpayable_income_costs_a_vp_per_pound(game):
    from brassbot.engine import _collect_income
    p = game.players[0]
    p.income_space = 4  # level -6
    p.money = 2
    p.vp = 10
    _collect_income(game, p)
    assert p.money == 0
    assert p.vp == 10 - 4


def test_an_industry_card_builds_anywhere_when_you_have_nothing_on_the_board(game):
    """Rulebook, "Building if you have no tiles on the board": with no industry
    or link tiles placed, an industry card may build in ANY location with a
    matching undeveloped space, not only inside your (empty) network.

    Every game opens in exactly this position, so omitting it silently narrowed
    the first move of every game ever played by this engine.
    """
    player = game.current.idx
    game.players[player].money = 60
    only_card(game, player, Card(CardKind.INDUSTRY,
                                 industries=frozenset({Industry.COAL_MINE})))
    towns = {b.town for b in legal_builds(game)}
    assert len(towns) > 1, "an empty network must not restrict where you may build"

    # once something is on the board, the ordinary network rule applies again
    place(game, "dudley", 0, player, Industry.COAL_MINE, 1)
    game.era = Era.RAIL
    game.players[player].mat[Industry.COAL_MINE][0] = 0
    assert {b.town for b in legal_builds(game)} == {"dudley"}


def test_wild_cards_return_to_their_decks_at_the_era_boundary(game):
    """A wild held across the Canal/Rail boundary used to vanish from the game.

    Scout needs both wild piles non-empty, so leaked wilds eventually make Scout
    illegal for every player for the rest of the game.
    """
    before_loc, before_ind = game.wild_location, game.wild_industry
    game.players[0].hand = [Card(CardKind.WILD_LOCATION),
                            Card(CardKind.WILD_INDUSTRY)]
    _end_era(game)
    assert game.wild_location == before_loc + 1
    assert game.wild_industry == before_ind + 1


def test_the_largest_possible_sale_is_always_offered(game):
    """Enumeration is smallest-first and capped, so without an explicit maximal
    candidate the one-action multi-flip is unreachable exactly when it matters."""
    player = game.current.idx
    p = game.players[player]
    p.money = 200
    only_card(game, player, Card(CardKind.LOCATION, town="birmingham"))
    towns = ["birmingham", "coventry", "dudley", "walsall", "wolverhampton"]
    for i, town in enumerate(towns):
        place(game, town, 0, player, Industry.MANUFACTURER, 2)
        place(game, town, 1, player, Industry.BREWERY, 2)
    for _t, _s, tile in game.all_tiles():
        if tile.industry is Industry.BREWERY:
            tile.resources = 4
    sells = legal_sells(game)
    if sells:
        assert max(len(s.sales) for s in sells) > 2, (
            "only small sales offered; the maximal combination is unreachable"
        )


@pytest.mark.parametrize("players", [2, 3, 4])
def test_merchant_spaces_count_even_without_a_merchant_tile(players):
    """Warrington (2p) and Nottingham (2-3p) hold no merchant tile, but the
    space is still on the board.

    The rulebook: a coal mine sells when "connected to any Merchant space (even
    those without Merchant tiles)", and the coal-purchase icons are printed at
    Warrington and Nottingham. The link icons are printed on the location too,
    so they score regardless of the player count.
    """
    game = new_game(players, seed=1)
    for merchant in ("warrington", "nottingham"):
        assert link_icons_at(game, merchant) == 2, (
            f"{merchant} should show its printed 2 link icons at {players}p"
        )
    # A town joined only to Nottingham can still reach the coal market.
    game.links["derby-nottingham"] = 0
    assert is_connected_to_merchant(game, "derby")


def test_a_tile_sellable_at_two_merchants_is_offered_at_both(game):
    """sellable_tiles yields one Sale per accepting slot; legal_sells must not
    collapse them again. The merchants differ by bonus and each slot carries its
    own beer, so they are different moves, not duplicates."""
    player = game.current.idx
    game.players[player].money = 200
    only_card(game, player, Card(CardKind.LOCATION, town="birmingham"))
    place(game, "birmingham", 0, player, Industry.MANUFACTURER, 2)
    place(game, "birmingham", 1, player, Industry.BREWERY, 2)
    for _t, _s, tile in game.all_tiles():
        if tile.industry is Industry.BREWERY:
            tile.resources = 4
    for link in game.data.links:
        if link.canal:
            game.links[link.id] = player
    reached = {(s.merchant, s.mslot)
               for sell in legal_sells(game) for s in sell.sales}
    assert len(reached) > 1, f"only one merchant slot ever offered: {reached}"
