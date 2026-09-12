# BrassBot

A rules engine, bots, and a measurement harness for **Brass: Birmingham**
(Roxley, 2018).

The engine plays all three player counts. The strongest bot is `heuristic`: a
37-weight position evaluation with an exact two-ply search over the two actions
that make up your own turn. Everything is measured against a held-out seed
block, and results that do not survive replication are recorded as failures
rather than shipped — several are, below.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install pytest pillow
PYTHONPATH=. .venv/bin/python -m pytest -q          # 204 tests
```

## Playing strength

`heuristic`, 200 games a cell on the reporting seed block. A *mirror* is every
seat playing the same bot; *vs greedy* is one seat against three weaker bots.

| format | pool | mean VP | SD | P10 | best | win rate |
| --- | --- | --- | --- | --- | --- | --- |
| 4p | mirror | 131.3 ± 0.4 | 12.4 | 116 | 172 | 25% |
| 4p | vs greedy | 146.7 ± 1.1 | 15.0 | 129 | 184 | 100% |
| 3p | mirror | 144.8 ± 0.6 | 14.5 | 128 | 185 | 33% |
| 3p | vs greedy | 148.0 ± 1.4 | 19.3 | 121 | 193 | 100% |
| 2p | mirror | 162.9 ± 0.9 | 17.0 | 141 | 203 | 50% |
| 2p | vs greedy | 157.0 ± 1.4 | 19.6 | 134 | 217 | 100% |

**Mirror win rates are mechanical.** 25/33/50% is what identical seats must
produce, so that column is a check that the harness is sound, not a result.
Read the mirror *mean* for score quality and the vs-greedy row for strength
against a fixed opponent.

**The SD column is the one that matters when judging a change.** A 12-point
spread at 4p means an improvement worth less than about 1 VP is invisible
without paired seeds.

The other bots, for orientation: `random` and `greedy` are floors; `book` plays
a fixed opening; `learned` is a value-network experiment; `planner` is a beam
search over action *sequences*.

Two of those used to be ahead and no longer are, which is worth stating plainly
because both were once this README's headline:

- **`planner` leads by +3.09 ± 0.96** (three disjoint blocks, 180 seat-balanced
  games, χ² = 0.64 on 2 df) — down from +14.78. The two bots share an
  evaluation, so lookahead was the only thing separating them, and the
  heuristic's exact two-ply turn search ate most of what the planner's
  eight-action horizon was being paid for. It is also far slower.
- **`mcts` was archived on 2026-09-04** to `brassbot/bots/archive/`, having
  measured **-4.81 +- 1.66** against the heuristic (60 seat-balanced games,
  -2.9 sigma; top score in 37% where an even split is 50%). Its leaf value and
  its move prior were both the heuristic's own evaluation, so it could only ever
  prefer what that evaluation already liked -- it spent its budget on the noisy
  part of the game, guessing opponents, while the heuristic searched the
  reliable part exactly. It is out of `REGISTRY` so no measurement can include
  it, but stays importable and under test so the retirement can be re-checked.
  Its `determinize` moved to `state.py`, which `planner` still uses.

**On the target.** The project began aiming at 200+ VP in 4 players. That is not
reachable: across fifteen verified tournament games the winning scores run
142–184 with a median of 158, and none reach 200. Actions are capped at 31 per
player at 4p and experts convert them at ~5 VP each. The realistic target is
150–165; 200+ belongs to the 2-player game, which has 39 actions.
`docs/research-landscape.md` has the evidence.

## Running the bot faster

The engine and the heuristic bot are standard-library Python, so they run
under PyPy unchanged, and a warm game takes about half the CPU it takes under
CPython (5.9s against 12.3s, four players, same moves and scores to the point).
The first game in a process pays a few seconds of JIT warm-up, which the
measurement harness amortises across the dozens each worker plays.

The interpreter lives outside the repo and the venv inside it:

```bash
# once: PyPy 3.11 from pypy.org, unpacked under ~/.local/opt, no root needed
curl -sSL -o /tmp/pypy.tar.bz2 https://downloads.python.org/pypy/pypy3.11-v7.3.23-linux64.tar.bz2
mkdir -p ~/.local/opt && tar xjf /tmp/pypy.tar.bz2 -C ~/.local/opt
ln -sfn ~/.local/opt/pypy3.11-v7.3.23-linux64 ~/.local/opt/pypy3
~/.local/opt/pypy3/bin/pypy3 -m venv .venv-pypy && .venv-pypy/bin/python -m pip install pytest

# then, for anything that is games of the heuristic bot:
PYTHONPATH=. .venv-pypy/bin/python tools/verify-weight.py --set ... --workers 8
PYTHONPATH=. .venv-pypy/bin/python tools/attribution.py 40 runs/attribution.json
```

`.venv/` stays the interpreter for everything else: the learned bot and the
value-model tools need numpy, which is slow under PyPy, and the server does
not need the speed. `pyproject.toml` says 3.12 because that is what `.venv` is;
nothing is installed as a package, so PyPy 3.11 on `PYTHONPATH` is fine.

## Playing it

There is a board you can play on, in a browser, against any of the bots.

```bash
PYTHONPATH=. .venv/bin/python tools/serve.py --name "Your Name"
# then open http://localhost:8765
```

Pick a card, pick an action, then click the highlighted town or link on the map.
Hovering a legal target draws the tile you would place and names its exact cost,
including where each cube comes from and whose mine it is — `£5 + 1 iron
(market £2) = £7` — before you commit to anything.

The VP track is drawn as the frame of the board, the way it is printed on the
real one, with a solid disc for VP banked and a dashed ring for where you would
finish if the game ended now. For the whole Canal Era the banked figure is near
zero for everyone, so the ring is the one that moves.

`⏻ Stop server` shuts the process down, which ends **every** table it is
serving, not only yours. It takes two clicks and exports nothing, so export
anything worth keeping first.

| flag | |
| --- | --- |
| `--port 8765` | change it if the port is busy |
| `--seed N` | a specific deal; omit for a fresh one each start |
| `--players 4` | 2, 3 or 4 |
| `--opponent heuristic` | `heuristic`, `planner`, `greedy`, `book`, `learned`, `random` |
| `--name "You"` | your seat's name in exported logs |
| `--host 0.0.0.0` | let other devices on your network play; default is localhost only |

### Three people and one bot at the same table

```bash
PYTHONPATH=. .venv/bin/python tools/serve.py --host 0.0.0.0 --humans 3 --names "Dheirav,Praveen,Hari"
```

Seats 0 to 2 are people, seat 3 is the bot. Each person opens the address with
their seat, `http://<ip>:8765/?seat=1`, and the server prints the three links
at startup. A page polls while it is somebody else's turn, so it updates when
they move. Undo is off at a shared table, since it would take back another
person's move. The exported log and the results page carry the names.

### Several people at once, each at their own table

Each URL is its own table, one human against three bots, and tables cannot see
each other:

```
http://<your-ip>:8765/             table "main", dealt from --seed
http://<your-ip>:8765/?room=alice  table "alice", its own random deal
http://<your-ip>:8765/?room=bob    table "bob"
```

A table is created the first time somebody asks for it, and the header shows
which one you are on. Started with `--host 0.0.0.0` the server prints the
address to share.

This is an unauthenticated development server: there are no accounts and no
passwords, so anyone who can reach the port can play and can open any table.
That is fine on a home network and is not something to expose to the internet.

**Export log** writes two files. The prose log goes to `logs/` in the same format
as the pasted-in real games, so games you play here pool with those and every
analysis script reads them unchanged. Pass the `--name` you play under elsewhere
if you want them counted together.

Beside it goes a `.replay.json`: the seed, the seat, and the index of every
action chosen. The engine is deterministic, so that reconstructs the game
exactly, hand and market included, which a pasted log can never do. Review your
decisions with it:

```bash
PYTHONPATH=. .venv/bin/python tools/review.py logs/<game>.replay.json
```

At each of your turns it enumerates what was legal, scores every option the way
the bot scores a position, and reports where your choice ranked and how far
behind the bot's pick it was. Read the gaps rather than the ranks: most
decisions score within a point of each other, and the bot is not obviously
stronger than you, so a disagreement means the moment is worth a look.

Two things about the server worth knowing: it holds **one game**, so a second
browser tab is playing the same one (a stale tab is refused rather than allowed
to play a move you cannot see); and **Undo rewinds past the bots' replies**, so
taking a move back after seeing what they did leaks information a real game
would not. That is right for analysis and wrong for honest play.

## Using it

```bash
# measure a matchup: seats rotated, full score distribution, drawn wins split
PYTHONPATH=. .venv/bin/python tools/evaluate.py heuristic -o greedy -n 100 -w 4

# where a bot's points come from, and what separates its good games from its bad
PYTHONPATH=. .venv/bin/python tools/diagnose.py heuristic -n 60 -w 4

# how far its play is from expert human play, on 11 measured dimensions
PYTHONPATH=. .venv/bin/python tools/yardstick.py heuristic -n 40 --sources

# tune weights by playing, seat-balanced: tune on one block, validate on another
PYTHONPATH=. .venv/bin/python tools/tune.py -b heuristic -n 60 -w 4

# play a seat yourself, or hand it to an agent, one decision per invocation
PYTHONPATH=. .venv/bin/python tools/play.py new --seed 1 --out /tmp/g.pkl
PYTHONPATH=. .venv/bin/python tools/play.py show /tmp/g.pkl
PYTHONPATH=. .venv/bin/python tools/play.py move /tmp/g.pkl 7 --expect brewery

# read a real logged game back in, and score its final board with our engine
PYTHONPATH=. .venv/bin/python tools/import_log.py logs/*.log
PYTHONPATH=. .venv/bin/python tools/check_scoring.py logs/*.log

# one game, round by round, for debugging the engine
PYTHONPATH=. .venv/bin/python tools/playout.py heuristic -s 3
```

## Layout

For how the pieces fit together and where to change what, see
`docs/architecture.md`.

| Path | What |
| --- | --- |
| `brassbot/gamedata.py` | The printed components: tiles, board, markets, income track |
| `brassbot/state.py` | Game state, setup, cloning |
| `brassbot/network.py` | Connectivity — "your network" vs "connected" |
| `brassbot/resources.py` | Coal / iron / beer sourcing and consumption |
| `brassbot/engine.py` | Move generation, application, era flow, scoring |
| `brassbot/bots/` | `random`, `greedy`, `book`, `heuristic`, `learned`, `planner` |
| `brassbot/bots/archive/` | Bots that no longer ship, kept runnable with the number that retired them |
| `brassbot/planner.py` | Beam search over action sequences |
| `brassbot/evaluate.py` | Matchup harness |
| `brassbot/diagnostics.py` | Where a score came from |
| `brassbot/yardstick.py` | Distance from expert human play |

## How results are judged

Brass scores are noisy and self-play is easy to fool yourself with, so the
harness is built to resist it:

- **Seats rotate** through every position, so turn order cannot be mistaken for
  skill.
- **Seat-balanced duels, not one-against-three.** A lone variant seat gains about
  **+0.5 VP for being different at all** — three deliberately neutral placebos
  measured +0.74, +0.39 and +0.47. The 2v2 harness puts every seat variant in
  half the games and has cut headline results by 2–3x, once to nothing.
- **Three disjoint seed blocks**: tune on one, validate on a second, report on a
  third. Tuning prints the measured noise floor and rejects steps that do not
  clear it.
- **Distributions, not means.** A bot averaging 150 by scoring 210 half the time
  is a different animal from one that always scores 150.
- **An external reference.** Every other number here compares a bot to another
  bot we wrote. `yardstick.py` scores play against a profile of expert *behaviour*
  from recorded tournament games — 7–10 rail links, 8–12 tiles flipped, 4–6 canal
  loans — so a bot can beat everything we have and still be told it is playing
  badly.

This machinery earned its keep. Five separate tuning results looked like gains on
their own seeds and vanished on unseen ones, and one shipped weight had to be
reverted after the tree it was measured in changed underneath it.

## Things worth knowing before changing the evaluation

- **Price the flow, not the stock.** Every term that valued *holding* something —
  cash, beer, cards, claimed towns — made the bot hoard it and play 10–25 VP
  worse. The terms that worked priced a deadline: a tile losing its chance to
  flip, beer capped at the tiles waiting to use it.
- **A weight is a number conditional on the rest of the vector**, and on the
  player count. Anything measured against one snapshot has to be re-measured in
  the tree it will ship in; several per-format values live in `PROFILES` for
  exactly this reason.
- **Do not optimise against the yardstick.** Pushing the bot onto the expert loan
  band raised profile agreement from 4 of 11 dimensions to 7 and cost 25 VP.
  Expert behaviour is what strong play looks like, not what causes it.
- **A cheap exact search beats an expensive approximate one.** Searching the two
  actions of your own turn exactly was worth +7.6 VP at 4p and took most of the
  value out of an eight-action beam search that costs orders of magnitude more.
- **Terms invented to patch a symptom lose.** Eleven tried, all at or below zero.
  Every term that has ever worked came instead from measuring what the term is
  actually *paid* and comparing it to what the bot believes.

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
