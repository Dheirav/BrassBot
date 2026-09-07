"""Measure a weight change against the shipped vector, seat-balanced.

    PYTHONPATH=. .venv/bin/python tools/verify-weight.py \
        --set unflipped=0.5625 --players 4 --games 180 --blocks 0,500,1000

Plays the candidate in half the seats and the shipped weights in the other half,
on paired seeds, and pools the blocks with a heterogeneity chi2. A single block
is not a result here: five separate tuning results have looked like gains on
their own seeds and vanished off them, and `scout_bias` cleared two blocks
before dying on the third.

Seat patterns follow tools/tune.py: at 4p the six 2-vs-2 splits, at 2p a seat
swap, and at 3p the one- and two-seat patterns together so the odd-seat-out
bonus cancels between them.
"""
from __future__ import annotations

import argparse
import itertools
import os
import statistics as st
import sys
import time
from concurrent.futures import ProcessPoolExecutor

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brassbot.bots.heuristic import HeuristicBot  # noqa: E402
from brassbot.engine import apply_action, legal_actions  # noqa: E402
from brassbot.state import new_game  # noqa: E402

_SIZES = {2: (1,), 3: (1, 2), 4: (2,)}


def patterns(players):
    return [frozenset(c) for size in _SIZES[players]
            for c in itertools.combinations(range(players), size)]


def _win(deltas) -> float:
    """Share of paired games the candidate seats came out ahead in. Ties are
    halved -- a draw is not a win and calling it one flatters every arm."""
    if not deltas:
        return 0.0
    return (sum(1 for x in deltas if x > 0)
            + 0.5 * sum(1 for x in deltas if x == 0)) / len(deltas)


def _one(arg):
    taken, seed, players, over = arg
    bots = [HeuristicBot(seed=seed * 1000 + s, **over) if s in taken
            else HeuristicBot(seed=seed * 1000 + s) for s in range(players)]
    state = new_game(players, seed=seed)
    while not state.finished:
        apply_action(state, bots[state.current.idx].choose(state, legal_actions(state)))
    sc = [p.vp for p in state.players]
    mine = [sc[i] for i in range(players) if i in taken]
    theirs = [sc[i] for i in range(players) if i not in taken]
    return st.mean(mine) - st.mean(theirs)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True, action="append", dest="sets",
                    help="weight=value, repeatable")
    ap.add_argument("-p", "--players", type=int, default=4, choices=(2, 3, 4))
    ap.add_argument("-n", "--games", type=int, default=180)
    ap.add_argument("-w", "--workers", type=int, default=6)
    ap.add_argument("--blocks", default="0,500,1000",
                    help="comma-separated seed-block starts")
    args = ap.parse_args(argv)

    over = {}
    for pair in args.sets:
        k, _, v = pair.partition("=")
        over[k.strip()] = float(v)
    known = HeuristicBot.DEFAULTS
    unknown = set(over) - set(known)
    if unknown:
        print(f"unknown weights: {sorted(unknown)}", file=sys.stderr)
        return 2
    for k, v in list(over.items()):
        if isinstance(known[k], int) and float(v).is_integer():
            over[k] = int(v)

    starts = [int(x) for x in args.blocks.split(",")]
    pats = patterns(args.players)
    label = ", ".join(f"{k}={v:g}" for k, v in over.items())
    print(f"  {label}   at {args.players}p, {args.games} seat-balanced games a block")
    t0, done, total = time.time(), 0, args.games * len(starts)
    results, every = [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for seed0 in starts:
            jobs = [(pats[g % len(pats)], seed0 + g, args.players, over)
                    for g in range(args.games)]
            d = []
            for x in pool.map(_one, jobs, chunksize=4):
                d.append(x)
                done += 1
                if done % 10 == 0:
                    print(f"PROGRESS done={done} total={total} unit=games "
                          f"t={time.time() - t0:.1f}", flush=True)
            m, se = st.mean(d), st.stdev(d) / len(d) ** 0.5
            results.append((seed0, m, se))
            every.extend(d)
            print(f"RESULT seed {seed0}: {m:+.2f} +- {se:.2f}  ({m/se:.1f} sigma)"
                  f"  win {100 * _win(d):.0f}%", flush=True)

    w = [1 / se ** 2 for _, _, se in results]
    m = sum(wi * x for wi, (_, x, _) in zip(w, results)) / sum(w)
    se = sum(w) ** -0.5
    chi2 = sum(wi * (x - m) ** 2 for wi, (_, x, _) in zip(w, results))
    agree = "blocks agree" if chi2 < 5.99 else "BLOCKS DISAGREE (p<0.05)"
    print(f"\n  POOLED {label} at {args.players}p: {m:+.2f} +- {se:.2f}   "
          f"{m/se:.1f} sigma, chi2 {chi2:.2f}/{len(results)-1}  -- {agree}")

    # The mean alone cannot tell a weight that lifts every game from one that
    # wins big sometimes and loses badly the rest, and those are different
    # things to ship. Win rate is how often the change is ahead at all; P10 is
    # what it does to the bad games, which is what "plays consistently" means.
    every.sort()
    n = len(every)
    p10 = every[max(0, int(0.10 * n) - 1)]
    p90 = every[min(n - 1, int(0.90 * n))]
    print(f"  spread: win {100 * _win(every):.0f}%  "
          f"P10 {p10:+.1f}  median {st.median(every):+.1f}  P90 {p90:+.1f}  "
          f"sd {st.stdev(every):.1f}  over {n} games")
    return 0


if __name__ == "__main__":
    sys.exit(main())
