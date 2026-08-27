"""Invariants on the static data.

These exist because the component data was transcribed from a third party. Each
test below is an independent fact about the physical game, so a transcription
error has to break at least one of them to get through.
"""

import pytest

from brassbot.gamedata import (
    Era,
    Industry,
    MAX_INCOME_SPACE,
    highest_space_of_level,
    income_level,
    load,
)

DATA = load()


# --- components -------------------------------------------------------------

def test_forty_five_tiles_per_player():
    """The publisher states 180 industry tiles, 45 per colour."""
    assert sum(t.count for tiles in DATA.tiles.values() for t in tiles) == 45


def test_every_industry_has_contiguous_levels_from_one():
    for industry, tiles in DATA.tiles.items():
        assert [t.level for t in tiles] == list(range(1, len(tiles) + 1)), industry


def test_sellable_industries_have_a_beer_cost_and_others_do_not():
    for industry, tiles in DATA.tiles.items():
        for t in tiles:
            if industry.is_sellable:
                assert t.beer_to_sell is not None, (industry, t.level)
            else:
                assert t.beer_to_sell is None, (industry, t.level)


def test_only_coal_and_iron_produce_cubes():
    for industry, tiles in DATA.tiles.items():
        for t in tiles:
            if industry in (Industry.COAL_MINE, Industry.IRON_WORKS):
                assert t.resource_produced > 0
            else:
                assert t.resource_produced == 0


def test_every_tile_is_buildable_in_at_least_one_era():
    for tiles in DATA.tiles.values():
        for t in tiles:
            assert t.canal_era or t.rail_era


def test_pottery_lightbulb_tiles_cannot_be_developed():
    """Pottery 1 and 3 carry the lightbulb icon; nothing else does."""
    undevelopable = {
        (i, t.level) for i, tiles in DATA.tiles.items() for t in tiles if not t.can_develop
    }
    assert undevelopable == {(Industry.POTTERY, 1), (Industry.POTTERY, 3)}


def test_brewery_output_is_per_era_not_per_level():
    """Rulebook Build 4b. Encoding this per-level is the single correction made
    to the vendored source, so pin it."""
    for t in DATA.tiles[Industry.BREWERY]:
        assert t.beer_produced(Era.CANAL) == 1
        assert t.beer_produced(Era.RAIL) == 2


# --- board ------------------------------------------------------------------

def test_board_has_twenty_towns_and_two_farm_breweries():
    farms = [t for t in DATA.towns.values() if t.farm_brewery]
    assert len(farms) == 2
    assert len(DATA.towns) - len(farms) == 20


def test_farm_breweries_only_accept_breweries():
    for town in DATA.towns.values():
        if town.farm_brewery:
            assert town.slots == (frozenset({Industry.BREWERY}),)


def test_every_town_slot_lists_at_least_one_industry():
    for town in DATA.towns.values():
        assert town.slots
        for slot in town.slots:
            assert slot


def test_link_endpoints_all_exist():
    known = set(DATA.towns) | set(DATA.merchants)
    for link in DATA.links:
        assert len(link.ends) >= 2, link
        assert len(set(link.ends)) == len(link.ends), link
        for end in link.ends:
            assert end in known, link


def test_every_link_is_canal_rail_or_both():
    for link in DATA.links:
        assert link.canal or link.rail


def test_board_is_connected_via_rail():
    """The Rail Era graph must be one component covering EVERY location, or part
    of the board would be unreachable. Checking coverage matters as much as
    checking connectivity: an isolated location simply would not appear in an
    adjacency map built from links alone."""
    adjacency: dict[str, set[str]] = {loc: set() for loc in {**DATA.towns, **DATA.merchants}}
    for link in DATA.links:
        for a in link.ends:
            for b in link.ends:
                if a != b:
                    adjacency[a].add(b)
    start = next(iter(adjacency))
    seen, stack = {start}, [start]
    while stack:
        for nxt in adjacency[stack.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    assert seen == set(adjacency)
    assert seen == set(DATA.towns) | set(DATA.merchants)


def test_farm_brewery_link_topology():
    """The northern farm brewery hangs off its own link tile from Cannock. The
    southern one has no tile of its own: the Kidderminster-Worcester line
    connects all three at once."""
    joins = {link.id: set(link.ends) for link in DATA.links}
    assert joins["cannock-northern"] == {"cannock", "farm_northern"}
    assert joins["kidderminster-worcester"] == {"kidderminster", "worcester", "farm_southern"}
    # farm_southern must never be an endpoint of any other line
    others = [l.id for l in DATA.links if "farm_southern" in l.ends]
    assert others == ["kidderminster-worcester"]


# --- merchants --------------------------------------------------------------

@pytest.mark.parametrize("players,expected", [(2, 5), (3, 7), (4, 9)])
def test_merchant_tiles_exactly_fill_the_available_slots(players, expected):
    slots = sum(m.slots for m in DATA.merchants_for(players).values())
    assert slots == expected
    assert len(DATA.merchant_tiles_for(players)) == expected


def test_two_player_game_drops_warrington_and_nottingham():
    """Rulebook setup: no merchant tiles in Warrington or Nottingham at 2p, and
    none in Nottingham at 3p."""
    assert set(DATA.merchants_for(2)) == {"shrewsbury", "gloucester", "oxford"}
    assert "nottingham" not in DATA.merchants_for(3)
    assert len(DATA.merchants_for(4)) == 5


def test_merchant_tiles_name_real_industries():
    for tile in DATA.merchant_tiles_for(4):
        assert tile in {"any", "blank"} or Industry(tile).is_sellable


# --- deck -------------------------------------------------------------------

@pytest.mark.parametrize("players,size", [(2, 40), (3, 54), (4, 64)])
def test_deck_sizes(players, size):
    deck = DATA.decks[players]
    total = (
        sum(deck["locations"].values())
        + sum(deck["industries"].values())
        + deck["dual_cotton_manufacturer"]
    )
    assert total == size


def test_deck_names_real_towns_and_never_a_farm_brewery():
    """Farm breweries have no location card; they are reachable only through a
    brewery or wild industry card."""
    for deck in DATA.decks.values():
        for town_id in deck["locations"]:
            assert town_id in DATA.towns, town_id
            assert not DATA.towns[town_id].farm_brewery, town_id


def test_deck_industry_cards_name_real_industries():
    for deck in DATA.decks.values():
        for industry in deck["industries"]:
            Industry(industry)


def test_four_player_deck_covers_every_non_farm_town():
    non_farm = {tid for tid, t in DATA.towns.items() if not t.farm_brewery}
    assert set(DATA.decks[4]["locations"]) == non_farm


# --- markets ----------------------------------------------------------------

def test_market_setup_leaves_the_cheap_spaces_free():
    """Coal starts with one £1 space free; iron with both."""
    coal, iron = DATA.coal, DATA.iron
    assert coal.capacity - coal.initial == 1
    assert iron.capacity - iron.initial == 2
    assert coal.price_to_buy_one(coal.initial) == 1
    assert iron.price_to_buy_one(iron.initial) == 2  # both £1 spaces are empty


def test_market_prices_are_two_of_each_value():
    assert DATA.coal.prices == (1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7)
    assert DATA.iron.prices == (1, 1, 2, 2, 3, 3, 4, 4, 5, 5)
    assert DATA.coal.empty_price == 8
    assert DATA.iron.empty_price == 6


def test_buying_drains_from_the_cheap_end_and_ratchets_the_price_up():
    coal = DATA.coal
    assert coal.cost_to_buy(13, 1) == 1
    assert coal.cost_to_buy(13, 3) == 5  # £1 + £2 + £2
    prices = [coal.price_to_buy_one(h) for h in range(coal.capacity, 0, -1)]
    assert prices == sorted(prices)  # never gets cheaper as the market drains


def test_buying_from_an_empty_market_pays_the_flat_price():
    assert DATA.coal.cost_to_buy(0, 3) == 24
    assert DATA.iron.cost_to_buy(0, 3) == 18


def test_selling_fills_the_most_expensive_empty_space_first():
    coal = DATA.coal
    assert coal.revenue_from_selling(4, 5) == (21, 5)  # £5+£5+£4+£4+£3
    assert coal.revenue_from_selling(13, 4) == (1, 1)  # only one space left, a £1


def test_a_full_market_absorbs_nothing():
    assert DATA.coal.revenue_from_selling(DATA.coal.capacity, 3) == (0, 0)


def test_buy_and_sell_are_inverse_at_the_boundary():
    """Selling a cube then buying it back is a wash, at every market level."""
    coal = DATA.coal
    for held in range(0, coal.capacity):
        revenue, placed = coal.revenue_from_selling(held, 1)
        assert placed == 1
        assert coal.cost_to_buy(held + 1, 1) == revenue


# --- income track -----------------------------------------------------------

def test_income_track_anchors():
    assert income_level(0) == -10
    assert income_level(10) == 0  # every player starts here
    assert income_level(MAX_INCOME_SPACE) == 30


def test_income_is_monotonic_over_the_whole_track():
    levels = [income_level(s) for s in range(MAX_INCOME_SPACE + 1)]
    assert levels == sorted(levels)


def test_income_levels_widen_up_the_track():
    """1 space per level, then 2, then 3, then 4 — this is what makes late
    income expensive."""
    from collections import Counter

    width = Counter(income_level(s) for s in range(MAX_INCOME_SPACE + 1))
    assert width[-5] == 1
    assert width[5] == 2
    assert width[15] == 3
    assert width[25] == 4


def test_highest_space_of_level_round_trips():
    for level in range(-10, 31):
        space = highest_space_of_level(level)
        assert income_level(space) == level
        if space < MAX_INCOME_SPACE:
            assert income_level(space + 1) == level + 1
