"""The evaluation's fast paths must agree exactly with the slow ones.

`position_value` optimises by computing work once and sharing it: the merchant
context, and the board walked once and bucketed by owner. `player_value` still
accepts neither, in which case it derives both itself. Those two routes must
produce bit-identical numbers, or the bot silently plays differently from what
every measurement in this project assumed.

This is the check that has caught real mistakes here. A refactor that looked
correct, read correctly, and passed the whole suite turned out to change the
evaluation; and a later one that looked identically correct did not. Reading the
diff could not tell them apart -- only running both routes on the same state
could.

**What this cannot catch.** It compares two routes, so it only sees a bug that
makes them *disagree*. Verified by injecting two faults: dropping flipped tiles
from the owner buckets failed 7 of the 8 tests, while forcing `merchant_beer` to
False passed all 8 -- because that fault lives after the context is unpacked, so
both routes execute it and agree on the same wrong answer. This file guards the
optimisation, not the evaluation's correctness. Terms are covered by
`tests/test_bots.py`, which pins their shape against play.

**Extend this file when adding a faster path.** The pattern is: implement the
slow, obviously-correct route; implement the fast one; assert they agree over
many real positions. Delta evaluation -- reusing a base value and applying only
what an action changed -- is the next such path, and belongs here rather than in
a one-off script.
"""

import pytest

from brassbot.bots import make
from brassbot.bots.heuristic import HeuristicBot
from brassbot.engine import apply_action, legal_actions
from brassbot.gamedata import Era
from brassbot.state import new_game

# Every weight non-zero, so terms that ship at 0 -- and are therefore skipped by
# their guards in normal play -- are still exercised here.
ALL_TERMS_ON = dict(
    money_compounding=0.01, wild_card=1.0, hand_breadth=0.1, site_urgency=0.2,
)


def positions(players=4, seeds=(1, 7), every=7, bot="greedy"):
    """Real positions from real games, sampled across both eras."""
    out = []
    for seed in seeds:
        state = new_game(players, seed=seed)
        driver = make(bot, seed=seed)
        for step in range(200):
            actions = legal_actions(state)
            if not actions or state.finished:
                break
            apply_action(state, driver.choose(state, actions))
            if step % every == 0:
                out.append(state.clone())
    return out


def reference_player_value(bot, state, seat):
    """The slow route: no shared context, no pre-bucketed tiles."""
    bot.w = bot.weights_for(state.n_players)
    return bot.player_value(state, seat)


def reference_position_value(bot, state, me):
    """The slow route for a whole position, mirroring position_value's own
    arithmetic but deriving every input from scratch."""
    bot.w = bot.weights_for(state.n_players)
    mine = reference_player_value(bot, state, me)
    rivals = [reference_player_value(bot, state, i)
              for i in range(state.n_players) if i != me]
    return mine - bot.w["rival"] * (max(rivals) if rivals else 0.0)


def fast_player_values(bot, state):
    """The fast route: context and owner buckets computed once and shared."""
    bot.w = bot.weights_for(state.n_players)
    context = bot._sale_context(state)
    owned = bot.tiles_by_owner(state)
    return [bot.player_value(state, i, context, owned[i])
            for i in range(state.n_players)]


# --- the invariant ----------------------------------------------------------

@pytest.mark.parametrize("players", [2, 3, 4])
def test_shared_context_and_buckets_change_nothing(players):
    bot = HeuristicBot()
    states = positions(players=players, seeds=(3,))
    assert len(states) > 5, "need a real sample of positions"
    for state in states:
        fast = fast_player_values(bot, state)
        for seat in range(players):
            assert fast[seat] == reference_player_value(bot, state, seat)


def test_position_value_matches_the_slow_route():
    bot = HeuristicBot()
    for state in positions():
        for me in range(state.n_players):
            assert bot.position_value(state, me) == reference_position_value(bot, state, me)


def test_holds_with_every_term_switched_on():
    """Several weights ship at 0 and are skipped by guards, so normal play never
    executes those branches. This is the only place they run."""
    bot = HeuristicBot(**ALL_TERMS_ON)
    for state in positions(seeds=(11,)):
        fast = fast_player_values(bot, state)
        for seat in range(state.n_players):
            assert fast[seat] == reference_player_value(bot, state, seat)


def test_holds_in_both_eras():
    seen = set()
    bot = HeuristicBot()
    for state in positions(seeds=(2, 5), every=5):
        seen.add(state.era)
        fast = fast_player_values(bot, state)
        for seat in range(state.n_players):
            assert fast[seat] == reference_player_value(bot, state, seat)
    assert seen == {Era.CANAL, Era.RAIL}, f"only sampled {seen}"


def test_holds_on_positions_a_searching_bot_reaches():
    """The heuristic and greedy reach different boards; the fast path has to hold
    on whatever the search actually visits."""
    bot = HeuristicBot()
    for state in positions(seeds=(4,), bot="heuristic", every=9):
        fast = fast_player_values(bot, state)
        for seat in range(state.n_players):
            assert fast[seat] == reference_player_value(bot, state, seat)


def _delta_mismatches(n_players: int, seed: int, limit: int = 400):
    """Play a real game; at every decision compare the reused rival value
    against a full recomputation, for every candidate move.

    Returns (mismatches, fast_path_hits, candidates).
    """
    from brassbot.network import connected_locations

    bot = make("heuristic")
    state = new_game(n_players, seed=seed)
    mismatches, hits, total = [], 0, 0
    while not state.finished and total < limit:
        actions = legal_actions(state)
        me = state.current.idx
        bot.w = bot.weights_for(state.n_players)
        base_links = set(state.links)
        base_reachable = connected_locations(state, list(state.merchants))
        owned, _bsig = bot.scan_board(state)
        context = bot._sale_context(state, base_reachable)
        rivals = [bot.player_value(state, i, context, owned[i])
                  for i in range(state.n_players) if i != me]
        shared = (bot.shared_signature(state, me, owned),
                  max(rivals) if rivals else 0.0)

        for action in actions:
            probe = state.clone()
            apply_action(probe, action)
            reachable = base_reachable if set(probe.links) == base_links else None
            fast = bot.position_value(probe, me, reachable, shared)
            slow = bot.position_value(probe, me)
            total += 1
            po, _ps = bot.scan_board(probe)
            if bot.shared_signature(probe, me, po) == shared[0]:
                hits += 1
            if abs(fast - slow) > 1e-9:
                mismatches.append((action, fast, slow))
        apply_action(state, bot.choose(state, actions))
    return mismatches, hits, total


@pytest.mark.parametrize("n_players,seed", [(4, 25), (4, 1), (3, 7), (2, 3)])
def test_reused_rival_values_equal_a_full_recomputation(n_players, seed):
    """Delta evaluation must be exact, not merely close.

    Seed 25 is here because it caught the first version of this: the signature
    counted flipped tiles instead of naming them, and a build that overbuilt a
    flipped tile while its coal draw flipped another left the count unchanged.
    Every rival holding a link into that town lost icons unseen -- 3 VP to one
    of them -- and one game in thirty played differently.
    """
    mismatches, _hits, total = _delta_mismatches(n_players, seed)
    assert total > 0, "no candidates were evaluated"
    assert not mismatches, (
        f"{len(mismatches)} of {total} candidates disagree; first: "
        f"{mismatches[0][0]} fast={mismatches[0][1]:.6f} slow={mismatches[0][2]:.6f}"
    )
