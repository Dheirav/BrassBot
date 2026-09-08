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
  bots/              players. heuristic, planner, greedy, random, book, learned
    archive/         retired bots, out of REGISTRY but still importable and tested
  planner.py         beam search over sequences, used by bots/planner_bot.py
  evaluate.py        run matchups, rotate seats, report distributions
  yardstick.py       compare play against expert bands, not against our bots
  features.py        feature vectors, for the learned-value experiments
tools/               command line entry points (see README for usage)
  serve.py           the playable UI's server: one game in a module dict
  ui/index.html      the whole client -- one file, inline SVG, no build step
  play.py            the same game one move at a time, for a shell or an agent
  verify-weight.py   the measurement that decides what ships
  regime-split.py    the same, partitioned by a board feature (mode-selection)
tests/               205 tests; several pin rules that agents found broken
```

Note what is NOT covered by tests: everything in `tools/`. The UI is verified by
driving a real browser against a real server (Playwright), not by unit tests.

## How one decision flows

1. `engine.legal_actions(state)` builds the move list. This is where most rules
   live, and where most bugs have been found -- **a rule that is wrong here is
   invisible to self-play**, because the bot only ever plays what it is offered.
2. The bot picks one. `HeuristicBot.choose` clones the state, applies each
   candidate, and scores the result with `position_value`.
3. `position_value` = our `player_value` minus `rival` x the best opponent's.
   `player_value` is the whole evaluation: 37 weighted terms, several of which
   carry per-player-count overrides in `PROFILES`.
4. `engine.apply_action(state, action)` mutates the real state, and may end the
   turn, the round or the era.

`BeamPlanner` sits on top: it searches *sequences* of actions rather than one,
scoring each line with the same evaluation and playing the first action of the
best line.

It used to be much stronger. Since `pair_search` gave the heuristic an exact
two-ply search inside its own turn, the planner's edge is **+3.09 +- 0.96**
(three blocks, 180 seat-balanced games, chi2 = 0.64 on 2 df) -- down from
+14.78. It is also drastically slower: a 60-game duel runs over an hour where
the heuristic plays 200 games in minutes. Treat it as a research baseline, not
a target to distil.

## Where to change what

| you want to | edit |
| --- | --- |
| fix or add a rule | `engine.py` (usually `legal_*`), then a test |
| change what a position is worth | `HeuristicBot.player_value` in `bots/heuristic.py` |
| change how far the bot looks | `planner.py`, or `pair_search` in `bots/heuristic.py` |
| change resource sourcing | `resources.py` |
| add a measurement | `evaluate.py`, or a script in `tools/` |
| change what the UI shows | `snapshot()` in `tools/serve.py`, then `draw()` in `tools/ui/index.html` |

## The UI

`tools/serve.py` holds **one game in a module-level `GAME` dict** and serves
`snapshot()` as JSON; `tools/ui/index.html` is the entire client. There is no
build step, no framework and no external asset -- it is served as one file.

Four things about it are load-bearing:

**A move is sent as an INDEX into `legal_actions()`, which the server
regenerates on every request.** Two tabs on one game, or a click racing an undo,
once applied a still-in-range index to a different list and played an action
nobody chose, silently. Every request now carries the snapshot `version` its
indices were drawn against and a mismatch is refused. **Any new endpoint taking
an index needs the same guard.**

**The board is three SVG layers.** `<defs>` holds gradients and filters and is
never re-serialised, so their ids stay stable; `#lay-live` is rebuilt wholesale
on every state change; `#lay-fx` is not, which is the only reason a hover ghost
can exist. Assigning `innerHTML` destroys the focused node, so `draw()` records
which target held focus and restores it -- without that, keyboard play is
impossible.

**Clicks and hovers are delegated from the SVG root** via
`e.target.closest('[data-act]')`, because `event.target` is always the inner
shape and never the group.

**The server is stateful and shared.** Two browser tabs, and any script driving
it, are playing the same game. A test that plays moves changes what the next
test sees -- which has produced "bugs" that were only an exhausted board.

Undo rewinds *past* the bots' replies, so taking a move back after seeing what
they did leaks information a real game would not. That is right for analysis and
wrong for honest play; it is a property of the tool, not a defect.

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
