"""Harness behaviour.

The harness is the instrument we will judge every future bot with, so its own
guarantees -- determinism, fair seating, honest win accounting -- need pinning
just as much as the rules do.
"""

import pytest

from brassbot.evaluate import (
    BotSummary,
    GameResult,
    evaluate,
    format_report,
    lineup,
    play_game,
    summarise,
)


# --- determinism ------------------------------------------------------------

def test_same_seed_and_lineup_gives_an_identical_game():
    seats = ["greedy", "random", "greedy", "random"]
    a = play_game(seats, seed=3)
    b = play_game(seats, seed=3)
    assert a == b


def test_different_seeds_give_different_games():
    seats = ["greedy", "random", "greedy", "random"]
    assert play_game(seats, seed=3).scores != play_game(seats, seed=4).scores


def test_a_game_always_produces_a_winner():
    result = play_game(["greedy"] * 4, seed=1)
    assert result.winners
    best = max(result.scores)
    for seat in result.winners:
        assert result.scores[seat] == best


# --- seating ----------------------------------------------------------------

def test_rotation_puts_the_subject_in_every_seat():
    seen = set()
    for g in range(4):
        seats = lineup("subject", ["a", "b", "c"], g)
        seen.add(seats.index("subject"))
        assert len(seats) == 4
    assert seen == {0, 1, 2, 3}


def test_a_single_opponent_name_fills_the_remaining_seats():
    seats = lineup("subject", ["rival"], 1)
    assert seats == ["rival", "subject", "rival", "rival"]


def test_lineup_handles_a_mirror():
    assert lineup("solo", [], 2) == ["solo", "solo", "solo", "solo"]


# --- aggregation ------------------------------------------------------------

def _result(seats, scores, winners, seed=0):
    return GameResult(seed=seed, seats=tuple(seats), scores=tuple(scores),
                      incomes=(0,) * len(seats), monies=(0,) * len(seats),
                      winners=tuple(winners), moves=1)


def test_summarise_collects_scores_per_bot_across_seats():
    results = [
        _result(["a", "b", "b", "b"], [10, 1, 2, 3], [0]),
        _result(["b", "a", "b", "b"], [4, 20, 5, 6], [1]),
    ]
    by_bot = summarise(results)
    assert sorted(by_bot["a"].scores) == [10, 20]
    assert by_bot["a"].games == 2
    assert by_bot["b"].games == 6


def test_win_shares_sum_to_one_per_game():
    results = [_result(["a", "b", "c", "d"], [5, 5, 1, 1], [0, 1])]
    by_bot = summarise(results)
    assert by_bot["a"].wins == pytest.approx(0.5)
    assert by_bot["b"].wins == pytest.approx(0.5)
    assert sum(s.wins for s in by_bot.values()) == pytest.approx(1.0)


def test_seat_breakdown_is_recorded():
    results = [_result(["a", "b", "b", "b"], [10, 1, 2, 3], [0])]
    by_bot = summarise(results)
    assert by_bot["a"].by_seat == {0: [10]}
    assert by_bot["b"].by_seat == {1: [1], 2: [2], 3: [3]}


# --- statistics -------------------------------------------------------------

def test_target_hit_rate_counts_scores_at_or_above_the_threshold():
    s = BotSummary("x", scores=[199, 200, 201, 100])
    assert s.pct_at_least(200) == pytest.approx(0.5)


def test_percentiles_are_ordered():
    s = BotSummary("x", scores=list(range(101)))
    assert s.percentile(0.10) <= s.percentile(0.50) <= s.percentile(0.90)
    assert s.percentile(0.50) == pytest.approx(50, abs=1)


def test_stderr_shrinks_as_games_accumulate():
    few = BotSummary("x", scores=[0, 100] * 5)
    many = BotSummary("x", scores=[0, 100] * 50)
    assert many.stderr < few.stderr


def test_empty_summary_does_not_explode():
    s = BotSummary("x")
    assert s.mean == 0.0 and s.sd == 0.0 and s.win_rate == 0.0
    assert s.pct_at_least(200) == 0.0


# --- end to end -------------------------------------------------------------

def test_evaluate_runs_and_renders():
    report = evaluate("greedy", ["random"] * 3, games=2, workers=None)
    assert len(report.results) == 2
    assert report.matchup == "greedy vs 3x random"
    text = format_report(report)
    assert "greedy" in text and "WIN%" in text


def test_mirror_matchup_is_labelled_as_one():
    report = evaluate("random", [], games=1, workers=None)
    assert report.matchup == "random mirror"
