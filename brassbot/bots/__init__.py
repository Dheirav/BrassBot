"""Bot registry, so the harness can name opponents on the command line."""

from .base import Bot
from .heuristic import HeuristicBot
from .simple import GreedyBot, RandomBot

REGISTRY: dict[str, type[Bot]] = {
    RandomBot.name: RandomBot,
    GreedyBot.name: GreedyBot,
    HeuristicBot.name: HeuristicBot,
}


def make(spec: str, seed: int = 0) -> Bot:
    """Build a bot from a spec string.

    Either a bare name (``"greedy"``) or a name with weight overrides
    (``"heuristic:income=0.3,debt=0.5"``). Keeping it a string means a tuning
    run can ship candidates to worker processes without pickling classes.
    """
    name, _, overrides = spec.partition(":")
    try:
        cls = REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown bot {name!r}; known: {sorted(REGISTRY)}") from None

    if not overrides:
        return cls(seed=seed)

    weights = {}
    for pair in overrides.split(","):
        if not pair.strip():
            continue
        key, _, value = pair.partition("=")
        weights[key.strip()] = float(value)
    return cls(seed=seed, **weights)


__all__ = ["Bot", "RandomBot", "GreedyBot", "HeuristicBot", "REGISTRY", "make"]
