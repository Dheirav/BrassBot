"""Measure a bot against expert human play rather than against our other bots.

    PYTHONPATH=. .venv/bin/python tools/yardstick.py heuristic -n 40 -w 4
    PYTHONPATH=. .venv/bin/python tools/yardstick.py mcts -o heuristic -n 20 -w 2
"""
import argparse
import os
import sys

from brassbot.bots import REGISTRY
from brassbot.diagnostics import collect
from brassbot.yardstick import evaluate, summarise

ARROW = {"ok": "  ok ", "low": " LOW ", "high": "HIGH "}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bot", choices=sorted(REGISTRY))
    ap.add_argument("-o", "--opponents", default=None, help="defaults to a mirror")
    ap.add_argument("-n", "--games", type=int, default=40)
    ap.add_argument("-p", "--players", type=int, default=4, choices=(2, 3, 4))
    ap.add_argument("-w", "--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--sources", action="store_true", help="print each band's source")
    args = ap.parse_args(argv)

    seats = [args.bot] + [args.opponents or args.bot] * (args.players - 1)
    records = [r for r in collect(seats, games=args.games, workers=args.workers,
                                  n_players=args.players) if r.seat == 0]

    gaps = evaluate(records, players=args.players)
    label_w = max(len(g.band.label) for g in gaps)

    print(f"{args.bot} vs {seats[1]} x{args.players - 1} — {len(records)} games, "
          f"{args.players}p")
    print(f"\n{'':<{label_w}}{'ours':>9}{'expert':>13}{'':>7}{'gap':>7}")
    print("-" * (label_w + 36))
    for g in gaps:
        band = f"{g.band.low:g}-{g.band.high:g}"
        gap = "" if g.inside else f"{g.distance:.1f}w"
        print(f"{g.band.label:<{label_w}}{g.value:>9.2f}{band:>13}  {ARROW[g.direction]}{gap:>7}")

    inside, distance = summarise(gaps)
    print("-" * (label_w + 36))
    print(f"{'inside expert band':<{label_w}}{inside:>4}/{len(gaps)}"
          f"      mean gap {distance:.2f} band-widths")

    if args.sources:
        print("\nWhere each band comes from:")
        for g in gaps:
            print(f"  {g.band.label}: {g.band.source}")
        print("\nThese are reported figures from a handful of tournament games and")
        print("written expert guidance, not a measured distribution. Being outside")
        print("a band is a question to investigate, not a verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
