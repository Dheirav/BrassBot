"""How far the bot's play is from expert human play.

Every other measurement in this project is relative to our own bots: the
heuristic was tuned against greedy, search is measured against the heuristic.
That ladder answers "better than our last bot", which is not the same question
as "good at Brass".

This measures against a profile of expert *behaviour* taken from tournament
play, so it owes nothing to any bot we wrote. A bot can beat every opponent we
have while still building half the rail links an expert builds -- and only this
will say so.

**Do not optimise against this.** It diagnoses; it is not an objective. Pushing
the bot to match the expert loan count was tried directly: it reached the band,
raised profile agreement from 4 of 11 dimensions to 7, and cost 25 VP of actual
score. Expert behaviour is what strong play *looks like*, not what causes it --
experts spend 4-6 canal actions borrowing because their remaining actions convert
at ~5 VP each. Copy the symptom without the capability and you just lose the
actions. Use a missed band as a question about the underlying capability.

**Provenance, and its limits.** The bands come from a handful of recorded
tournament games (WBC 2024/2025, Prezcon 2023, WSBG 2022/2025) and from written
expert guidance; sources are cited per band and collected in
`docs/research-landscape.md`. They are *not* a measured distribution -- no public
score distribution exists for this game. Treat a band as "what strong players are
reported to do", not as a confidence interval, and treat being outside one as a
question to investigate rather than a verdict.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable, Sequence

from .diagnostics import SeatRecord

# Actions available to one player across a whole game, by player count.
ACTION_BUDGET = {2: 39, 3: 35, 4: 31}


@dataclass(frozen=True, slots=True)
class Band:
    key: str
    label: str
    low: float
    high: float
    source: str
    measure: Callable[..., float]
    lower_is_better: bool = False
    # VP-per-action is the one band that depends on the format, because the
    # action budget does: 39 / 35 / 31 at 2 / 3 / 4 players.
    needs_players: bool = False


def _mean(values) -> float:
    values = list(values)
    return statistics.fmean(values) if values else 0.0


def _vp_per_action(records, players: int = 4):
    if not records:
        return 0.0
    return _mean(r.final_vp for r in records) / ACTION_BUDGET[players]


def _industry_share(records):
    """Share of VP coming from flipped tiles rather than links."""
    industry = _mean(r.total(r.industry_vp) for r in records)
    links = _mean(r.total(r.link_vp) for r in records)
    total = industry + links
    return industry / total if total else 0.0


PROFILE: tuple[Band, ...] = (
    Band("vp_per_action", "VP per action", 4.8, 5.2,
         "tournament median 158 VP over a 31-action 4p budget = 5.10",
         _vp_per_action, needs_players=True),
    Band("rail_links", "rail links built", 7, 10,
         "WSBG 2025 semifinal, live-scored: 9 / 10 / 7 / 7",
         lambda rs: _mean(r.links_built.get("rail", 0) for r in rs)),
    Band("canal_links", "canal links built", 2, 4,
         "WSBG semifinal itemised end of canal: 2 / 3 / 4 / 3",
         lambda rs: _mean(r.links_built.get("canal", 0) for r in rs)),
    Band("tiles_flipped", "tiles flipped", 8, 12,
         "expert guidance; unflipped tiles are normally a blunder",
         lambda rs: _mean(r.total(r.tiles_flipped) for r in rs)),
    Band("vp_entering_rail", "VP entering the Rail Era", 70, 80,
         "'57 points is low for a heavy industry player, who wants to be at 70+'",
         lambda rs: _mean(r.vp_entering_rail for r in rs)),
    Band("loans_canal", "loans in the Canal Era", 4, 6,
         "'you want to take 4-5 loans in canal and offset them efficiently'",
         lambda rs: _mean(r.loans_by_era.get("canal", 0) for r in rs)),
    Band("loans_rail", "loans in the Rail Era", 0, 3,
         "coal replaces loans in rail: 'think of coal like a loan that gives points'",
         lambda rs: _mean(r.loans_by_era.get("rail", 0) for r in rs),
         lower_is_better=True),
    Band("develops", "tiles developed", 2, 4,
         "cotton III and manufactured V each need 5 tiles cleared",
         lambda rs: _mean(r.tiles_developed for r in rs)),
    Band("develops_rail", "tiles developed in the Rail Era", 0, 0,
         "developing is Canal Era work; rail actions are worth ~5 VP each",
         lambda rs: _mean(r.develops_by_era.get("rail", 0) for r in rs),
         lower_is_better=True),
    Band("money_left", "money left at the end", 0, 10,
         "money scores nothing; leftover cash is unspent buying power",
         lambda rs: _mean(r.money for r in rs), lower_is_better=True),
    Band("industry_share", "share of VP from industry", 0.40, 0.65,
         "measured splits run 65:35 to 40:60 depending on strategy",
         _industry_share),
)


@dataclass(frozen=True, slots=True)
class Gap:
    band: Band
    value: float

    @property
    def inside(self) -> bool:
        return self.band.low <= self.value <= self.band.high

    @property
    def direction(self) -> str:
        if self.inside:
            return "ok"
        return "low" if self.value < self.band.low else "high"

    @property
    def distance(self) -> float:
        """How far outside the band, in band-widths.

        A zero-width band (like 'no developing in the Rail Era') has no natural
        scale, so it is measured against 1 unit instead.
        """
        if self.inside:
            return 0.0
        width = self.band.high - self.band.low or 1.0
        if self.value < self.band.low:
            return (self.band.low - self.value) / width
        return (self.value - self.band.high) / width


def evaluate(records: Sequence[SeatRecord], players: int = 4) -> list[Gap]:
    return [
        Gap(band, band.measure(records, players) if band.needs_players
            else band.measure(records))
        for band in PROFILE
    ]


def summarise(gaps: Sequence[Gap]) -> tuple[int, float]:
    """(dimensions inside their band, mean distance outside in band-widths)."""
    inside = sum(1 for g in gaps if g.inside)
    return inside, _mean(g.distance for g in gaps)
