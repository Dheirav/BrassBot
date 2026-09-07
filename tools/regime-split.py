"""Stage 0 of mode selection: does a weight's value depend on the BOARD?

    PYTHONPATH=. .venv/bin/python tools/regime-split.py \
        --set sell_ready=0.75 --blocks 0,500,1000 --span 500

The hypothesis is not "modes help" -- that is unfalsifiable and expensive. It is:

    a weight that measures NULL on average should measure POSITIVE in one
    regime and NEGATIVE in the other.

So this runs the same seat-balanced paired duel `verify-weight.py` runs, but
partitions the seeds by a board feature decided at setup and pools each
partition separately. If the partitions disagree, a single weight vector is
averaging over regimes and `PROFILES` is keyed on the wrong thing.

Structure exists at chi2 > 3.84 (1 df) BETWEEN regimes, with each regime's own
blocks agreeing internally. If they agree, this feature is dead -- and that
costs compute only, with no mode machinery built.
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


def vp_merchant_slots(state) -> int:
    """Non-blank slots at the two VP merchants. Nine merchant tiles -- two of
    them blank -- are shuffled across five locations at setup, so whether cotton
    or manufacturer sells into shrewsbury's +4 VP or into a dead blank is
    decided before move one and is the same for every seat."""
    n = 0
    for mid in ("shrewsbury", "nottingham"):
        for slot in state.merchants.get(mid, ()):
            if slot.kind != "blank":
                n += 1
    return n


def regime_of(seed: int, players: int, cut: int) -> str:
    return "sell_rich" if vp_merchant_slots(new_game(players, seed=seed)) >= cut \
        else "sell_poor"


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


def pool(rows):
    """Inverse-variance pool with a heterogeneity chi2, as verify-weight does."""
    w = [1 / se ** 2 for _, se in rows]
    m = sum(wi * x for wi, (x, _) in zip(w, rows)) / sum(w)
    se = sum(w) ** -0.5
    chi2 = sum(wi * (x - m) ** 2 for wi, (x, _) in zip(w, rows))
    return m, se, chi2


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True, action="append", dest="sets")
    ap.add_argument("-p", "--players", type=int, default=4, choices=(2, 3, 4))
    ap.add_argument("--blocks", default="0,500,1000")
    ap.add_argument("--span", type=int, default=500,
                    help="seeds scanned per block; the split decides how many "
                         "land in each regime")
    ap.add_argument("--cut", type=int, default=3,
                    help="sell_rich when VP-merchant slots >= this")
    ap.add_argument("-w", "--workers", type=int, default=6)
    args = ap.parse_args(argv)

    over = {}
    for pair in args.sets:
        k, _, v = pair.partition("=")
        over[k.strip()] = float(v)
    unknown = set(over) - set(HeuristicBot.DEFAULTS)
    if unknown:
        print(f"unknown weights: {sorted(unknown)}", file=sys.stderr)
        return 2
    for k, v in list(over.items()):
        if isinstance(HeuristicBot.DEFAULTS[k], int) and float(v).is_integer():
            over[k] = int(v)

    label = ", ".join(f"{k}={v:g}" for k, v in over.items())
    starts = [int(x) for x in args.blocks.split(",")]
    pats = patterns(args.players)

    # Partition first so the seat-balance pattern cycles WITHIN each regime.
    # Cycling on the global index would let seat pattern correlate with regime.
    jobs, tags = [], []
    for seed0 in starts:
        buckets: dict[str, list[int]] = {"sell_rich": [], "sell_poor": []}
        for s in range(seed0, seed0 + args.span):
            buckets[regime_of(s, args.players, args.cut)].append(s)
        for reg, seeds in buckets.items():
            for i, s in enumerate(seeds):
                jobs.append((pats[i % len(pats)], s, args.players, over))
                tags.append((seed0, reg))

    counts = {}
    for _, reg in tags:
        counts[reg] = counts.get(reg, 0) + 1
    print(f"  {label}   at {args.players}p, split on VP-merchant slots >= {args.cut}")
    print(f"  {counts}  over blocks {starts}\n", flush=True)

    t0, done, total = time.time(), 0, len(jobs)
    cells: dict[tuple, list[float]] = {}
    print(f"PROGRESS done=0 total={total} unit=games t=0", flush=True)
    with ProcessPoolExecutor(max_workers=args.workers) as pool_:
        for tag, x in zip(tags, pool_.map(_one, jobs, chunksize=4)):
            cells.setdefault(tag, []).append(x)
            done += 1
            if done % 20 == 0:
                print(f"PROGRESS done={done} total={total} unit=games "
                      f"t={time.time() - t0:.1f}", flush=True)

    pooled = {}
    for reg in ("sell_rich", "sell_poor"):
        rows = []
        print(f"\n  --- {reg} ---")
        for seed0 in starts:
            d = cells.get((seed0, reg), [])
            m, se = st.mean(d), st.stdev(d) / len(d) ** 0.5
            rows.append((m, se))
            print(f"    seed {seed0}: {m:+.2f} +- {se:.2f}  n={len(d)}")
        m, se, chi2 = pool(rows)
        agree = "blocks agree" if chi2 < 5.99 else "BLOCKS DISAGREE"
        pooled[reg] = (m, se)
        print(f"    POOLED {m:+.2f} +- {se:.2f}   {m/se:.1f} sigma, "
              f"chi2 {chi2:.2f}/2 -- {agree}")

    (a, sa), (b, sb) = pooled["sell_rich"], pooled["sell_poor"]
    diff = a - b
    sd = (sa ** 2 + sb ** 2) ** 0.5
    chi2 = (diff / sd) ** 2
    verdict = ("CONDITIONAL STRUCTURE: regimes disagree" if chi2 > 3.84
               else "no structure on this feature -- regimes agree")
    print(f"\n  sell_rich {a:+.2f} vs sell_poor {b:+.2f}")
    print(f"  difference {diff:+.2f} +- {sd:.2f}  chi2 {chi2:.2f}/1")
    print(f"  --> {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
