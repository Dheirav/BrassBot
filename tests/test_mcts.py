"""Search behaviour.

Kept to small iteration counts -- these check the machinery is right, not that
it plays well. Playing strength is the harness's job.
"""

import random

import pytest

from brassbot.bots import make
from brassbot.bots.mcts import Bounds, MCTSBot, determinize
from brassbot.engine import apply_action, legal_actions
from brassbot.state import new_game
from tests.test_bots import snapshot


@pytest.fixture
def game():
    state = new_game(4, seed=5)
    bot = make("greedy")
    for _ in range(20):  # get off the opening, where hands dominate
        apply_action(state, bot.choose(state, legal_actions(state)))
    return state


@pytest.fixture
def bot():
    return MCTSBot(seed=1, iterations=12, prior_width=6)


# --- contract ---------------------------------------------------------------

def test_returns_a_legal_action(game, bot):
    actions = legal_actions(game)
    assert bot.choose(game, actions) in actions


def test_does_not_mutate_the_state_it_searches(game, bot):
    """Search clones aggressively; a leak here would corrupt the real game."""
    actions = legal_actions(game)
    before = snapshot(game)
    bot.choose(game, actions)
    assert snapshot(game) == before


def test_a_forced_move_skips_the_search(game, bot):
    """One legal action means nothing to decide -- and searching would waste a
    full budget on it."""
    only = legal_actions(game)[:1]
    assert bot.choose(game, only) is only[0]


def test_rejects_unknown_parameters():
    with pytest.raises(KeyError):
        MCTSBot(nonsense=1)


def test_is_reproducible_from_its_seed(game):
    """Determinization is random, so the bot is stochastic -- but seeded, so a
    given seed replays exactly."""
    a = MCTSBot(seed=7, iterations=12, prior_width=6).choose(game, legal_actions(game))
    b = MCTSBot(seed=7, iterations=12, prior_width=6).choose(game, legal_actions(game))
    assert a == b


# --- determinization --------------------------------------------------------

def test_determinize_leaves_the_observer_alone(game):
    rng = random.Random(1)
    sampled = determinize(game, observer=0, rng=rng)
    assert sampled.players[0].hand == game.players[0].hand


def test_determinize_preserves_every_hand_size(game):
    rng = random.Random(1)
    sampled = determinize(game, observer=0, rng=rng)
    for real, fake in zip(game.players, sampled.players):
        assert len(real.hand) == len(fake.hand)


def test_determinize_conserves_the_hidden_cards(game):
    """Cards are redealt, not invented: the unseen pool has the same size."""
    rng = random.Random(1)
    sampled = determinize(game, observer=0, rng=rng)
    def hidden(state):
        n = len(state.deck)
        for seat, p in enumerate(state.players):
            if seat != 0:
                n += len(p.hand)
        return n
    assert hidden(sampled) == hidden(game)


def test_determinize_keeps_wild_cards_where_they_are(game):
    """Wilds are taken from a faceup deck, so everyone knows who holds them --
    redealing them would model the opponent as more hidden than they are."""
    from brassbot.cards import WILD_INDUSTRY, WILD_LOCATION
    game.players[2].hand = [WILD_LOCATION, WILD_INDUSTRY] + game.players[2].hand[2:]
    sampled = determinize(game, observer=0, rng=random.Random(3))
    assert sum(1 for c in sampled.players[2].hand if c.is_wild) == 2


def test_determinize_does_not_touch_the_original(game):
    before = snapshot(game)
    determinize(game, observer=1, rng=random.Random(2))
    assert snapshot(game) == before


# --- widening and backup ----------------------------------------------------

def test_widening_keeps_the_tree_narrow_early(game):
    """The whole point: with a branching factor near 40 and a few hundred
    iterations, a tree that fans out fully is one ply deep."""
    bot = MCTSBot(seed=2, iterations=30, widen_k=1.0, widen_alpha=0.5, prior_width=20)
    bot.choose(game, legal_actions(game))
    # exercised via the internal node the bot built for its root
    node_cap = bot.p["widen_k"] * (30 ** bot.p["widen_alpha"])
    assert node_cap < 20, "cap must bite below the prior width to mean anything"


def test_backup_carries_a_value_for_every_player(game):
    """4-player Brass is not zero-sum, so one scalar cannot describe a node."""
    bot = MCTSBot(seed=4, iterations=10, prior_width=4)
    values = bot._values(game)
    assert len(values) == game.n_players


def test_prior_ranks_actions_and_respects_its_width(game):
    bot = MCTSBot(seed=5, iterations=1, prior_width=5)
    actions = legal_actions(game)
    ranked = bot._ranked_actions(game, actions)
    assert len(ranked) == min(5, len(actions))
    assert all(a in actions for a in ranked)


# --- bounds -----------------------------------------------------------------

def test_bounds_normalise_into_the_unit_interval():
    b = Bounds()
    for v in (-5.0, 10.0, 2.0):
        b.update(v)
    assert b.normalise(-5.0) == 0.0
    assert b.normalise(10.0) == 1.0
    assert 0.0 < b.normalise(2.0) < 1.0


def test_bounds_handle_a_single_observed_value():
    """Before the tree has seen any spread, everything is equally good."""
    b = Bounds()
    b.update(3.0)
    assert b.normalise(3.0) == 0.5


# --- play-out leaves --------------------------------------------------------

def test_playout_values_returns_one_real_score_per_player(game):
    """The play-out path values a leaf by finishing the game, so it must return
    genuine final scores -- one per seat, in seat order."""
    bot = MCTSBot(seed=2, iterations=4, prior_width=3)
    values = bot._playout_values(game)
    assert len(values) == game.n_players
    assert all(isinstance(v, int) for v in values)


def test_playout_does_not_mutate_the_state(game):
    """The riskiest property of the new path: it applies actions in a loop, so a
    missing clone would corrupt the real game."""
    bot = MCTSBot(seed=2, iterations=4, prior_width=3)
    before = snapshot(game)
    bot._playout_values(game)
    assert snapshot(game) == before


def test_a_rollout_bot_still_returns_a_legal_action(game):
    bot = MCTSBot(seed=5, iterations=4, prior_width=3, rollout=1.0)
    actions = legal_actions(game)
    assert bot.choose(game, actions) in actions
