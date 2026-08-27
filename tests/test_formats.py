"""Every player count must work, not just 4.

Deck size, merchant tiles in play, rounds per era and the action budget all
change with player count, so each is a genuinely different game.
"""

import pytest

from brassbot.bots import make
from brassbot.engine import apply_action, legal_actions
from brassbot.evaluate import evaluate, play_game
from brassbot.gamedata import load
from brassbot.state import ROUNDS_PER_ERA, new_game

# Actions available to one player across the whole game: two per round over both
# eras, less one for the single-action opening round.
ACTION_BUDGET = {n: ROUNDS_PER_ERA[n] * 2 * 2 - 1 for n in (2, 3, 4)}


@pytest.mark.parametrize("players", [2, 3, 4])
def test_a_full_game_completes(players):
    result = play_game(["heuristic"] * players, seed=1, n_players=players)
    assert len(result.scores) == players
    assert result.winners


@pytest.mark.parametrize("players,budget", sorted(ACTION_BUDGET.items()))
def test_total_moves_match_the_action_budget(players, budget):
    """39 / 35 / 31 actions each at 2 / 3 / 4 players. This is the constraint the
    whole game runs on, so it is worth pinning."""
    assert budget == {2: 39, 3: 35, 4: 31}[players]
    result = play_game(["greedy"] * players, seed=2, n_players=players)
    assert result.moves == budget * players


@pytest.mark.parametrize("players,size", [(2, 40), (3, 54), (4, 64)])
def test_setup_uses_the_right_deck(players, size):
    state = new_game(players, seed=1)
    dealt = sum(len(p.hand) + len(p.discard) for p in state.players)
    assert dealt + len(state.deck) == size


@pytest.mark.parametrize("players,merchants", [(2, 3), (3, 4), (4, 5)])
def test_setup_uses_the_right_merchants(players, merchants):
    state = new_game(players, seed=1)
    assert len(state.merchants) == merchants
    slots = sum(len(v) for v in state.merchants.values())
    assert slots == len(load().merchant_tiles_for(players))


@pytest.mark.parametrize("players", [2, 3, 4])
def test_every_bot_can_play_every_format(players):
    for name in ("random", "greedy", "heuristic"):
        result = play_game([name] * players, seed=3, n_players=players)
        assert sum(result.scores) >= 0


@pytest.mark.parametrize("players", [2, 3, 4])
def test_the_harness_runs_at_every_player_count(players):
    report = evaluate("greedy", ["random"] * (players - 1), games=1,
                      workers=None, n_players=players)
    assert len(report.results[0].scores) == players


# --- determinism ------------------------------------------------------------

@pytest.mark.parametrize("players", [2, 3, 4])
def test_the_same_seed_reproduces_the_same_game(players):
    a = play_game(["heuristic"] * players, seed=7, n_players=players)
    b = play_game(["heuristic"] * players, seed=7, n_players=players)
    assert a == b


def test_the_heuristic_bot_ignores_its_own_seed():
    """It is strictly deterministic: the position decides the move, so two
    instances seeded differently must still agree."""
    state = new_game(4, seed=11)
    actions = legal_actions(state)
    picks = {make("heuristic", seed=k).choose(state, actions) for k in range(6)}
    assert len(picks) == 1


def test_determinism_holds_all_the_way_through_a_game():
    """Not just the opening -- drift would only show up deep in a game."""
    def run():
        state = new_game(3, seed=13)
        bot = make("heuristic")
        trace = []
        while not state.finished:
            action = bot.choose(state, legal_actions(state))
            trace.append(repr(action))
            apply_action(state, action)
        return trace

    assert run() == run()
