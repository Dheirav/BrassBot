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
    """A single Sell action may flip several tiles; beer is resolved greedily at
    apply time (merchant beer first, then own breweries)."""

    card: int
    sales: tuple[Sale, ...]


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
