"""The expert-profile yardstick.

This is the only measurement in the project that does not reference our own
bots, so its arithmetic and its provenance both need pinning.
"""

import pytest

from brassbot.diagnostics import SeatRecord
from brassbot.yardstick import ACTION_BUDGET, PROFILE, Band, Gap, evaluate, summarise


def record(**kw):
    rec = SeatRecord(bot="x", seat=0, seed=0)
    for key, value in kw.items():
        setattr(rec, key, value)
    return rec


# --- gaps -------------------------------------------------------------------

def band(low, high):
    return Band("k", "label", low, high, "source", lambda rs: 0.0)


def test_a_value_inside_the_band_has_no_gap():
    g = Gap(band(2, 4), 3.0)
    assert g.inside and g.direction == "ok" and g.distance == 0.0


def test_the_band_edges_count_as_inside():
    assert Gap(band(2, 4), 2.0).inside
    assert Gap(band(2, 4), 4.0).inside


def test_distance_is_measured_in_band_widths():
    assert Gap(band(2, 4), 1.0).distance == pytest.approx(0.5)   # 1 below a width of 2
    assert Gap(band(2, 4), 6.0).distance == pytest.approx(1.0)   # 2 above


def test_direction_names_which_side_we_are_on():
    assert Gap(band(2, 4), 1.0).direction == "low"
    assert Gap(band(2, 4), 9.0).direction == "high"


def test_a_zero_width_band_still_measures_a_gap():
    """'No developing in the Rail Era' is a point, not a range, so it has no
    natural scale to divide by."""
    g = Gap(band(0, 0), 3.0)
    assert not g.inside
    assert g.distance == pytest.approx(3.0)


# --- profile ----------------------------------------------------------------

def test_every_band_cites_a_source():
    """These numbers come from outside the project; an uncited one would be an
    invented target dressed up as ground truth."""
    for b in PROFILE:
        assert b.source and len(b.source) > 15, b.key


def test_bands_are_well_formed():
    keys = [b.key for b in PROFILE]
    assert len(keys) == len(set(keys))
    for b in PROFILE:
        assert b.low <= b.high, b.key


def test_evaluate_returns_one_gap_per_band():
    gaps = evaluate([record(final_vp=100)])
    assert len(gaps) == len(PROFILE)


def test_vp_per_action_uses_the_right_budget_for_the_format():
    """39 / 35 / 31 actions at 2 / 3 / 4 players -- the same score is a very
    different efficiency depending on how many actions bought it."""
    recs = [record(final_vp=100)]
    by_key = {g.band.key: g.value for g in evaluate(recs, players=4)}
    assert by_key["vp_per_action"] == pytest.approx(100 / ACTION_BUDGET[4])
    by_key2 = {g.band.key: g.value for g in evaluate(recs, players=2)}
    assert by_key2["vp_per_action"] == pytest.approx(100 / ACTION_BUDGET[2])
    assert by_key2["vp_per_action"] < by_key["vp_per_action"]


def test_industry_share_splits_tile_vp_from_link_vp():
    recs = [record(industry_vp={"canal": 30, "rail": 30},
                   link_vp={"canal": 20, "rail": 20})]
    share = {g.band.key: g.value for g in evaluate(recs)}["industry_share"]
    assert share == pytest.approx(0.6)


def test_industry_share_survives_a_scoreless_game():
    recs = [record(industry_vp={}, link_vp={})]
    assert {g.band.key: g.value for g in evaluate(recs)}["industry_share"] == 0.0


# --- summary ----------------------------------------------------------------

def test_summarise_counts_bands_met_and_averages_the_rest():
    gaps = [Gap(band(0, 10), 5.0), Gap(band(0, 10), 5.0), Gap(band(0, 10), 20.0)]
    inside, distance = summarise(gaps)
    assert inside == 2
    assert distance == pytest.approx(1.0 / 3)  # only the third is outside, by 1w


def test_a_perfect_profile_scores_zero_distance():
    gaps = [Gap(band(0, 10), 5.0) for _ in range(4)]
    assert summarise(gaps) == (4, 0.0)


def test_empty_records_do_not_explode():
    gaps = evaluate([])
    assert len(gaps) == len(PROFILE)
    summarise(gaps)
