"""Run a matchup and print the score distribution.

    PYTHONPATH=. .venv/bin/python tools/evaluate.py greedy -o random -n 200 -w 8
    PYTHONPATH=. .venv/bin/python tools/evaluate.py greedy --mirror -n 200
"""
import argparse
import os
import sys

from brassbot.bots import REGISTRY
from brassbot.evaluate import DEFAULT_TARGET, evaluate, format_report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject", choices=sorted(REGISTRY), help="the bot under test")
    ap.add_argument("-o", "--opponents", default="random",
                    help="comma-separated; a single name fills every other seat")
    ap.add_argument("--mirror", action="store_true",
                    help="play the subject against copies of itself")
    ap.add_argument("-n", "--games", type=int, default=100)
    ap.add_argument("-s", "--seed", type=int, default=0)
    ap.add_argument("-p", "--players", type=int, default=4)
    ap.add_argument("-w", "--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("-t", "--target", type=int, default=DEFAULT_TARGET,
                    help="score we are chasing; reported as a hit rate")
    args = ap.parse_args(argv)

    if args.mirror:
        opponents = [args.subject] * (args.players - 1)
    else:
        names = [n.strip() for n in args.opponents.split(",") if n.strip()]
        unknown = [n for n in names if n not in REGISTRY]
        if unknown:
            ap.error(f"unknown bot(s): {unknown}; known: {sorted(REGISTRY)}")
        # One name means "fill every other seat with this".
        opponents = names * (args.players - 1) if len(names) == 1 else names
        opponents = opponents[: args.players - 1]

    report = evaluate(args.subject, opponents, games=args.games, seed0=args.seed,
                      workers=args.workers, n_players=args.players, target=args.target)
    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
