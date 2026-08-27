"""Mutable game state, plus setup.

Designed to be cloned constantly by search, so it holds plain lists/dicts and
shares the immutable :class:`GameData` rather than copying it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .cards import (
    WILD_INDUSTRY_COUNT,
    WILD_LOCATION_COUNT,
    Card,
    build_deck,
)
from .gamedata import (
    MAX_INCOME_SPACE,
    Era,
    GameData,
    Industry,
    highest_space_of_level,
    income_level,
    load,
)

LINKS_PER_PLAYER = 14
HAND_SIZE = 8

# Rounds per era, from deck exhaustion: 8/9/10 for 4/3/2 players.
ROUNDS_PER_ERA = {2: 10, 3: 9, 4: 8}


class LinkMap(dict):
    """The placed link tiles, tracking a version so derived graphs can cache.

    Connectivity is recomputed constantly -- coal sourcing, sell legality, beer
    reach -- but the link graph changes only when someone builds a link or an
    era ends. Bumping a counter on mutation lets those derived structures cache
    safely without every call site having to remember to invalidate.
    """

    __slots__ = ("version",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.version = 0

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.version += 1

    def __delitem__(self, key):
        super().__delitem__(key)
        self.version += 1

    def clear(self):
        super().clear()
        self.version += 1

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self.version += 1

    def pop(self, *args):
        result = super().pop(*args)
        self.version += 1
        return result


@dataclass(slots=True)
class Tile:
    """An industry tile placed on the board."""

    owner: int
    industry: Industry
    level: int
    era_built: Era
    flipped: bool = False
    resources: int = 0  # coal/iron cubes, or beer barrels, still on the tile

    def clone(self) -> Tile:
        return Tile(self.owner, self.industry, self.level, self.era_built,
                    self.flipped, self.resources)


@dataclass(slots=True)
class MerchantSlot:
    """One merchant tile in a merchant location, with its beer space."""

    merchant: str
    kind: str  # 'any' | 'blank' | an Industry value
    beer: int = 0

    def accepts(self, industry: Industry) -> bool:
        return self.kind == "any" or self.kind == industry.value

    def clone(self) -> MerchantSlot:
        return MerchantSlot(self.merchant, self.kind, self.beer)


@dataclass(slots=True)
class Player:
    idx: int
    money: int
    income_space: int
    vp: int = 0
    spent: int = 0  # money spent this round; drives next round's turn order
    hand: list[Card] = field(default_factory=list)
    discard: list[Card] = field(default_factory=list)
    # Remaining copies of each level, indexed by level-1. You always take the
    # lowest level still present.
    mat: dict[Industry, list[int]] = field(default_factory=dict)
    links_left: int = LINKS_PER_PLAYER
    # VP surrendered to unpayable negative income. Diagnostics only -- the rules
    # never read it -- but without it a score breakdown cannot tell a merchant
    # bonus from a debt penalty.
    vp_penalties: int = 0

    @property
    def income(self) -> int:
        return income_level(self.income_space)

    def lowest_level(self, industry: Industry) -> int | None:
        """The only tile of this industry you may build or develop away."""
        for i, remaining in enumerate(self.mat[industry]):
            if remaining:
                return i + 1
        return None

    def advance_income(self, spaces: int) -> None:
        self.income_space = min(self.income_space + spaces, MAX_INCOME_SPACE)

    def lose_income_levels(self, levels: int) -> None:
        """Loans move the marker by income LEVELS, landing on the highest space
        within the new level."""
        self.income_space = highest_space_of_level(self.income - levels)

    def clone(self) -> Player:
        p = Player(self.idx, self.money, self.income_space, self.vp, self.spent,
                   list(self.hand), list(self.discard),
                   {k: list(v) for k, v in self.mat.items()}, self.links_left,
                   self.vp_penalties)
        return p


@dataclass(slots=True)
class GameState:
    data: GameData
    n_players: int
    era: Era
    round: int
    turn_order: list[int]  # player indices, first to last
    turn_pos: int  # index into turn_order
    actions_left: int
    players: list[Player]
    tiles: dict[str, list[Tile | None]]  # town id -> one entry per build slot
    links: LinkMap  # link id -> owner
    merchants: dict[str, list[MerchantSlot]]
    coal: int  # cubes in the coal market
    iron: int  # cubes in the iron market
    deck: list[Card]
    wild_location: int
    wild_industry: int
    rng: random.Random
    finished: bool = False
    # One entry per era once scored. Diagnostics read it; the rules never do.
    era_scores: list = field(default_factory=list)
    # Derived-graph caches, keyed on links.version. Never copied by clone().
    _adj_cache: tuple | None = None
    _dist_cache: tuple | None = None

    # -- convenience ---------------------------------------------------------

    @property
    def current(self) -> Player:
        return self.players[self.turn_order[self.turn_pos]]

    @property
    def rounds_this_era(self) -> int:
        return ROUNDS_PER_ERA[self.n_players]

    def all_tiles(self):
        """Every placed tile, as (town_id, slot_index, tile)."""
        for town_id, slots in self.tiles.items():
            for i, tile in enumerate(slots):
                if tile is not None:
                    yield town_id, i, tile

    def merchant_slots(self):
        for slots in self.merchants.values():
            yield from slots

    def clone(self) -> GameState:
        # The clone needs its own generator. A lookahead that applies an action
        # far enough to reshuffle the deck would otherwise draw from the real
        # game's RNG and change what actually happens. Copying the state keeps
        # it deterministic while making it independent.
        rng = random.Random()
        rng.setstate(self.rng.getstate())
        return GameState(
            data=self.data,  # immutable, shared
            n_players=self.n_players,
            era=self.era,
            round=self.round,
            turn_order=list(self.turn_order),
            turn_pos=self.turn_pos,
            actions_left=self.actions_left,
            players=[p.clone() for p in self.players],
            tiles={k: [t.clone() if t else None for t in v] for k, v in self.tiles.items()},
            links=LinkMap(self.links),
            merchants={k: [s.clone() for s in v] for k, v in self.merchants.items()},
            coal=self.coal,
            iron=self.iron,
            deck=list(self.deck),
            wild_location=self.wild_location,
            wild_industry=self.wild_industry,
            rng=rng,
            finished=self.finished,
            era_scores=list(self.era_scores),
        )


def new_game(n_players: int = 4, seed: int | None = None) -> GameState:
    data = load()
    rng = random.Random(seed)

    deck = build_deck(n_players)
    rng.shuffle(deck)

    players: list[Player] = []
    for i in range(n_players):
        mat = {
            industry: [spec.count for spec in specs]
            for industry, specs in data.tiles.items()
        }
        p = Player(
            idx=i,
            money=data.constants["initial_money"],
            income_space=data.constants["initial_income_space"],
            mat=mat,
        )
        p.hand = [deck.pop() for _ in range(HAND_SIZE)]
        # Setup deals one extra card facedown; it is the bottom of the discard
        # pile, which is why the rules say to turn it over before reshuffling.
        p.discard = [deck.pop()]
        players.append(p)

    # Merchant tiles are shuffled and dealt to the slots in play.
    tiles_to_deal = list(data.merchant_tiles_for(n_players))
    rng.shuffle(tiles_to_deal)
    merchants: dict[str, list[MerchantSlot]] = {}
    for mid, merchant in data.merchants_for(n_players).items():
        slots = []
        for _ in range(merchant.slots):
            kind = tiles_to_deal.pop()
            # A beer barrel sits beside every non-blank merchant tile.
            slots.append(MerchantSlot(mid, kind, beer=0 if kind == "blank" else 1))
        merchants[mid] = slots

    order = list(range(n_players))
    rng.shuffle(order)

    return GameState(
        data=data,
        n_players=n_players,
        era=Era.CANAL,
        round=1,
        turn_order=order,
        turn_pos=0,
        actions_left=1,  # first round of the Canal Era is a single action
        players=players,
        tiles={tid: [None] * len(t.slots) for tid, t in data.towns.items()},
        links=LinkMap(),
        merchants=merchants,
        coal=data.coal.initial,
        iron=data.iron.initial,
        deck=deck,
        wild_location=WILD_LOCATION_COUNT,
        wild_industry=WILD_INDUSTRY_COUNT,
        rng=rng,
    )
