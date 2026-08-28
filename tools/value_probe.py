"""Does a learned value function beat the hand-crafted one at the job it does?

Extends the earlier probe (docs/research-landscape.md section 6) in the two
directions that one explicitly left open: nonlinearity, and richer features.

The metric is Spearman against final VP *within a game stage*. Across stages is
a trap -- a Rail Era position already has most of its score banked, so a model
scores 0.700 mostly by learning what turn it is. The evaluation never does that:
it ranks sibling positions inside one decision, where the stage is identical for
every candidate.

Baseline to beat: hand-crafted 0.605, linear on the original 45 features 0.595.

Run with .venv-ml/bin/python -- a separate venv holding scikit-learn, kept out
of the project's .venv so the engine's dependencies stay clean.
"""
from __future__ import annotations

import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, ".")

from brassbot import features as F                      # noqa: E402
from brassbot.features import extra_features           # noqa: E402
from brassbot.bots import make                          # noqa: E402
from brassbot.engine import apply_action, legal_actions  # noqa: E402
from brassbot.gamedata import Industry                  # noqa: E402
from brassbot.state import new_game                     # noqa: E402

def play(seed: int):
    """One game; every (state, seat) with the seat's final score as the label."""
    bot = make("heuristic")
    ev = make("heuristic")
    state = new_game(4, seed=seed)
    rows = []
    while not state.finished:
        stage = (1 if state.era.name == "RAIL" else 0, state.round)
        ev.w = ev.weights_for(state.n_players)
        for seat in range(4):
            rows.append((
                F.extract_extended(state, seat),
                stage, seat, ev.player_value(state, seat),
            ))
        apply_action(state, bot.choose(state, legal_actions(state)))
    final = [pl.vp for pl in state.players]
    return [(f, st, final[s], hv) for f, st, s, hv in rows]


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3:
        return float("nan")
    ra, rb = _rank(a), _rank(b)
    ra = ra - ra.mean()
    rb = rb - rb.mean()
    denom = np.sqrt((ra @ ra) * (rb @ rb))
    return float(ra @ rb / denom) if denom else float("nan")


def _rank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=np.float64)
    ranks[order] = np.arange(len(x), dtype=np.float64)
    return ranks


def within_stage(stages, truth, pred) -> float:
    """Spearman inside each stage, averaged weighted by stage size."""
    total = weight = 0.0
    for stage in set(stages):
        mask = np.array([s == stage for s in stages])
        if mask.sum() < 5:
            continue
        r = spearman(truth[mask], pred[mask])
        if not np.isnan(r):
            total += r * mask.sum()
            weight += mask.sum()
    return total / weight if weight else float("nan")


def fit_models(xtr, ytr, xte, n_orig):
    """Linear and gradient-boosted fits, each regularised on its own terms.

    Gradient boosting rather than a polynomial expansion: the hand-rolled
    degree-2 ridge used a single lambda for 2,600 terms and scored *below* the
    linear fit, which measures the fitting, not the data. Trees need no scaling,
    find interactions on their own, and early-stop against a validation split.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.linear_model import RidgeCV

    out = {}
    for label, cols in (("original 45 features", slice(0, n_orig)),
                        ("+track features", slice(None))):
        a_tr, a_te = xtr[:, cols], xte[:, cols]

        ridge = RidgeCV(alphas=np.logspace(-2, 4, 25)).fit(a_tr, ytr)
        out[f"linear, {label}"] = ridge.predict(a_te)

        gbm = HistGradientBoostingRegressor(
            max_iter=600, learning_rate=0.06, max_leaf_nodes=31,
            early_stopping=True, validation_fraction=0.15,
            n_iter_no_change=30, random_state=0,
        ).fit(a_tr, ytr)
        out[f"boosted trees, {label}"] = gbm.predict(a_te)
        out[f"boosted trees, {label} __iters"] = gbm.n_iter_
    return out


def main(games: int = 240):
    with Pool(8) as pool:
        per_game = pool.map(play, range(games))

    split = int(games * 0.7)
    train = [r for g in per_game[:split] for r in g]
    test = [r for g in per_game[split:] for r in g]
    print(f"{len(train)} train rows, {len(test)} test rows, "
          f"{len(train[0][0])} features\n")

    xtr = np.array([r[0] for r in train], dtype=np.float64)
    xte = np.array([r[0] for r in test], dtype=np.float64)
    ytr = np.array([r[2] for r in train], dtype=np.float64)
    yte = np.array([r[2] for r in test], dtype=np.float64)
    stages_te = [r[1] for r in test]
    hand_te = np.array([r[3] for r in test], dtype=np.float64)

    n_orig = len(F.NAMES)
    results = {"hand-crafted evaluation": hand_te}
    fitted = fit_models(xtr, ytr, xte, n_orig)
    iters = {k: v for k, v in fitted.items() if k.endswith("__iters")}
    results.update({k: v for k, v in fitted.items() if not k.endswith("__iters")})

    print(f"{'predictor':>34} {'across stages':>14} {'within stage':>13}")
    for label, pred in results.items():
        print(f"{label:>34} {spearman(yte, pred):>14.3f} "
              f"{within_stage(stages_te, yte, pred):>13.3f}")
    for k, v in iters.items():
        print(f"\n{k.replace(' __iters', '')}: {v} boosting rounds before early stop")
    print("\nbaseline from the earlier probe: hand-crafted 0.605, linear 0.595")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 240)
