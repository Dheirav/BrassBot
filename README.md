# BrassBot

A rules engine, bots, and a measurement harness for **Brass: Birmingham**
(Roxley, 2018).

The engine plays all three player counts. The strongest bot is a determinized
MCTS searching over a tuned position evaluation. Everything is measured against
a held-out seed block, and results that do not survive validation are recorded as
failures rather than shipped.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest pillow
PYTHONPATH=. .venv/bin/python -m pytest -q          # 175 tests
```

## Playing strength

4 players, against three heuristic bots, where an equal share of wins is 25%:

| agent | mean VP | win rate | VP per action |
| --- | --- | --- | --- |
| `random` | ~2 | 0% | 0.07 |
| `greedy` | ~35 | 25% | 1.1 |
| `heuristic` | 96 | 25% | 3.10 |
| `mcts`, 600 iterations | 112.8 | 57.5% | 3.64 |
| **`mcts`, 1500 iterations** | **115.6** | **66.7%** | **3.73** |
| *expert human* | *~155* | *-* | *~5.0* |

Per player count, mirror matches on held-out seeds:

| format | mean | VP/action |
| --- | --- | --- |
| 2p | 104.9 | 2.69 |
| 3p | 100.2 | 2.86 |
| 4p | 98.2 | 3.17 |

**On the target.** The project began aiming at 200+ VP in 4 players. That is not
reachable: across fifteen verified tournament games the winning scores run
142-184 with a median of 158, and none reach 200. Actions are capped at 31 per
player at 4p and experts convert them at ~5 VP each. The realistic target is
150-165; 200+ belongs to the 2-player game, which has 39 actions.
`docs/research-landscape.md` has the evidence.

## Using it

```bash
# measure a matchup: seats rotated, full score distribution, drawn wins split
PYTHONPATH=. .venv/bin/python tools/evaluate.py mcts -o heuristic -n 100 -w 4

# where a bot's points come from, and what separates its good games from its bad
PYTHONPATH=. .venv/bin/python tools/diagnose.py heuristic -n 60 -w 4

# how far its play is from expert human play, on 11 measured dimensions
PYTHONPATH=. .venv/bin/python tools/yardstick.py heuristic -n 40 --sources

# tune weights by playing: tune on one seed block, validate on another
PYTHONPATH=. .venv/bin/python tools/tune.py -b heuristic -o greedy -n 60 -w 4

# one game, round by round, for debugging the engine
PYTHONPATH=. .venv/bin/python tools/playout.py heuristic -s 3
```

## Layout

| Path | What |
| --- | --- |
| `brassbot/gamedata.py` | The printed components: tiles, board, markets, income track |
| `brassbot/state.py` | Game state, setup, cloning |
| `brassbot/network.py` | Connectivity — "your network" vs "connected" |
| `brassbot/resources.py` | Coal / iron / beer sourcing and consumption |
| `brassbot/engine.py` | Move generation, application, era flow, scoring |
| `brassbot/bots/` | `random`, `greedy`, `heuristic`, `mcts`, `book` |
| `brassbot/evaluate.py` | Matchup harness |
| `brassbot/diagnostics.py` | Where a score came from |
| `brassbot/yardstick.py` | Distance from expert human play |

## How results are judged

Brass scores are noisy and self-play is easy to fool yourself with, so the
harness is built to resist it:

- **Seats rotate** through every position, so turn order cannot be mistaken for
  skill.
- **Three disjoint seed blocks**: tune on one, validate on a second, report on a
  third. Tuning prints the measured noise floor and rejects steps that do not
  clear it.
- **Distributions, not means.** A bot averaging 150 by scoring 210 half the time
  is a different animal from one that always scores 150.
- **An external reference.** Every other number here compares a bot to another
  bot we wrote. `yardstick.py` scores play against a profile of expert *behaviour*
  from recorded tournament games — 7-10 rail links, 8-12 tiles flipped, 4-6 canal
  loans — so a bot can beat everything we have and still be told it is playing
  badly.

This machinery earned its keep. Five separate tuning results looked like gains on
their own seeds and vanished on unseen ones.

## Things worth knowing before changing the evaluation

- **Price the flow, not the stock.** Every term that valued *holding* something —
  cash, beer, cards, claimed towns — made the bot hoard it and play 10-25 VP
  worse. The terms that worked priced a deadline: a tile losing its chance to
  flip, beer capped at the tiles waiting to use it.
- **Do not optimise against the yardstick.** Pushing the bot onto the expert loan
  band raised profile agreement from 4 of 11 dimensions to 7 and cost 25 VP.
  Expert behaviour is what strong play looks like, not what causes it.
- **Search inherits the evaluation's blind spots.** MCTS scores +9 VP over the
  heuristic while playing an identical strategy — same tile levels, same batching,
  same 4 of 11 bands. Its prior and its leaf value are the same function.

`NEXT.md` is the live handover document: current standing, what has been tried,
and what failed. Three rules that no text source states unambiguously were
settled from the physical components and are pinned by tests — see
`docs/link-scoring.md`.

## Provenance

Component values are generated from a vendored third-party transcription and
cross-checked by independent invariants rather than trusted: 45 tiles per player,
deck sizes of 40/54/64, merchant tiles filling 5/7/9 slots. Two corrections were
needed, both pinned by tests. The vendored source, the rules summary this was
implemented against, and the artwork crops used to settle link scoring are all
untracked for licensing reasons; `docs/research-landscape.md` explains what is
excluded and how to obtain it.
