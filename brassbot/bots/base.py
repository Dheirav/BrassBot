"""Bot interface.

A bot is handed the live state and the legal actions, and returns one of them.

**The state is read-only.** It is not cloned before the call, because search
bots clone far more selectively than a blanket copy would. A bot that wants to
look ahead must call ``state.clone()`` itself.
"""

from __future__ import annotations

import random

from ..actions import Action
from ..state import GameState


class Bot:
    name = "bot"

    def __init__(self, seed: int = 0):
        self.rng = random.Random(seed)

    def choose(self, state: GameState, actions: list[Action]) -> Action:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<{self.name}>"
