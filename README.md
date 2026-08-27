# BrassBot

An engine and bot for **Brass: Birmingham** (Roxley, 2018), targeting strong
4-player play.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest pillow
PYTHONPATH=. .venv/bin/python -m pytest -q
```

## Use

```bash
# measure a matchup (seats rotated, full score distribution)
PYTHONPATH=. .venv/bin/python tools/evaluate.py heuristic -o greedy -n 200 -w 8
PYTHONPATH=. .venv/bin/python tools/evaluate.py heuristic --mirror -n 200 -w 8

# one game, round by round, for debugging the engine
PYTHONPATH=. .venv/bin/python tools/playout.py heuristic -s 3

# tune the heuristic weights by playing
PYTHONPATH=. .venv/bin/python tools/tune.py -n 40 --passes 2 -w 8

# regenerate the component data from its vendored source
node tools/extract_gamedata.js
```

## Layout

| Path | What |
| --- | --- |
| `brassbot/gamedata.py` | Static components: tiles, board, markets, income track |
| `brassbot/state.py` | Game state, setup, cloning |
| `brassbot/network.py` | Connectivity — "your network" vs "connected" |
| `brassbot/resources.py` | Coal / iron / beer sourcing and consumption |
| `brassbot/engine.py` | Move generation, application, era flow, scoring |
| `brassbot/bots/` | Bot interface and the bots themselves |
| `brassbot/evaluate.py` | Evaluation harness |
| `docs/link-scoring.md` | How link scoring was settled from the components |

**A score in Brass is not self-contained** — your tiles flip when opponents
consume your coal and drink your beer. The same bot scores far more against
strong opponents than weak ones, so every result here is labelled with its
opponent pool. See `NEXT.md`.
