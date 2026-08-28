"""Train the learned value function and save it for brassbot.bots.learned.

Run with .venv-ml/bin/python -- scikit-learn lives there, not in the engine's
own venv. The model is a build artifact, so models/ is gitignored; retrain with
this script rather than committing a pickle whose format tracks sklearn's.
"""
from __future__ import annotations

import os

# Pin the maths libraries to one thread BEFORE numpy/sklearn are imported. Each
# pool worker otherwise opens its own OpenMP pool for predict(), and eight
# workers on eight cores produced a load average of 32 -- a run that should have
# taken minutes was still going after an hour.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import sys
import time
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, ".")

from tools.value_probe import play  # noqa: E402


_LEARNER = None


def _worker_learner():
    """One bot per worker process: the 4MB model is unpickled once, not once
    per game."""
    global _LEARNER
    if _LEARNER is None:
        from brassbot.bots import make
        _LEARNER = make("learned")
        _LEARNER.model  # force the load now
    return _LEARNER


def play_onpolicy(seed: int):
    """A game where the learned bot itself is choosing, labelled the same way.

    Training only on heuristic games teaches the model what positions are worth
    *when the heuristic plays on from them*. Acting on it then walks into states
    the training set never contained, where the prediction is unconstrained
    extrapolation -- the first model passed 45 times a game, having never seen a
    Pass in training, while scoring 36 VP. Adding the states it actually reaches
    is the standard correction.
    """
    from brassbot.bots import make
    from brassbot.engine import apply_action, legal_actions
    from brassbot.features import extract_extended
    from brassbot.state import new_game

    learner = _worker_learner()
    state = new_game(4, seed=seed)
    bots = [learner] + [make("heuristic") for _ in range(3)]
    rows = []
    while not state.finished:
        stage = (1 if state.era.name == "RAIL" else 0, state.round)
        for seat in range(4):
            rows.append((extract_extended(state, seat), stage, seat, 0.0))
        apply_action(state, bots[state.current.idx].choose(
            state, legal_actions(state)))
    final = [pl.vp for pl in state.players]
    return [(f, st, final[s], hv) for f, st, s, hv in rows]


def main(games: int = 600, out: str = "models/value_4p.joblib",
         onpolicy: int = 0):
    t0 = time.time()
    with Pool(8) as pool:
        per_game = pool.map(play, range(30000, 30000 + games))
        rows = [r for g in per_game for r in g]
        if onpolicy:
            # Needs a model already on disk to play with; this is round two.
            extra = pool.map(play_onpolicy, range(40000, 40000 + onpolicy))
            n = sum(len(g) for g in extra)
            rows += [r for g in extra for r in g]
            print(f"added {n} on-policy rows from {onpolicy} games", flush=True)
    x = np.array([r[0] for r in rows], dtype=np.float64)
    y = np.array([r[2] for r in rows], dtype=np.float64)
    print(f"{len(rows)} rows, {x.shape[1]} features, "
          f"{time.time() - t0:.0f}s to generate", flush=True)

    from joblib import dump
    from sklearn.ensemble import HistGradientBoostingRegressor

    model = HistGradientBoostingRegressor(
        max_iter=1200, learning_rate=0.06, max_leaf_nodes=31,
        early_stopping=True, validation_fraction=0.15,
        n_iter_no_change=40, random_state=0,
    ).fit(x, y)
    print(f"stopped after {model.n_iter_} rounds", flush=True)
    dump(model, out)
    print(f"saved {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 600,
         onpolicy=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
