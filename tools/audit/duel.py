"""2v2 duel: two variant seats against two baseline seats, seat-balanced.

The 1-vs-3 harness gives the odd seat out a differentiation bonus that shows up
as a small positive delta for almost any perturbation. A 2v2 with the six
balanced seat pairings cancels it: every seat is variant in exactly half the
patterns.
"""
import statistics as st, sys
from concurrent.futures import ProcessPoolExecutor

from brassbot.evaluate import play_game

PATTERNS = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]


def job(a):
    seats, seed = a
    return play_game(seats, seed, 4)


def main():
    games = int(sys.argv[1]); seed0 = int(sys.argv[2])
    base = sys.argv[3]; var = sys.argv[4]
    jobs = []
    for g in range(games):
        pat = PATTERNS[g % len(PATTERNS)]
        seats = [var if s in pat else base for s in range(4)]
        jobs.append((seats, seed0 + g))
    with ProcessPoolExecutor(max_workers=4) as pool:
        res = list(pool.map(job, jobs, chunksize=4))
    dv = []; wv = []; wb = []
    for r, (seats, _s) in zip(res, jobs):
        v = [r.scores[i] for i in range(4) if seats[i] == var]
        b = [r.scores[i] for i in range(4) if seats[i] == base]
        dv.append(st.fmean(v) - st.fmean(b))
        wv.append(sum((1.0 / len(r.winners)) for i in r.winners if seats[i] == var))
        wb.append(sum((1.0 / len(r.winners)) for i in r.winners if seats[i] == base))
    se = st.stdev(dv) / len(dv) ** 0.5
    print(f"2v2 {var}  vs  {base}   n={games} seeds {seed0}+")
    print(f"   mean VP per seat: variant-minus-baseline {st.fmean(dv):+.2f} +- {se:.2f} "
          f"({st.fmean(dv)/se:.1f} sigma)")
    print(f"   win share: variant {100*st.fmean(wv):.1f}%  baseline {100*st.fmean(wb):.1f}%")


if __name__ == "__main__":
    main()
