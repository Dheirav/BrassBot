"""Refresh the standings table in NEXT.md.

Runs the report-seed cells that the handover document quotes. Unlike
`brassbot.evaluate.evaluate`, which uses `pool.map` and prints nothing until it
finishes, this reports per-game progress so a long run can be watched:

    PYTHONPATH=. .venv/bin/python tools/standings.py --out runs/standings.log
    tools/watch-progress.sh runs/standings.log        # in another shell

Each line of PROGRESS output carries the counter and the elapsed seconds, so the
watcher derives its ETA from the measured rate rather than guessing one.
"""
from __future__ import annotations

import argparse
import os
import statistics as st
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brassbot.evaluate import lineup, play_game  # noqa: E402

# The cells NEXT.md quotes, in the order it lists them.
CELLS = [(4, "heuristic"), (4, "greedy"), (3, "heuristic"), (3, "greedy"),
         (2, "heuristic"), (2, "greedy")]


def _play(job):
    seats, seed, players = job
    return play_game(seats, seed, players).scores


def run_cell(players, opponent, games, seed0, workers, done, total, t0):
    jobs = [(lineup("heuristic", [opponent] * (players - 1), g, players),
             seed0 + g, players) for g in range(games)]
    subject_scores, wins = [], 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_play, j): j for j in jobs}
        for fut in as_completed(futures):
            scores = fut.result()
            seats = futures[fut][0]
            mine = [s for s, name in zip(scores, seats) if name == "heuristic"]
            others = [s for s, name in zip(scores, seats) if name != "heuristic"]
            subject_scores.extend(mine)
            if others and max(mine) > max(others):
                wins += 1
            elif not others:                      # mirror: share the win
                wins += 1 / players
            done[0] += 1
            print(f"PROGRESS done={done[0]} total={total} unit=games t={time.time() - t0:.1f}",
                  flush=True)
    return subject_scores, wins


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--games", type=int, default=200)
    ap.add_argument("-w", "--workers", type=int, default=6)
    ap.add_argument("--seed0", type=int, default=0, help="report block starts at 0")
    ap.add_argument("--formats", default="4",
                    help="comma-separated player counts, e.g. 4 or 2,3,4")
    args = ap.parse_args(argv)

    want = {int(x) for x in args.formats.split(",")}
    cells = [c for c in CELLS if c[0] in want]
    total = len(cells) * args.games
    done, t0 = [0], time.time()

    print(f"standings, {args.games} games a cell, report seeds {args.seed0}+")
    print(f"cells: {', '.join(f'{p}p vs {o}' for p, o in cells)}", flush=True)
    rows = []
    for players, opponent in cells:
        scores, wins = run_cell(players, opponent, args.games, args.seed0,
                                args.workers, done, total, t0)
        s = sorted(scores)
        rows.append((players, "mirror" if opponent == "heuristic" else "vs greedy",
                     st.mean(s), st.stdev(s) / len(s) ** 0.5, st.stdev(s),
                     s[len(s) // 10], s[-1], 100 * wins / args.games))
        print(f"RESULT {rows[-1]}", flush=True)

    print(f"\n  {'fmt':<4}{'pool':<11}{'all seats':>14}{'SD':>7}{'P10':>6}"
          f"{'best':>6}{'win%':>7}")
    for p, pool_, mean, se, sd, p10, best, win in rows:
        print(f"  {p}p  {pool_:<11}{mean:9.1f} +-{se:.1f}{sd:7.1f}{p10:6d}"
              f"{best:6d}{win:6.0f}%")
    print(f"\ntotal {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
