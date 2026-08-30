# How the code fits together

Orientation for someone changing this project. `NEXT.md` records *what we
learned*; this records *where things are*.

## The shape of it

```
brassbot/            the game, and the bots that play it
  gamedata.py        static components: tiles, towns, links, markets, decks
  state.py           GameState, Player, Tile -- everything that changes
  actions.py         the seven action types, as frozen dataclasses
  engine.py          move generation, applying a move, era flow, scoring
  network.py         connectivity: what your network reaches, what is buildable
  resources.py       where coal/iron/beer come from, and what they cost
  bots/              players. heuristic, mcts, planner_bot, greedy, random
  planner.py         beam search over sequences, used by bots/planner_bot.py
  evaluate.py        run matchups, rotate seats, report distributions
  yardstick.py       compare play against expert bands, not against our bots
  features.py        feature vectors, for the learned-value experiments
tools/               command line entry points (see README for usage)
tests/               204 tests; several pin rules that agents found broken
```

## How one decision flows

1. `engine.legal_actions(state)` builds the move list. This is where most rules
   live, and where most bugs have been found -- **a rule that is wrong here is
   invisible to self-play**, because the bot only ever plays what it is offered.
2. The bot picks one. `HeuristicBot.choose` clones the state, applies each
   candidate, and scores the result with `position_value`.
3. `position_value` = our `player_value` minus `rival` x the best opponent's.
   `player_value` is the whole evaluation: about twenty weighted terms.
4. `engine.apply_action(state, action)` mutates the real state, and may end the
   turn, the round or the era.

`BeamPlanner` sits on top: it searches *sequences* of actions rather than one,
scoring each line with the same evaluation and playing the first action of the
best line. It is stronger and about 25x slower.

## Where to change what

| you want to | edit |
| --- | --- |
| fix or add a rule | `engine.py` (usually `legal_*`), then a test |
| change what a position is worth | `HeuristicBot.player_value` in `bots/heuristic.py` |
| change how far the bot looks | `planner.py`, or `bots/mcts.py` |
| change resource sourcing | `resources.py` |
| add a measurement | `evaluate.py`, or a script in `tools/` |

## Things that will bite you

**Move generation is the usual suspect.** Seventeen rules bugs have been found
here, none by self-play. Three separate times a "the bot plays this badly"
verdict turned out to be a legal move the generator never offered. Before
concluding the bot chose wrongly, check it was offered the alternative.

**The evaluation is not the objective.** `player_value` mixes real VP (tile and
link scores) with proxies for things not yet realised (income, liquidity, merchant
access). The proxies are numerically larger than the VP differences they decide.

**Weights are a tuned set, not independent knobs.** `tools/tune.py` fits them
together on one seed block and validates on another. A weight changed alone is
usually worse, and a weight tuned and reported on the same block is usually a
mirage -- both mistakes are recorded in `NEXT.md` with numbers.

**A mirror cannot see a symmetric change.** If a change helps every seat equally,
the mirror mean does not move; measure it head to head, one variant seat against
baseline opponents. Several real gains read as exactly zero in a mirror.

**Determinism is a requirement, not a nicety.** Sets of strings iterate in
hash order, which varies per process; `tests/test_determinism.py` pins it by
playing whole games in subprocesses under different `PYTHONHASHSEED`.

**Never change engine state at import.** `tools/play.py` once raised a move
generation constant at module scope, which silently changed how the bot played
in every analysis script that imported it.

## Seed blocks

Three disjoint blocks, and mixing them is how you fool yourself:

| block | for |
| --- | --- |
| 10000+ | tuning |
| 20000+ | validating a tuned result |
| 0+ | reporting |

An effect of 3 VP needs about 200 games an arm to see at all; at 24 games the
floor is 8.7 VP.
