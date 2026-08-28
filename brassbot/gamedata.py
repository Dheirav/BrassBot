"""Static game data: the printed components, loaded once and frozen.

Everything here is a fact about the physical game, not a rule about how it is
played. It is generated from ``tools/extract_gamedata.js``; edit that (and the
vendored source it reads) rather than the JSON, so the provenance stays intact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from functools import cache
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "data" / "brass.json"


class Industry(str, Enum):
    COAL_MINE = "coal_mine"
    IRON_WORKS = "iron_works"
    BREWERY = "brewery"
    COTTON_MILL = "cotton_mill"
    MANUFACTURER = "manufacturer"
    POTTERY = "pottery"

    @property
    def is_sellable(self) -> bool:
        """Sellable industries flip via the Sell action; the rest flip when their
        cubes are exhausted."""
        return self in _SELLABLE

    @property
    def is_resource(self) -> bool:
        return self in _RESOURCE


_SELLABLE = frozenset({Industry.COTTON_MILL, Industry.MANUFACTURER, Industry.POTTERY})
_RESOURCE = frozenset({Industry.COAL_MINE, Industry.IRON_WORKS, Industry.BREWERY})


class Era(str, Enum):
    CANAL = "canal"
    RAIL = "rail"


@dataclass(frozen=True, slots=True)
class TileSpec:
    """One level of one industry, as printed on the player mat."""

    industry: Industry
    level: int
    count: int  # copies each player owns
    canal_era: bool
    rail_era: bool
    cost: int
    coal_cost: int
    iron_cost: int
    vp: int
    income: int  # income SPACES advanced on flip, not income levels
    link_vp: int
    can_develop: bool  # False == the lightbulb icon (pottery 1 and 3)
    beer_to_sell: int | None  # None for non-sellable industries
    resource_produced: int  # coal/iron cubes; 0 for everything else

    def buildable_in(self, era: Era) -> bool:
        return self.canal_era if era is Era.CANAL else self.rail_era

    def beer_produced(self, era: Era) -> int:
        """Rulebook Build step 4b: a brewery gets 1 barrel in the Canal Era and 2
        in the Rail Era. This is a function of the era it is BUILT in, and never
        of the tile's level."""
        if self.industry is not Industry.BREWERY:
            return 0
        return 1 if era is Era.CANAL else 2


@dataclass(frozen=True, slots=True)
class Town:
    id: str
    name: str
    region: str
    slots: tuple[frozenset[Industry], ...]  # allowed industries per build slot
    farm_brewery: bool


@dataclass(frozen=True, slots=True)
class Merchant:
    id: str
    name: str
    slots: int
    min_players: int
    bonus_type: str  # 'vp' | 'income' | 'money' | 'develop'
    bonus_amount: int


@dataclass(frozen=True, slots=True)
class Link:
    """One buildable line on the board, joining the locations in ``ends``.

    Almost always two, but the Kidderminster-Worcester line joins three: the
    rules attach the southern farm brewery to that single tile.
    """

    id: str
    ends: tuple[str, ...]
    canal: bool
    rail: bool


@dataclass(frozen=True, slots=True)
class Market:
    """A resource market: a ladder of price slots, cheapest first.

    Cubes always occupy the EXPENSIVE end of the ladder, so the empty spaces are
    a prefix at the cheap end. Setup makes this concrete: the coal market holds
    13 of 14 cubes with "one of the £1 spaces free", and iron holds 8 of 10 with
    "both £1 spaces free".

    So buying takes the cheapest cube present (and the price ratchets up as the
    market drains), while selling fills the most expensive empty space first
    (and the price ratchets down). A depleted market is an expensive one.
    """

    prices: tuple[int, ...]
    initial: int
    empty_price: int

    @property
    def capacity(self) -> int:
        return len(self.prices)

    def price_to_buy_one(self, held: int) -> int:
        return self.prices[self.capacity - held] if held > 0 else self.empty_price

    def cost_to_buy(self, held: int, n: int) -> int:
        """Total price of buying ``n`` cubes from a market holding ``held``.
        Each cube taken raises the price of the next."""
        total = 0
        for _ in range(n):
            total += self.price_to_buy_one(held)
            held = max(0, held - 1)
        return total

    def revenue_from_selling(self, held: int, n: int) -> tuple[int, int]:
        """Money earned putting up to ``n`` cubes into the market, and how many
        actually fit. Cubes that do not fit stay on the industry tile."""
        total = 0
        placed = 0
        while placed < n and held < self.capacity:
            total += self.prices[self.capacity - held - 1]
            held += 1
            placed += 1
        return total, placed


@dataclass(frozen=True, slots=True)
class GameData:
    tiles: dict[Industry, tuple[TileSpec, ...]]
    towns: dict[str, Town]
    merchants: dict[str, Merchant]
    merchant_tile_mix: dict[int, tuple[str, ...]]
    links: tuple[Link, ...]
    #: links keyed by id, so a player's own links can be walked without
    #: scanning all 39 lines on the board
    link_by_id: dict[str, Link]
    decks: dict[int, dict]
    coal: Market
    iron: Market
    constants: dict[str, int]

    def tile(self, industry: Industry, level: int) -> TileSpec:
        return self.tiles[industry][level - 1]

    def merchants_for(self, players: int) -> dict[str, Merchant]:
        return {k: m for k, m in self.merchants.items() if m.min_players <= players}

    def merchant_tiles_for(self, players: int) -> tuple[str, ...]:
        """The merchant tiles in play, which is every tile marked with a player
        count at or below this game's."""
        out: list[str] = []
        for n in sorted(self.merchant_tile_mix):
            if n <= players:
                out.extend(self.merchant_tile_mix[n])
        return tuple(out)


# --- income track -----------------------------------------------------------
# The progress track is nonlinear: high income levels are spaced further apart,
# so each additional point of income costs progressively more flips. Income
# ADVANCES are measured in spaces; the level is what the space is worth.

def income_level(space: int) -> int:
    if space <= 10:
        return space - 10
    if space <= 30:
        return -(-(space - 10) // 2)
    if space <= 60:
        return 10 + -(-(space - 30) // 3)
    if space <= 96:
        return 20 + -(-(space - 60) // 4)
    return 30


def highest_space_of_level(level: int) -> int:
    """The space a marker drops to when a loan costs it income levels: the
    highest-numbered space still showing that level."""
    if level <= 0:
        return level + 10
    if level <= 10:
        return 10 + 2 * level
    if level <= 20:
        return 30 + 3 * (level - 10)
    if level <= 29:
        return 60 + 4 * (level - 20)
    return 99


MAX_INCOME_SPACE = 99


@cache
def load() -> GameData:
    raw = json.loads(_DATA_PATH.read_text())

    tiles = {
        Industry(k): tuple(
            TileSpec(
                industry=Industry(k),
                level=t["level"],
                count=t["count"],
                canal_era=t["canal_era"],
                rail_era=t["rail_era"],
                cost=t["cost"],
                coal_cost=t["coal_cost"],
                iron_cost=t["iron_cost"],
                vp=t["vp"],
                income=t["income"],
                link_vp=t["link_vp"],
                can_develop=t["can_develop"],
                beer_to_sell=t["beer_to_sell"],
                resource_produced=t.get("resource_produced", 0),
            )
            for t in sorted(v, key=lambda t: t["level"])
        )
        for k, v in raw["industries"].items()
    }

    towns = {
        tid: Town(
            id=tid,
            name=t["name"],
            region=t["region"],
            slots=tuple(frozenset(Industry(i) for i in slot) for slot in t["slots"]),
            farm_brewery=t.get("farm_brewery", False),
        )
        for tid, t in raw["towns"].items()
    }

    merchants = {
        mid: Merchant(id=mid, name=m["name"], slots=m["slots"], min_players=m["min_players"],
                      bonus_type=m["bonus_type"], bonus_amount=m["bonus_amount"])
        for mid, m in raw["merchants"].items()
    }

    return GameData(
        tiles=tiles,
        towns=towns,
        merchants=merchants,
        merchant_tile_mix={int(k): tuple(v) for k, v in raw["merchant_tile_mix"].items()},
        links=(links := tuple(Link(id=l["id"], ends=tuple(l["ends"]),
                                   canal=l["canal"], rail=l["rail"])
                              for l in raw["connections"])),
        link_by_id={link.id: link for link in links},
        decks={int(k): v for k, v in raw["decks"].items()},
        coal=Market(tuple(raw["market"]["coal"]["prices"]), raw["market"]["coal"]["initial"],
                    raw["market"]["coal"]["empty_price"]),
        iron=Market(tuple(raw["market"]["iron"]["prices"]), raw["market"]["iron"]["initial"],
                    raw["market"]["iron"]["empty_price"]),
        constants=raw["constants"],
    )
