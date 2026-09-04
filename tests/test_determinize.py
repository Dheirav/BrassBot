"""Sampling the cards we cannot see.

`determinize` lived in `bots/mcts.py` until that bot was retired for losing to
the evaluation it searched with. The sampling was never what was wrong with it,
and `bots/planner_bot.py` still depends on it, so these tests moved here rather
than being deleted alongside.
"""

import random

import pytest

from brassbot.bots import make
from brassbot.engine import apply_action, legal_actions
from brassbot.state import determinize, new_game
from tests.test_bots import snapshot


@pytest.fixture
def game():
    state = new_game(4, seed=5)
    bot = make("greedy")
    for _ in range(20):  # get off the opening, where hands dominate
        apply_action(state, bot.choose(state, legal_actions(state)))
    return state


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
