"""Evaluation harness.

A Brass score is not self-contained: your tiles flip when *opponents* sell and
consume, so a number only means something against a named opponent pool. Every
report here is therefore labelled with the matchup, and reports a distribution
rather than a mean -- a bot that averages 150 by scoring 210 half the time and
90 the other half is a different animal from one that always scores 150.

Seats rotate so turn-order advantage cannot be mistaken for skill.
"""

from __future__ import annotations

import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Sequence

from .bots import make
from .engine import apply_action, legal_actions, winners
from .state import new_game

DEFAULT_TARGET = 200  # the score we are actually chasing


@dataclass(frozen=True, slots=True)
class GameResult:
    seed: int
    seats: tuple[str, ...]
    scores: tuple[int, ...]
    incomes: tuple[int, ...]
    monies: tuple[int, ...]
    winners: tuple[int, ...]
    moves: int


def play_game(seat_bots: Sequence[str], seed: int, n_players: int = 4) -> GameResult:
    """One game. Fully determined by ``seat_bots`` and ``seed``."""
    bots = [make(name, seed=seed * 1000 + seat) for seat, name in enumerate(seat_bots)]
    state = new_game(n_players, seed=seed)

    moves = 0
    while not state.finished:
        actions = legal_actions(state)
        if not actions:
            raise RuntimeError(f"no legal action at era={state.era} round={state.round}")
        seat = state.current.idx
        action = bots[seat].choose(state, actions)
        apply_action(state, action)
        moves += 1
        if moves > 5000:
            raise RuntimeError("runaway game")

    return GameResult(
        seed=seed,
        seats=tuple(seat_bots),
        scores=tuple(p.vp for p in state.players),
        incomes=tuple(p.income for p in state.players),
        monies=tuple(p.money for p in state.players),
        winners=tuple(winners(state)),
        moves=moves,
    )


def _play(args) -> GameResult:
    return play_game(*args)


# --- lineups ----------------------------------------------------------------

def lineup(subject: str, opponents: Sequence[str], rotation: int,
           n_players: int = 4) -> list[str]:
    """Seat the subject at ``rotation``, filling the rest cyclically."""
    seats: list[str | None] = [None] * n_players
    seats[rotation % n_players] = subject
    pool = list(opponents) or [subject]
    i = 0
    for seat in range(n_players):
        if seats[seat] is None:
            seats[seat] = pool[i % len(pool)]
            i += 1
    return seats  # type: ignore[return-value]


# --- aggregation ------------------------------------------------------------

@dataclass
class BotSummary:
    name: str
    scores: list[int] = field(default_factory=list)
    wins: float = 0.0
    seatings: int = 0
    by_seat: dict[int, list[int]] = field(default_factory=dict)

    @property
    def games(self) -> int:
        return len(self.scores)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.scores) if self.scores else 0.0

    @property
    def sd(self) -> float:
        return statistics.stdev(self.scores) if len(self.scores) > 1 else 0.0

    @property
    def stderr(self) -> float:
        """How much of the gap between two bots is real, and how much is noise."""
        return self.sd / (len(self.scores) ** 0.5) if self.scores else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    def pct_at_least(self, threshold: int) -> float:
        if not self.scores:
            return 0.0
        return sum(1 for s in self.scores if s >= threshold) / len(self.scores)

    def percentile(self, q: float) -> float:
        if not self.scores:
            return 0.0
        ordered = sorted(self.scores)
        idx = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
        return ordered[idx]


@dataclass
class Report:
    subject: str
    opponents: tuple[str, ...]
    results: list[GameResult]
    by_bot: dict[str, BotSummary]
    elapsed: float
    target: int

    @property
    def matchup(self) -> str:
        if not self.opponents:
            return f"{self.subject} mirror"
        counts: dict[str, int] = {}
        for o in self.opponents:
            counts[o] = counts.get(o, 0) + 1
        parts = [f"{n}x {name}" if n > 1 else name for name, n in counts.items()]
        return f"{self.subject} vs {' + '.join(parts)}"


def summarise(results: Sequence[GameResult]) -> dict[str, BotSummary]:
    by_bot: dict[str, BotSummary] = {}
    for result in results:
        # A drawn game splits the win, so win rates always sum to 1 per game.
        share = 1.0 / len(result.winners)
        for seat, name in enumerate(result.seats):
            summary = by_bot.setdefault(name, BotSummary(name))
            summary.scores.append(result.scores[seat])
            summary.by_seat.setdefault(seat, []).append(result.scores[seat])
            if seat in result.winners:
                summary.wins += share
    return by_bot


def evaluate(subject: str, opponents: Sequence[str], games: int = 100,
             seed0: int = 0, workers: int | None = None,
             n_players: int = 4, target: int = DEFAULT_TARGET) -> Report:
    jobs = [
        (lineup(subject, opponents, g, n_players), seed0 + g, n_players)
        for g in range(games)
    ]

    t0 = time.time()
    if workers and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_play, jobs, chunksize=4))
    else:
        results = [_play(job) for job in jobs]
    elapsed = time.time() - t0

    return Report(subject=subject, opponents=tuple(opponents), results=results,
                  by_bot=summarise(results), elapsed=elapsed, target=target)


# --- rendering --------------------------------------------------------------

def format_report(report: Report) -> str:
    lines: list[str] = []
    games = len(report.results)
    moves = sum(r.moves for r in report.results)
    lines.append(f"Matchup: {report.matchup}")
    lines.append(f"{games} games, seeds {report.results[0].seed}-{report.results[-1].seed}, "
                 f"seats rotated")
    lines.append(f"{report.elapsed:.1f}s  ({games / max(report.elapsed, 1e-9):.1f} games/s, "
                 f"{moves / max(report.elapsed, 1e-9):.0f} moves/s)")
    lines.append("")

    header = (f"{'BOT':<12}{'GAMES':>6}{'MEAN':>8}{'+-':>6}{'SD':>7}"
              f"{'P10':>6}{'P50':>6}{'P90':>6}{'MAX':>6}{'WIN%':>8}{f'>={report.target}':>8}")
    lines.append(header)
    lines.append("-" * len(header))

    order = sorted(report.by_bot.values(), key=lambda s: -s.mean)
    for s in order:
        lines.append(
            f"{s.name:<12}{s.games:>6}{s.mean:>8.1f}{s.stderr:>6.1f}{s.sd:>7.1f}"
            f"{s.percentile(0.10):>6.0f}{s.percentile(0.50):>6.0f}"
            f"{s.percentile(0.90):>6.0f}{max(s.scores):>6}"
            f"{100 * s.win_rate:>7.1f}%{100 * s.pct_at_least(report.target):>7.1f}%"
        )

    # Turn-order bias: if seats differ a lot, a matchup result may be seating.
    subject = report.by_bot.get(report.subject)
    if subject and len(subject.by_seat) > 1:
        lines.append("")
        lines.append(f"{report.subject} by seat (turn order at setup is random, "
                     f"so this should be flat):")
        for seat in sorted(subject.by_seat):
            scores = subject.by_seat[seat]
            lines.append(f"  seat {seat}: n={len(scores):<4} "
                         f"mean {statistics.fmean(scores):.1f}")
    return "\n".join(lines)
