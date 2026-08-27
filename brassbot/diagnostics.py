"""Where the points actually come from.

A mean score says a bot is weak; it does not say *how*. Failing to flip tiles,
failing to build rail links, and never developing far enough up the mat to own
the expensive tiles all look identical from the outside and call for completely
different fixes.

This records the decomposition, and -- more usefully -- lets a bot's best games
be compared against its worst. The gap between those two is the shortest
description of what the bot should be doing more of.
"""

from __future__ import annotations

import statistics
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Sequence

from .actions import Build, Develop, Loan, Network, Sell
from .bots import make
from .engine import apply_action, legal_actions
from .gamedata import Era, Industry
from .state import new_game


@dataclass
class SeatRecord:
    bot: str
    seat: int
    seed: int
    final_vp: int = 0
    money: int = 0
    income: int = 0
    # VP by source, keyed by era value
    industry_vp: dict = field(default_factory=dict)
    link_vp: dict = field(default_factory=dict)
    links_scored: dict = field(default_factory=dict)
    tiles_flipped: dict = field(default_factory=dict)
    tiles_stranded: dict = field(default_factory=dict)
    # behaviour
    actions: Counter = field(default_factory=Counter)
    vp_penalties: int = 0
    tiles_built: int = 0
    tiles_developed: int = 0
    tiles_sold: int = 0
    links_built: Counter = field(default_factory=Counter)
    # Expert play puts loans and develops almost entirely in the Canal Era, so
    # the totals alone hide the mistake that matters.
    loans_by_era: Counter = field(default_factory=Counter)
    develops_by_era: Counter = field(default_factory=Counter)
    # Which stacks get cleared. Developing coal is not the same move as
    # developing cotton, and the totals hide which one is happening.
    develops_by_industry: Counter = field(default_factory=Counter)
    vp_entering_rail: int = 0
    builds_by_industry: Counter = field(default_factory=Counter)
    highest_level: dict = field(default_factory=dict)

    def total(self, source: dict) -> int:
        return sum(source.values())


def run_game(seat_bots: Sequence[str], seed: int, n_players: int = 4) -> list[SeatRecord]:
    bots = [make(name, seed=seed * 1000 + seat) for seat, name in enumerate(seat_bots)]
    state = new_game(n_players, seed=seed)
    records = [SeatRecord(bot=seat_bots[i], seat=i, seed=seed) for i in range(n_players)]

    while not state.finished:
        actions = legal_actions(state)
        if not actions:
            raise RuntimeError(f"no legal action at era={state.era} round={state.round}")
        seat = state.current.idx
        action = bots[seat].choose(state, actions)
        rec = records[seat]
        rec.actions[type(action).__name__] += 1

        # Capture what the action does *before* applying it -- a Build consumes
        # the tile it reports, so the level is only visible beforehand.
        if isinstance(action, Build):
            level = state.players[seat].lowest_level(action.industry)
            rec.tiles_built += 1
            rec.builds_by_industry[action.industry.value] += 1
            if level is not None:
                prev = rec.highest_level.get(action.industry.value, 0)
                rec.highest_level[action.industry.value] = max(prev, level)
        elif isinstance(action, Develop):
            rec.tiles_developed += len(action.industries)
            rec.develops_by_era[state.era.value] += len(action.industries)
            for ind in action.industries:
                rec.develops_by_industry[ind.value] += 1
        elif isinstance(action, Loan):
            rec.loans_by_era[state.era.value] += 1
        elif isinstance(action, Sell):
            rec.tiles_sold += len(action.sales)
        elif isinstance(action, Network):
            rec.links_built[state.era.value] += len(action.lines)

        was_canal = state.era is Era.CANAL
        apply_action(state, action)
        # The moment the era turns, bank what each player is carrying: experts
        # aim to enter the Rail Era on 70-80 VP.
        if was_canal and state.era is not Era.CANAL:
            for seat, p in enumerate(state.players):
                records[seat].vp_entering_rail = p.vp

    for scoring in state.era_scores:
        era = scoring.era.value
        for seat in range(n_players):
            rec = records[seat]
            rec.industry_vp[era] = scoring.industry_vp[seat]
            rec.link_vp[era] = scoring.link_vp[seat]
            rec.links_scored[era] = scoring.links_scored[seat]
            rec.tiles_flipped[era] = scoring.tiles_flipped[seat]
            rec.tiles_stranded[era] = scoring.tiles_stranded[seat]

    for seat, p in enumerate(state.players):
        records[seat].final_vp = p.vp
        records[seat].money = p.money
        records[seat].income = p.income
        records[seat].vp_penalties = p.vp_penalties
    return records


def _run(args):
    return run_game(*args)


def collect(seat_bots: Sequence[str], games: int, seed0: int = 0,
            workers: int | None = None, n_players: int = 4) -> list[SeatRecord]:
    jobs = [(list(seat_bots), seed0 + g, n_players) for g in range(games)]
    if workers and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            batches = list(pool.map(_run, jobs, chunksize=2))
    else:
        batches = [_run(job) for job in jobs]
    return [rec for batch in batches for rec in batch]


# --- reporting --------------------------------------------------------------

def _mean(values) -> float:
    values = list(values)
    return statistics.fmean(values) if values else 0.0


def _merchant_vp(rec: SeatRecord) -> int:
    """Shrewsbury and Nottingham pay VP the moment their beer is drunk, so those
    points never pass through era scoring. Backed out so the split reconciles --
    adding back any VP surrendered to unpayable debt, which is a separate line."""
    scored = rec.total(rec.industry_vp) + rec.total(rec.link_vp)
    return rec.final_vp + rec.vp_penalties - scored


def composition(records: Sequence[SeatRecord]) -> dict[str, float]:
    """Mean VP by source. These sum to the mean final score."""
    return {
        "industry canal": _mean(r.industry_vp.get("canal", 0) for r in records),
        "industry rail": _mean(r.industry_vp.get("rail", 0) for r in records),
        "link canal": _mean(r.link_vp.get("canal", 0) for r in records),
        "link rail": _mean(r.link_vp.get("rail", 0) for r in records),
        "merchant bonus": _mean(_merchant_vp(r) for r in records),
        "lost to debt": _mean(-r.vp_penalties for r in records),
    }


def behaviour(records: Sequence[SeatRecord]) -> dict[str, float]:
    return {
        "tiles built": _mean(r.tiles_built for r in records),
        "tiles sold": _mean(r.tiles_sold for r in records),
        "tiles developed": _mean(r.tiles_developed for r in records),
        "links canal": _mean(r.links_built.get("canal", 0) for r in records),
        "links rail": _mean(r.links_built.get("rail", 0) for r in records),
        "final income": _mean(r.income for r in records),
        "money wasted": _mean(r.money for r in records),
    }


def action_mix(records: Sequence[SeatRecord]) -> dict[str, float]:
    """Mean count of each action type per game."""
    names = sorted({name for r in records for name in r.actions})
    return {name: _mean(r.actions.get(name, 0) for r in records) for name in names}


def stranded_by_era(records: Sequence[SeatRecord]) -> dict[str, float]:
    """Unflipped tiles sitting on the board when each era scored. Reported per
    era because a level 2+ tile stranded in the Canal Era survives the wipe and
    can be counted stranded again in the Rail Era."""
    return {
        "stranded at canal end": _mean(r.tiles_stranded.get("canal", 0) for r in records),
        "stranded at rail end": _mean(r.tiles_stranded.get("rail", 0) for r in records),
        "flipped by canal end": _mean(r.tiles_flipped.get("canal", 0) for r in records),
        "flipped by rail end": _mean(r.tiles_flipped.get("rail", 0) for r in records),
    }


def highest_levels(records: Sequence[SeatRecord]) -> dict[str, float]:
    """Mean of the highest level actually built, per industry. This is the
    clearest read on whether a bot ever reaches the expensive tiles."""
    out = {}
    for industry in Industry:
        out[industry.value] = _mean(r.highest_level.get(industry.value, 0)
                                    for r in records)
    return out


def split_by_outcome(records: Sequence[SeatRecord], fraction: float = 0.2):
    """The bot's best games and its worst, by final score."""
    ordered = sorted(records, key=lambda r: r.final_vp)
    n = max(1, int(len(ordered) * fraction))
    return ordered[-n:], ordered[:n]
