"""A bot that ranks candidate moves with a learned value function.

The probe in docs/research-landscape.md found boosted trees predict a seat's
final score better than the hand-crafted evaluation does, on the job the
evaluation actually performs -- ranking siblings inside one decision. This is
the test of whether that turns into victory points.

scikit-learn is imported lazily, inside the loader. The engine's own venv does
not have it, and importing at module scope would break `brassbot.bots` for
everything else; the model only loads when this bot is actually built.

Deliberately 1-ply, like the heuristic. A tree ensemble is far too slow for an
MCTS leaf, and search was measured not to be the constraint anyway.
"""

from __future__ import annotations

import os

from ..engine import apply_action
from ..features import extract_extended
from .base import Bot

DEFAULT_MODEL = "models/value_4p.joblib"


class LearnedBot(Bot):
    name = "learned"

    def __init__(self, seed: int = 0, **params):
        super().__init__(seed)
        self.path = params.pop("path", None) or os.environ.get(
            "BRASSBOT_VALUE_MODEL", DEFAULT_MODEL)
        # rival=1 ranks by our score net of the best opponent's, as
        # position_value does; rival=0 ranks by our own predicted score alone.
        self.rival = float(params.pop("rival", 0.0))
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from joblib import load
            self._model = load(self.path)
        return self._model

    def choose(self, state, actions):
        if len(actions) == 1:
            return actions[0]
        me = state.current.idx
        seats = range(state.n_players)

        rows, probes = [], []
        for action in actions:
            probe = state.clone()
            apply_action(probe, action)
            probes.append(probe)
            if self.rival:
                rows.extend(extract_extended(probe, s) for s in seats)
            else:
                rows.append(extract_extended(probe, me))

        import numpy as np
        pred = self.model.predict(np.array(rows, dtype=np.float64))

        best_value = None
        best_action = None
        n = state.n_players if self.rival else 1
        for i, action in enumerate(actions):
            if self.rival:
                block = pred[i * n:(i + 1) * n]
                rivals = [v for s, v in enumerate(block) if s != me]
                value = block[me] - self.rival * (max(rivals) if rivals else 0.0)
            else:
                value = pred[i]
            # Strict >, so ties fall to generation order and play stays
            # reproducible from the seed alone.
            if best_value is None or value > best_value + 1e-9:
                best_value, best_action = value, action
        return best_action
