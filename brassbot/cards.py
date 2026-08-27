"""The card deck.

A card is permission, not a resource: it says *where* you may build (location)
or *what* you may build (industry). Every action discards one, including the
ones that seem not to need a card.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .gamedata import Industry, load

# Both wild decks hold 4 cards. Wild cards return to their faceup deck when
# played, so the supply only depletes while cards sit in players' hands.
WILD_LOCATION_COUNT = 4
WILD_INDUSTRY_COUNT = 4


class CardKind(str, Enum):
    LOCATION = "location"
    INDUSTRY = "industry"
    WILD_LOCATION = "wild_location"
    WILD_INDUSTRY = "wild_industry"


@dataclass(frozen=True, slots=True)
class Card:
    kind: CardKind
    town: str | None = None
    # An industry card may name more than one: the dual cotton/manufacturer card
    # is buildable as either.
    industries: frozenset[Industry] = frozenset()

    @property
    def is_wild(self) -> bool:
        return self.kind in (CardKind.WILD_LOCATION, CardKind.WILD_INDUSTRY)

    def __repr__(self) -> str:  # keeps game logs readable
        if self.kind is CardKind.LOCATION:
            return f"<{self.town}>"
        if self.kind is CardKind.INDUSTRY:
            return "<" + "/".join(sorted(i.value for i in self.industries)) + ">"
        return "<wild-loc>" if self.kind is CardKind.WILD_LOCATION else "<wild-ind>"


WILD_LOCATION = Card(CardKind.WILD_LOCATION)
WILD_INDUSTRY = Card(CardKind.WILD_INDUSTRY)


def build_deck(players: int) -> list[Card]:
    """The draw deck for a game of this size. Wild cards are not part of it."""
    spec = load().decks[players]
    deck: list[Card] = []

    for town, count in spec["locations"].items():
        deck += [Card(CardKind.LOCATION, town=town)] * count

    for industry, count in spec["industries"].items():
        deck += [Card(CardKind.INDUSTRY, industries=frozenset({Industry(industry)}))] * count

    dual = frozenset({Industry.COTTON_MILL, Industry.MANUFACTURER})
    deck += [Card(CardKind.INDUSTRY, industries=dual)] * spec["dual_cotton_manufacturer"]

    return deck
