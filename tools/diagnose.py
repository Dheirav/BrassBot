"""Where a bot's points come from, and what separates its good games from its bad.

    PYTHONPATH=. .venv/bin/python tools/diagnose.py heuristic -n 100 -w 8
"""
import argparse
import os
import sys

from brassbot.bots import REGISTRY
from brassbot.diagnostics import (
    action_mix,
    behaviour,
    collect,
    composition,
    highest_levels,
    split_by_outcome,
    stranded_by_era,
)


def table(title, rows, unit=""):
    width = max(len(k) for k in rows)
    print(f"\n{title}")
    print("-" * (width + 26))
    for key, value in rows.items():
        print(f"  {key:<{width}}  {value:>8.1f}{unit}")


def compare(title, best, worst, fn, unit=""):
    a, b = fn(best), fn(worst)
    width = max(len(k) for k in a)
    print(f"\n{title}")
    print(f"  {'':<{width}}  {'best 20%':>10}{'worst 20%':>11}{'delta':>10}")
    print("-" * (width + 35))
    for key in a:
        delta = a[key] - b[key]
        print(f"  {key:<{width}}  {a[key]:>10.1f}{b[key]:>11.1f}{delta:>+10.1f}{unit}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bot", choices=sorted(REGISTRY))
    ap.add_argument("-o", "--opponents", default=None,
                    help="defaults to a mirror match")
    ap.add_argument("-n", "--games", type=int, default=100)
    ap.add_argument("-s", "--seed", type=int, default=0)
    ap.add_argument("-w", "--workers", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args(argv)

    seats = [args.bot] + [args.opponents or args.bot] * 3
    records = collect(seats, games=args.games, seed0=args.seed, workers=args.workers)
    subject = [r for r in records if r.bot == args.bot and r.seat == 0]

    mean_vp = sum(r.final_vp for r in subject) / len(subject)
    print(f"{args.bot} in seat 0 vs {seats[1]} x3 — {len(subject)} games, "
          f"mean {mean_vp:.1f} VP")

    comp = composition(subject)
    width = max(len(k) for k in comp)
    print("\nVP composition")
    print("-" * (width + 30))
    for key, value in comp.items():
        share = 100 * value / mean_vp if mean_vp else 0
        print(f"  {key:<{width}}  {value:>8.1f}  {share:>5.1f}%")
    print(f"  {'TOTAL':<{width}}  {sum(comp.values()):>8.1f}")

    table("Behaviour (per game)", behaviour(subject))
    table("Tile fate at each era scoring", stranded_by_era(subject))
    table("Actions taken (per game)", action_mix(subject))
    table("Highest tile level built", highest_levels(subject))

    best, worst = split_by_outcome(subject)
    print(f"\n\n=== what separates a good game from a bad one ===")
    print(f"best 20%: mean {sum(r.final_vp for r in best)/len(best):.1f} VP   "
          f"worst 20%: mean {sum(r.final_vp for r in worst)/len(worst):.1f} VP")
    compare("VP composition", best, worst, composition)
    compare("Behaviour", best, worst, behaviour)
    compare("Actions taken", best, worst, action_mix)
    compare("Highest tile level built", best, worst, highest_levels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
