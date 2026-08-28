"""Actions.

Every action discards exactly one card, except Scout which discards three.
Resource plans are carried on the action itself so that applying it is
deterministic -- search needs to be able to replay a chosen move exactly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .gamedata import Industry
from .resources import Plan


@dataclass(frozen=True, slots=True)
class Build:
    card: int
    town: str
    slot: int
    industry: Industry
    coal: Plan = ()
    iron: Plan = ()


@dataclass(frozen=True, slots=True)
class Network:
    """One canal, one rail, or two rails in a single action."""

    card: int
    lines: tuple[str, ...]
    coal: Plan = ()
    beer: Plan = ()


@dataclass(frozen=True, slots=True)
class Develop:
    card: int
    industries: tuple[Industry, ...]  # one or two, may repeat
    iron: Plan = ()


@dataclass(frozen=True, slots=True)
class Sale:
    town: str
    slot: int
    merchant: str
    mslot: int


@dataclass(frozen=True, slots=True)
class Sell:
    """A single Sell action may flip several tiles.

    ``own_beer`` asks the sale to spend our own barrels before a merchant's. The
    rulebook says you MAY consume a merchant's beer, and taking it is usually
    right -- it is free and carries a bonus -- but not always: spending your own
    barrels flips your own breweries, which is 5-10 VP each and scores twice if
    it happens in the Canal Era. Three separate agents reported being unable to
    make that choice.
    """

    card: int
    sales: tuple[Sale, ...]
    own_beer: bool = False


@dataclass(frozen=True, slots=True)
class Loan:
    card: int


@dataclass(frozen=True, slots=True)
class Scout:
    card: int
    extra: tuple[int, int]


@dataclass(frozen=True, slots=True)
class Pass:
    card: int


Action = Build | Network | Develop | Sell | Loan | Scout | Pass
