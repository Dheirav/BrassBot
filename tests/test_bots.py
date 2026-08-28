"""Bot contract and the heuristic evaluation.

The evaluation is tuned numerically, so these tests pin its *shape* -- the
orderings that must hold whatever the weights are -- rather than any particular
number, which tuning is free to move.
"""

import pytest

from brassbot.bots import REGISTRY, GreedyBot, HeuristicBot, RandomBot, make
from brassbot.engine import flip_tile, legal_actions
from brassbot.gamedata import Era, Industry
from brassbot.state import Tile, new_game


@pytest.fixture
def game():
    return new_game(4, seed=5)


def place(state, town, slot, owner, industry, level, *, flipped=False, resources=0):
    state.tiles[town][slot] = Tile(owner=owner, industry=industry, level=level,
                                   era_built=Era.CANAL, flipped=flipped,
                                   resources=resources)


def snapshot(state):
    """Everything a bot must leave untouched while it thinks."""
    return (
        [(p.money, p.vp, p.income_space, len(p.hand), len(p.discard), p.links_left)
         for p in state.players],
        sorted((t, s, tile.owner, tile.level, tile.flipped, tile.resources)
               for t, s, tile in state.all_tiles()),
        dict(state.links), state.coal, state.iron, len(state.deck),
        state.turn_pos, state.actions_left, state.era, state.round,
        state.rng.getstate(),
    )


# --- registry ---------------------------------------------------------------

def test_registry_exposes_every_bot():
    assert set(REGISTRY) == {"random", "greedy", "heuristic", "mcts", "book", "commit",
                             "learned"}


def test_make_builds_a_bare_name():
    assert isinstance(make("greedy"), GreedyBot)
    assert isinstance(make("random"), RandomBot)


def test_make_keeps_counts_as_integers():
    """Some parameters are counts, and a float count breaks range() and slicing."""
    bot = make("mcts:iterations=100,c=1.5")
    assert bot.p["iterations"] == 100 and isinstance(bot.p["iterations"], int)
    assert isinstance(bot.p["c"], float)


def test_make_applies_weight_overrides():
    bot = make("heuristic:income=0.25,debt=0.9")
    assert bot.w["income"] == 0.25
    assert bot.w["debt"] == 0.9
    assert bot.w["money"] == HeuristicBot.DEFAULTS["money"]  # untouched


def test_make_rejects_an_unknown_bot():
    with pytest.raises(KeyError):
        make("nonesuch")


def test_heuristic_rejects_an_unknown_weight():
    with pytest.raises(KeyError):
        make("heuristic:not_a_weight=1")


# --- contract ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["random", "greedy", "heuristic"])
def test_bots_return_a_legal_action(game, name):
    actions = legal_actions(game)
    assert make(name, seed=1).choose(game, actions) in actions


@pytest.mark.parametrize("name", ["random", "greedy", "heuristic"])
def test_bots_do_not_mutate_the_state_they_are_shown(game, name):
    """The state is passed live, not cloned. A bot that looks ahead must clone
    it itself -- and must leave the real game exactly as it found it."""
    actions = legal_actions(game)
    before = snapshot(game)
    make(name, seed=1).choose(game, actions)
    assert snapshot(game) == before


@pytest.mark.parametrize("name", ["random", "greedy", "heuristic"])
def test_bots_are_deterministic_for_a_given_seed(game, name):
    actions = legal_actions(game)
    assert make(name, seed=3).choose(game, actions) == make(name, seed=3).choose(game, actions)


# --- shape of the evaluation ------------------------------------------------

def test_a_flipped_tile_is_worth_more_than_an_unflipped_one(game):
    """Flipped through the engine, so the income the flip pays is included --
    that income is most of why flipping is worth chasing."""
    bot = HeuristicBot()
    place(game, "birmingham", 0, 0, Industry.COTTON_MILL, 1, flipped=False)
    unflipped = bot.player_value(game, 0)
    flip_tile(game, game.tiles["birmingham"][0])
    assert bot.player_value(game, 0) > unflipped


def test_income_is_worth_more_earlier_in_the_game(game):
    """A point of income pays out every remaining round, so the same income is
    worth more in the Canal Era than at the end of the Rail Era."""
    bot = HeuristicBot()
    game.players[0].income_space = 30
    early = bot.player_value(game, 0)

    late = game.clone()
    late.era = Era.RAIL
    late.round = late.rounds_this_era
    assert bot.player_value(late, 0) < early


def test_negative_income_is_penalised_beyond_the_linear_term(game):
    """Debt is worse than symmetric: unpayable income sells your tiles off."""
    bot = HeuristicBot()
    p = game.players[0]
    p.income_space = 10  # level 0
    neutral = bot.player_value(game, 0)
    p.income_space = 4   # level -6
    down_six = neutral - bot.player_value(game, 0)

    p.income_space = 16  # level +3
    up_three = bot.player_value(game, 0) - neutral
    assert down_six / 6 > up_three / 3


def test_being_broke_is_worse_than_the_missing_money_alone(game):
    """Zero money removes nearly every action, so the value of cash is steepest
    near zero."""
    bot = HeuristicBot()
    p = game.players[0]
    p.money = 0
    broke = bot.player_value(game, 0)
    p.money = 10
    solvent = bot.player_value(game, 0)
    p.money = 60
    rich = bot.player_value(game, 0)
    assert (solvent - broke) / 10 > (rich - solvent) / 50


def test_stranded_canal_only_tiles_are_penalised_only_in_the_rail_era(game):
    """A level 1 tile cannot be built once the era turns, so it blocks every
    higher level of that industry."""
    bot = HeuristicBot()
    canal = bot.player_value(game, 0)
    game.era = Era.RAIL
    assert bot.player_value(game, 0) < canal


def test_position_value_counts_a_rivals_strength_against_us(game):
    """Draining an opponent's mine flips their tile and pays them income, so a
    bot that ignored opponents would happily do them favours."""
    bot = HeuristicBot()
    alone = bot.position_value(game, 0)
    game.players[1].vp += 50
    assert bot.position_value(game, 0) < alone


def test_rounds_left_falls_as_the_game_runs_out(game):
    bot = HeuristicBot()
    canal_start = bot.rounds_left(game)
    rail = game.clone()
    rail.era = Era.RAIL
    rail.round = rail.rounds_this_era
    assert bot.rounds_left(rail) < canal_start
    assert bot.rounds_left(rail) == 0


# --- era boundary -----------------------------------------------------------

def test_an_unflipped_level_1_tile_is_worth_less_as_the_canal_era_closes(game):
    """Level 1 tiles are removed at the end of the Canal Era. One built late and
    not yet flipped is deleted having scored nothing -- measured at 1.36 tiles
    per player per game before this term existed."""
    bot = HeuristicBot()
    place(game, "birmingham", 0, 0, Industry.COTTON_MILL, 1)

    game.round = 1
    early = bot.player_value(game, 0)
    game.round = game.rounds_this_era
    assert bot.player_value(game, 0) < early


def test_the_canal_deadline_bites_level_1_harder_than_level_2(game):
    """Level 2+ tiles survive the wipe, so the closing Canal round is not a
    deadline for them. Both still ease off as the game shortens -- income has
    fewer rounds left to pay out in -- so the test is the *relative* fall."""
    bot = HeuristicBot()

    def fall(level):
        board = game.clone()
        place(board, "birmingham", 0, 0, Industry.COTTON_MILL, level)
        board.round = 1
        early = bot.player_value(board, 0)
        board.round = board.rounds_this_era
        return early - bot.player_value(board, 0)

    assert fall(1) > fall(2)


def test_the_deadline_applies_to_every_tile_in_the_rail_era(game):
    """At the end of the Rail Era the game simply stops, so nothing unflipped is
    worth anything -- level 2+ included."""
    bot = HeuristicBot()
    game.era = Era.RAIL
    place(game, "birmingham", 0, 0, Industry.COTTON_MILL, 2)

    game.round = 1
    early = bot.player_value(game, 0)
    game.round = game.rounds_this_era
    assert bot.player_value(game, 0) < early


# --- per-format profiles ----------------------------------------------------

@pytest.fixture
def clean_profiles():
    saved = dict(HeuristicBot.PROFILES)
    HeuristicBot.PROFILES.clear()
    yield HeuristicBot.PROFILES
    HeuristicBot.PROFILES.clear()
    HeuristicBot.PROFILES.update(saved)


def test_without_a_profile_a_format_gets_the_defaults(clean_profiles):
    bot = HeuristicBot()
    for players in (2, 3, 4):
        assert bot.weights_for(players) == HeuristicBot.DEFAULTS


def test_a_profile_applies_only_to_its_own_player_count(clean_profiles):
    clean_profiles[2] = {"income": 0.9}
    bot = HeuristicBot()
    assert bot.weights_for(2)["income"] == 0.9
    assert bot.weights_for(4)["income"] == HeuristicBot.DEFAULTS["income"]
    # everything else in the 2p profile still comes from the defaults
    assert bot.weights_for(2)["money"] == HeuristicBot.DEFAULTS["money"]


def test_explicit_weights_beat_the_profile(clean_profiles):
    """A tuning run pins the weights it is testing, so its overrides have to win
    -- otherwise the profile would silently overwrite the candidate."""
    clean_profiles[2] = {"income": 0.9}
    bot = HeuristicBot(income=0.01)
    assert bot.weights_for(2)["income"] == 0.01


def test_choosing_a_move_uses_the_profile_for_that_player_count(clean_profiles):
    """The bot only learns the player count from the state it is handed."""
    from brassbot.engine import legal_actions

    clean_profiles[3] = {"pass_bias": -99.0}
    bot = HeuristicBot()
    three = new_game(3, seed=2)
    bot.choose(three, legal_actions(three))
    assert bot.w["pass_bias"] == -99.0

    four = new_game(4, seed=2)
    bot.choose(four, legal_actions(four))
    assert bot.w["pass_bias"] == HeuristicBot.DEFAULTS["pass_bias"]


def test_commit_bot_with_no_commitment_is_the_plain_heuristic():
    """The control arm has to be a real control.

    If commit=-1 diverged from the heuristic even slightly, the whole ceiling
    measurement would be comparing two different bots rather than isolating the
    effect of committing.
    """
    from brassbot.engine import apply_action, legal_actions

    for seed in (0, 3):
        a, b = new_game(4, seed=seed), new_game(4, seed=seed)
        plain = make("heuristic:commit=-1")
        control = make("commit:commit=-1")
        while not a.finished:
            assert repr(plain.choose(a, legal_actions(a))) == \
                   repr(control.choose(b, legal_actions(b)))
            apply_action(a, plain.choose(a, legal_actions(a)))
            apply_action(b, control.choose(b, legal_actions(b)))
        assert [p.vp for p in a.players] == [p.vp for p in b.players]
