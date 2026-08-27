"""Tune a bot's parameters by playing, not by arguing.

Coordinate descent: take each weight in turn, try it scaled up and down, keep
whatever actually wins games, repeat.

Two things keep the signal above the noise:

* **Paired seeds.** Every candidate plays the *same* games, so two candidates
  differ only by their weights and not by which boards they drew. Unpaired,
  the run-to-run spread (SD ~30) would swamp the effect being measured.
* **Separate tuning and reporting seeds.** Tuning runs on its own seed block so
  the headline number can be measured on boards the weights never saw.

    PYTHONPATH=. .venv/bin/python tools/tune.py -n 40 --passes 2 -w 8
    PYTHONPATH=. .venv/bin/python tools/tune.py -b mcts --fixed iterations=300 \
        -o heuristic -n 30 -w 4

Search parameters are noisier than evaluation weights, because determinization
resamples every iteration and the bot is genuinely stochastic. Expect a wider
noise floor and budget more games per candidate accordingly.
"""
import argparse
import json
import os
import sys
import time

from brassbot.bots import REGISTRY
from brassbot.evaluate import evaluate

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


def tune(bot, opponents, games, passes, workers, keys=None, players=4, fixed=()):
    weights = tunable(bot)
    skip = set(fixed) | {"pass_bias"}
    keys = keys or [k for k in weights if k not in skip]

    best_mean, best_win, noise = measure(bot, weights, opponents, games, workers,
                                         players=players)
    print(f"baseline: mean {best_mean:.1f}  win {100*best_win:.0f}%  "
          f"(noise +-{noise:.1f} -- treat smaller steps as meaningless)")
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
                mean, win, _ = measure(bot, trial, opponents, games, workers,
                                       players=players)
                evals += 1
                # Require the step to clear the noise floor. Coordinate descent
                # will otherwise happily chase run-to-run variance, and a run
                # that "improves" on its own seeds can measure worse off them.
                if mean > best_mean + noise:
                    improved, best_mean, best_win = value, mean, win
            if improved is not None:
                weights[key] = improved
                print(f"  {key:<16} {current:>8.3g} -> {improved:<8.3g} "
                      f"mean {best_mean:.1f}  win {100*best_win:.0f}%")
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
                                     fixed=tuple(fixed))
    weights.update(fixed)
    elapsed = time.time() - t0

    print(f"\n{evals} candidates in {elapsed/60:.1f} min")
    print(f"best on tuning seeds: mean {mean:.1f}  win {100*win:.0f}%")

    # The verdict that counts: does it hold up on boards nobody optimised for?
    base = {**tunable(args.bot), **fixed}
    start_v, _, v_noise = measure(args.bot, base, opponents, args.games, args.workers,
                                  seed0=VALIDATE_SEED0, players=args.players)
    tuned_v, _, _ = measure(args.bot, weights, opponents, args.games, args.workers,
                            seed0=VALIDATE_SEED0, players=args.players)
    print(f"\nVALIDATION on unseen seeds {VALIDATE_SEED0}+:")
    print(f"  starting weights: {start_v:.1f}")
    print(f"  tuned weights:    {tuned_v:.1f}   ({tuned_v - start_v:+.1f}, "
          f"noise +-{v_noise:.1f})")
    if tuned_v <= start_v + v_noise:
        print("  ==> NOT a real improvement. Keep the starting weights.")
    print()
    print(spec(args.bot, weights))

    with open(args.out, "w") as fh:
        json.dump({"bot": args.bot, "weights": weights, "tuning_mean": mean, "tuning_win_rate": win,
                   "validation_start": start_v, "validation_tuned": tuned_v,
                   "validation_noise": v_noise, "held_up": tuned_v > start_v + v_noise,
                   "opponents": opponents, "games_per_candidate": args.games,
                   "players": args.players,
                   "tune_seed0": TUNE_SEED0, "validate_seed0": VALIDATE_SEED0},
                  fh, indent=2)
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
