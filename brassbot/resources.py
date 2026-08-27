"""Sourcing and consuming coal, iron and beer.

Each resource has different reach, and the differences drive most of the game's
tactics:

* **Coal** must come from the *closest connected* unflipped mine. Only when no
  connected mine has any coal left may you buy from the market, and that needs a
  route to a merchant space.
* **Iron** may come from *any* unflipped iron works anywhere on the board -- no
  connection, no distance. Market iron needs no connection either.
* **Beer** comes from your own breweries anywhere, an opponent's brewery only if
  connected, or the beer beside the merchant tile you are selling to.

Taking the last cube off a tile flips it, which pays its owner income. That is
why *which* tied source you drain is a real decision and not a detail: it can
hand an opponent income, or flip your own tile for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import islice

from .gamedata import Industry
from .network import connected_locations, distances_from, is_connected_to_merchant
from .state import GameState

# Enumerating every tied source explodes the action space for no strategic gain
# past the first few. Search sees this many distinct plans per requirement.
DEFAULT_PLAN_LIMIT = 6


@dataclass(frozen=True, slots=True)
class Draw:
    """One unit of one resource, taken from one place."""

    kind: str  # 'tile' | 'market' | 'merchant_beer'
    resource: str = "coal"  # 'coal' | 'iron' | 'beer'
    town: str | None = None
    slot: int | None = None
    merchant: str | None = None
    mslot: int | None = None
    cost: int = 0  # money, for market draws only

    @property
    def is_merchant_beer(self) -> bool:
        return self.kind == "merchant_beer"


Plan = tuple[Draw, ...]


def plan_cost(plan: Plan) -> int:
    return sum(d.cost for d in plan)


# --- coal -------------------------------------------------------------------

def _mines_with_coal(state: GameState) -> list[tuple[str, int]]:
    return [
        (town, slot)
        for town, slot, tile in state.all_tiles()
        if tile.industry is Industry.COAL_MINE and tile.resources > 0
    ]


def coal_plans(state: GameState, origin, n: int, limit: int = DEFAULT_PLAN_LIMIT) -> list[Plan]:
    """Distinct ways to obtain ``n`` coal for something at ``origin``.

    ``origin`` is one or more locations: a build site, or both ends of a rail
    link (the link only has to be connected to coal once placed).
    """
    if n == 0:
        return [()]
    origins = [origin] if isinstance(origin, str) else list(origin)
    market_ok = is_connected_to_merchant(state, origins)

    results: list[Plan] = []

    # The link graph cannot change while we plan, so distances are fixed.
    #
    # Searching from each MINE instead (so the cache key is a single town shared
    # by every candidate action) was tried twice and measured slower both times,
    # hoisted and not: a board carries 8-12 mines, so it multiplies the number
    # of searches to save re-keying one. One search from the origin wins.
    dist = distances_from(state, origins)

    # Track depletion inside a plan without mutating the board.
    def recurse(taken: dict[tuple[str, int], int], market_bought: int, plan: Plan):
        if len(results) >= limit:
            return
        if len(plan) == n:
            results.append(plan)
            return

        available = []
        for town, slot in _mines_with_coal(state):
            left = state.tiles[town][slot].resources - taken.get((town, slot), 0)
            if left > 0 and town in dist:
                available.append((dist[town], town, slot))

        if available:
            nearest = min(d for d, _, _ in available)
            options = sorted((t, s) for d, t, s in available if d == nearest)
            for town, slot in options:
                key = (town, slot)
                recurse({**taken, key: taken.get(key, 0) + 1}, market_bought,
                        plan + (Draw("tile", "coal", town=town, slot=slot),))
                if len(results) >= limit:
                    return
        elif market_ok:
            # Market coal only once no connected mine has any coal left.
            held = state.coal - market_bought
            cost = state.data.coal.price_to_buy_one(held)
            recurse(taken, market_bought + 1, plan + (Draw("market", "coal", cost=cost),))

    recurse({}, 0, ())
    return results


# --- iron -------------------------------------------------------------------

def iron_plans(state: GameState, n: int, limit: int = DEFAULT_PLAN_LIMIT) -> list[Plan]:
    """Iron ignores the network entirely: any unflipped iron works will do, and
    the market is always reachable."""
    if n == 0:
        return [()]

    results: list[Plan] = []

    def recurse(taken: dict[tuple[str, int], int], market_bought: int, plan: Plan):
        if len(results) >= limit:
            return
        if len(plan) == n:
            results.append(plan)
            return

        available = sorted(
            (town, slot)
            for town, slot, tile in state.all_tiles()
            if tile.industry is Industry.IRON_WORKS
            and tile.resources - taken.get((town, slot), 0) > 0
        )
        if available:
            for town, slot in available:
                key = (town, slot)
                recurse({**taken, key: taken.get(key, 0) + 1}, market_bought,
                        plan + (Draw("tile", "iron", town=town, slot=slot),))
                if len(results) >= limit:
                    return
        else:
            held = state.iron - market_bought
            cost = state.data.iron.price_to_buy_one(held)
            recurse(taken, market_bought + 1, plan + (Draw("market", "iron", cost=cost),))

    recurse({}, 0, ())
    return results


# --- beer -------------------------------------------------------------------

def beer_plans(
    state: GameState,
    player: int,
    origin,
    n: int,
    merchant: tuple[str, int] | None = None,
    limit: int = DEFAULT_PLAN_LIMIT,
) -> list[Plan]:
    """Ways to obtain ``n`` beer for something at ``origin``.

    ``merchant`` is the (merchant id, slot index) being sold to, if this is a
    Sell action -- merchant beer is available only then, and carries a bonus.
    """
    if n == 0:
        return [()]
    origins = [origin] if isinstance(origin, str) else list(origin)
    reachable = connected_locations(state, origins)

    results: list[Plan] = []

    def recurse(taken: dict, merchant_used: bool, plan: Plan):
        if len(results) >= limit:
            return
        if len(plan) == n:
            results.append(plan)
            return

        options: list[Draw] = []
        # Merchant beer first: it is strictly better when available, since it
        # carries a bonus and costs no brewery.
        if merchant is not None and not merchant_used:
            mid, mslot = merchant
            if state.merchants[mid][mslot].beer > 0:
                options.append(Draw("merchant_beer", "beer", merchant=mid, mslot=mslot))

        for town, slot, tile in state.all_tiles():
            if tile.industry is not Industry.BREWERY:
                continue
            if tile.resources - taken.get((town, slot), 0) <= 0:
                continue
            # Your own breweries need no connection; an opponent's must be
            # connected to where the beer is needed.
            if tile.owner != player and town not in reachable:
                continue
            options.append(Draw("tile", "beer", town=town, slot=slot))

        for draw in options:
            if draw.is_merchant_beer:
                recurse(taken, True, plan + (draw,))
            else:
                key = (draw.town, draw.slot)
                recurse({**taken, key: taken.get(key, 0) + 1}, merchant_used, plan + (draw,))
            if len(results) >= limit:
                return

    recurse({}, False, ())
    return results


# --- applying ---------------------------------------------------------------

def apply_plan(state: GameState, player: int, plan: Plan) -> int:
    """Consume the resources in ``plan``. Returns money spent on market buys.

    Flipping happens here because it is a consequence of consumption, and it
    pays income to the tile's owner -- often an opponent, on your turn.
    """
    from .engine import flip_tile  # imported late: engine imports this module

    spent = 0
    for draw in plan:
        if draw.kind == "tile":
            tile = state.tiles[draw.town][draw.slot]
            tile.resources -= 1
            if tile.resources == 0:
                flip_tile(state, tile)
        elif draw.kind == "merchant_beer":
            state.merchants[draw.merchant][draw.mslot].beer -= 1
        elif draw.kind == "market":
            # Priced against live market state rather than the plan's estimate:
            # a Build can sell cubes into the market before buying from it.
            if draw.resource == "coal":
                spent += state.data.coal.price_to_buy_one(state.coal)
                state.coal = max(0, state.coal - 1)
            else:
                spent += state.data.iron.price_to_buy_one(state.iron)
                state.iron = max(0, state.iron - 1)
        else:  # pragma: no cover
            raise AssertionError(f"unknown draw kind {draw.kind!r}")
    return spent
