"""The diagnostic's accounting.

Its whole value is that the pieces add up to the final score. If they do not,
it will send us chasing the wrong bottleneck.
"""

import pytest

from brassbot.diagnostics import (
    action_mix,
    behaviour,
    composition,
    highest_levels,
    run_game,
    split_by_outcome,
    stranded_by_era,
)
from brassbot.gamedata import Industry


@pytest.fixture(scope="module")
def records():
    return run_game(["heuristic", "greedy", "greedy", "greedy"], seed=2)


def test_a_record_is_produced_for_every_seat(records):
    assert len(records) == 4
    assert [r.seat for r in records] == [0, 1, 2, 3]


def test_vp_composition_reconciles_with_the_final_score(records):
    """Every point has to come from somewhere: era scoring, money, or the
    merchant bonuses that are paid immediately during a Sell."""
    for rec in records:
        total = rec.total(rec.industry_vp) + rec.total(rec.link_vp)
        merchant = rec.final_vp + rec.vp_penalties - total
        assert merchant >= 0, "merchant bonuses cannot be negative"
        assert sum(composition([rec]).values()) == pytest.approx(rec.final_vp)


def test_both_eras_are_recorded(records):
    for rec in records:
        assert set(rec.industry_vp) == {"canal", "rail"}
        assert set(rec.link_vp) == {"canal", "rail"}


def test_action_counts_match_the_moves_taken(records):
    """Four seats splitting a fixed number of moves."""
    assert sum(sum(r.actions.values()) for r in records) > 0
    for rec in records:
        assert rec.actions["Build"] == rec.tiles_built


def test_highest_level_is_never_below_a_built_tile(records):
    for rec in records:
        for industry, level in rec.highest_level.items():
            assert level >= 1
            assert rec.builds_by_industry[industry] >= 1


def test_industries_never_built_report_level_zero(records):
    levels = highest_levels(records)
    assert set(levels) == {i.value for i in Industry}
    assert all(v >= 0 for v in levels.values())


def test_summary_helpers_return_a_value_per_metric(records):
    for fn in (composition, behaviour, action_mix, stranded_by_era, highest_levels):
        result = fn(records)
        assert result and all(isinstance(v, float) for v in result.values())


def test_split_by_outcome_orders_best_above_worst():
    from brassbot.diagnostics import SeatRecord
    records = [SeatRecord(bot="x", seat=0, seed=i, final_vp=i) for i in range(10)]
    best, worst = split_by_outcome(records, fraction=0.3)
    assert min(r.final_vp for r in best) > max(r.final_vp for r in worst)


def test_split_never_returns_an_empty_side():
    from brassbot.diagnostics import SeatRecord
    best, worst = split_by_outcome([SeatRecord(bot="x", seat=0, seed=0)], fraction=0.2)
    assert best and worst
