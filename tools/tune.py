"""Tune a bot's parameters by playing, not by arguing.

Coordinate descent: take each weight in turn, try it scaled up and down, keep
whatever actually wins games, repeat.

Three things keep the signal above the noise:

* **Paired seeds.** Every candidate plays the *same* games, so two candidates
  differ only by their weights and not by which boards they drew. Unpaired,
  the run-to-run spread (SD ~30) would swamp the effect being measured.
* **Separate tuning and reporting seeds.** Tuning runs on its own seed block so
  the headline number can be measured on boards the weights never saw.
* **A seat-balanced harness.** A candidate plays *the current best weights*,
  with the seats it occupies rotated so that every seat is the candidate in
  half the games. The obvious alternative -- one candidate seat against three
  fixed opponents -- rewards a candidate for merely being DIFFERENT: three
  deliberately near-neutral placebos measured +0.74, +0.39 and +0.47 in it,
  because the odd seat out stops contending for the same slots as three copies
  of itself, roughly in proportion to how much its play changes. Coordinate
  descent will happily climb that gradient, which is the likeliest reason this
  tuner has twice reported a gain 3x what a separate harness could find. Pass
  ``--harness vs`` for the old behaviour.

    PYTHONPATH=. .venv/bin/python tools/tune.py -n 40 --passes 2 -w 8
    PYTHONPATH=. .venv/bin/python tools/tune.py -b planner --fixed horizon=8 \
        -o heuristic -n 30 -w 4

Search parameters are noisier than evaluation weights, because determinization
resamples every plan and the bot is genuinely stochastic. Expect a wider noise
floor and budget more games per candidate accordingly.
"""
import argparse
import json
import os
import sys
import time

import itertools
import statistics
from concurrent.futures import ProcessPoolExecutor

from brassbot.bots import REGISTRY
from brassbot.evaluate import evaluate, play_game

SCALES = (0.5, 0.75, 1.5, 2.0)  # the current value is always also considered
TUNE_SEED0 = 10_000             # kept clear of the reporting seeds
VALIDATE_SEED0 = 20_000         # a third block, unseen by both


def spec(bot: str, params: dict) -> str:
    def fmt(v):
        return str(v) if isinstance(v, int) else f"{v:.4g}"
    return bot + ":" + ",".join(f"{k}={fmt(v)}" for k, v in sorted(params.items()))


def tunable(bot: str) -> dict:
    """A bot's tunable parameters. Both bots expose them as DEFAULTS."""
    return dict(REGISTRY[bot].DEFAULTS)


def coerce(default, value):
    """Keep a parameter the type it started as. Counts must stay whole -- a
    fractional prior width or iteration count breaks slicing and range()."""
    return max(1, int(round(value))) if isinstance(default, int) else value


def measure(bot, weights, opponents, games, workers, seed0=TUNE_SEED0, players=4):
    name = spec(bot, weights)
    report = evaluate(name, opponents, games=games, seed0=seed0, workers=workers,
                      n_players=players)
    summary = report.by_bot[name]
    return summary.mean, summary.win_rate, summary.stderr


def seat_patterns(players):
    """Which seats the candidate takes, so that every seat is the candidate in
    the same number of games AND the candidate is the odd one out exactly as
    often as the baseline is.

    At 4p that is the six 2-vs-2 splits. At 3p no split is even, so the
    one-seat and two-seat patterns are run together and the odd-seat bonus
    cancels between them. At 2p a seat swap is all there is.
    """
    seats = range(players)
    sizes = {2: (1,), 3: (1, 2), 4: (2,)}[players]
    return [frozenset(c) for size in sizes
            for c in itertools.combinations(seats, size)]


def _duel_game(arg):
    seats, seed, players = arg
    return play_game(seats, seed, players)


def duel(bot, weights, base_weights, games, workers, seed0=TUNE_SEED0, players=4):
    """Play `weights` against `base_weights` seat-balanced, on paired seeds.

    Returns the per-seat VP difference, the candidate's share of wins, and the
    standard error of the difference. The difference is what coordinate descent
    steps on: an absolute mean says how strong the board was, a difference says
    which weights won.
    """
    var, base = spec(bot, weights), spec(bot, base_weights)
    patterns = seat_patterns(players)
    jobs, taken_by_game = [], []
    for g in range(games):
        taken = patterns[g % len(patterns)]
        jobs.append(([var if s in taken else base for s in range(players)],
                     seed0 + g, players))
        taken_by_game.append(taken)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_duel_game, jobs, chunksize=4))

    # Attribute by seat rather than by name: when a candidate is identical to
    # the baseline the two spec strings are equal, and a name test would credit
    # every seat to both sides. That case is worth keeping honest -- it is the
    # null control, and it should read 0.00 +- 0.00 at an even win share.
    deltas, wins = [], []
    for result, taken in zip(results, taken_by_game):
        mine = [result.scores[i] for i in range(players) if i in taken]
        theirs = [result.scores[i] for i in range(players) if i not in taken]
        deltas.append(statistics.fmean(mine) - statistics.fmean(theirs))
        wins.append(sum(1.0 / len(result.winners)
                        for i in result.winners if i in taken))
    stderr = (statistics.stdev(deltas) / len(deltas) ** 0.5
              if len(deltas) > 1 else 0.0)
    return statistics.fmean(deltas), statistics.fmean(wins), stderr


SIGMAS = 2.0   # how far a step must clear its own standard error to be kept


def tune(bot, opponents, games, passes, workers, keys=None, players=4, fixed=(),
         harness="duel"):
    weights = tunable(bot)
    # `fixed` used to be passed as a tuple of KEYS, so a value given on the
    # command line was excluded from the search and then applied only after the
    # run had finished. `--fixed pair_search=8` therefore tuned at whatever the
    # default happened to be -- 24, and 2.3x slower -- while reporting 8 in the
    # output. Apply it up front, where it was always meant to bite.
    if isinstance(fixed, dict):
        weights.update(fixed)
    # `rollout` is a research switch, not a quality parameter: one play-out costs
    # ~285 ms against ~0.25 ms for an evaluation, so a candidate at rollout=1.0
    # turns a minutes-long run into hours -- and if it happened to clear the noise
    # floor, tune() would adopt it and ship a 1000x-slower bot.
    skip = set(fixed) | {"pass_bias", "rollout"}
    keys = keys or [k for k in weights if k not in skip]

    if harness == "vs":
        best_mean, best_win, noise = measure(bot, weights, opponents, games,
                                             workers, players=players)
        print(f"baseline: mean {best_mean:.1f}  win {100*best_win:.0f}%  "
              f"(noise +-{noise:.1f} -- treat smaller steps as meaningless)")
    else:
        best_mean, best_win, noise = 0.0, 0.0, 0.0
        print(f"baseline: the starting weights themselves, played seat-balanced "
              f"across {len(seat_patterns(players))} seat patterns")
    print(f"  {spec(bot, weights)}\n")

    evals = 1
    for round_no in range(1, passes + 1):
        print(f"--- pass {round_no} ---")
        for key in keys:
            current = weights[key]
            candidates = [coerce(current, current * s) for s in SCALES]
            if current == 0:
                candidates = [0.1, 0.5, 1.0]
            candidates = [c for c in dict.fromkeys(candidates) if c != current]

            improved = None
            for value in candidates:
                trial = dict(weights, **{key: value})
                evals += 1
                if harness == "vs":
                    mean, win, _ = measure(bot, trial, opponents, games, workers,
                                           players=players)
                    # Require the step to clear the noise floor. Coordinate
                    # descent will otherwise happily chase run-to-run variance,
                    # and a run that "improves" on its own seeds can measure
                    # worse off them.
                    if mean > best_mean + noise:
                        improved, best_mean, best_win = value, mean, win
                    continue
                # The candidate plays the weights it is trying to beat, so the
                # comparison is a difference rather than two absolute means,
                # and the seat-balancing removes the odd-seat-out bonus that
                # would otherwise reward any change at all.
                base = (weights if improved is None
                        else dict(weights, **{key: improved}))
                delta, win, stderr = duel(bot, trial, base, games, workers,
                                          players=players)
                if delta > SIGMAS * stderr:
                    improved, best_win = value, win
                    best_mean += delta
            if improved is not None:
                weights[key] = improved
                shown = f"mean {best_mean:.1f}" if harness == "vs" else f"{best_mean:+.2f} cumulative"
                print(f"  {key:<16} {current:>8.3g} -> {improved:<8.3g} "
                      f"{shown}  win {100*best_win:.0f}%")
            else:
                print(f"  {key:<16} {current:>8.3g}    kept")
    return weights, best_mean, best_win, evals


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-b", "--bot", default="heuristic", choices=sorted(REGISTRY),
                    help="which bot's parameters to tune")
    ap.add_argument("-o", "--opponents", default="greedy")
    ap.add_argument("--fixed", default="",
                    help="params to hold constant, e.g. iterations=300")
    ap.add_argument("-n", "--games", type=int, default=40)
    ap.add_argument("--passes", type=int, default=2)
    ap.add_argument("-p", "--players", type=int, default=4, choices=(2, 3, 4))
    ap.add_argument("-w", "--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--out", default="tuned_weights.json")
    ap.add_argument("--harness", default="duel", choices=("duel", "vs"),
                    help="duel: candidate plays the current best weights, "
                         "seat-balanced. vs: one candidate seat against fixed "
                         "opponents (flatters any change by ~+0.5 VP)")
    args = ap.parse_args(argv)

    opponents = [args.opponents] * (args.players - 1)
    t0 = time.time()
    fixed = {}
    for pair in args.fixed.split(","):
        if "=" in pair:
            k, _, v = pair.partition("=")
            base = tunable(args.bot)[k.strip()]
            fixed[k.strip()] = coerce(base, float(v))

    weights, mean, win, evals = tune(args.bot, opponents, args.games, args.passes,
                                     args.workers, players=args.players,
                                     fixed=fixed, harness=args.harness)
    weights.update(fixed)
    elapsed = time.time() - t0

    print(f"\n{evals} candidates in {elapsed/60:.1f} min")
    gain = f"mean {mean:.1f}" if args.harness == "vs" else f"{mean:+.1f} VP claimed"
    print(f"best on tuning seeds: {gain}  win {100*win:.0f}%")

    # The verdict that counts: does it hold up on boards nobody optimised for?
    # Measured against the STARTING weights, not against the running best, so a
    # sequence of steps that each cleared their own error bar still has to show
    # a gain end to end.
    base = {**tunable(args.bot), **fixed}
    print(f"\nVALIDATION on unseen seeds {VALIDATE_SEED0}+:")
    if args.harness == "vs":
        start_v, _, v_noise = measure(args.bot, base, opponents, args.games,
                                      args.workers, seed0=VALIDATE_SEED0,
                                      players=args.players)
        tuned_v, _, _ = measure(args.bot, weights, opponents, args.games,
                                args.workers, seed0=VALIDATE_SEED0,
                                players=args.players)
        held = tuned_v - start_v
        print(f"  starting weights: {start_v:.1f}")
        print(f"  tuned weights:    {tuned_v:.1f}   ({held:+.1f}, "
              f"noise +-{v_noise:.1f})")
    else:
        held, v_win, v_noise = duel(args.bot, weights, base, args.games,
                                    args.workers, seed0=VALIDATE_SEED0,
                                    players=args.players)
        start_v, tuned_v = 0.0, held
        print(f"  tuned vs starting weights, seat-balanced: {held:+.2f} "
              f"+-{v_noise:.2f}  win share {100*v_win:.1f}%")
    if held <= SIGMAS * v_noise:
        print(f"  ==> NOT a real improvement ({SIGMAS:g} sigma required). "
              f"Keep the starting weights.")
    print()
    print(spec(args.bot, weights))

    with open(args.out, "w") as fh:
        json.dump({"bot": args.bot, "weights": weights, "tuning_mean": mean, "tuning_win_rate": win,
                   "validation_start": start_v, "validation_tuned": tuned_v,
                   "validation_noise": v_noise, "held_up": held > SIGMAS * v_noise,
                   "harness": args.harness, "sigmas_required": SIGMAS,
                   "opponents": opponents, "games_per_candidate": args.games,
                   "players": args.players,
                   "tune_seed0": TUNE_SEED0, "validate_seed0": VALIDATE_SEED0},
                  fh, indent=2)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
