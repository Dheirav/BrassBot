"""Bot registry, so the harness can name opponents on the command line."""

from .base import Bot
from .book import BookBot
from .commit import CommitBot
from .heuristic import HeuristicBot
from .learned import LearnedBot
from .mcts import MCTSBot
from .simple import GreedyBot, RandomBot

REGISTRY: dict[str, type[Bot]] = {
    RandomBot.name: RandomBot,
    GreedyBot.name: GreedyBot,
    HeuristicBot.name: HeuristicBot,
    MCTSBot.name: MCTSBot,
    BookBot.name: BookBot,
    CommitBot.name: CommitBot,
    LearnedBot.name: LearnedBot,
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
        text = value.strip()
        # Keep whole numbers as ints: some parameters are counts (iterations,
        # widths) and float counts break range() and slicing.
        try:
            weights[key.strip()] = int(text)
        except ValueError:
            weights[key.strip()] = float(text)
    return cls(seed=seed, **weights)


__all__ = ["Bot", "RandomBot", "GreedyBot", "HeuristicBot", "MCTSBot", "BookBot", "CommitBot", "LearnedBot", "REGISTRY", "make"]
