"""What the bot plays in the first three rounds, by turn-order position.

Self-play, four seats, the shipped heuristic. For every action in Canal rounds
1 to 3 it records the round, the seat's position in that round's turn order,
the action kind and, for a Build, the industry. Emits PROGRESS lines for
tools/watch-progress.sh and writes a JSON tally.

    PYTHONPATH=. .venv/bin/python tools/openings.py 60 runs/openings.json
"""
from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from brassbot.actions import Build  # noqa: E402
from brassbot.bots import make  # noqa: E402
from brassbot.engine import apply_action, legal_actions  # noqa: E402
from brassbot.state import new_game  # noqa: E402


def main() -> None:
    n, out = int(sys.argv[1]), sys.argv[2]
    tally = collections.defaultdict(collections.Counter)
    built = collections.defaultdict(collections.Counter)
    t0 = time.time()
    for g in range(n):
        seed = 5000 + g
        st = new_game(4, seed=seed)
        bots = [make("heuristic", seed=seed * 10 + i) for i in range(4)]
        while not st.finished and st.era.value == "canal" and st.round <= 3:
            acts = legal_actions(st)
            if not acts:
                break
            who = st.current.idx
            pos = st.turn_order.index(who) + 1
            a = bots[who].choose(st, acts)
            tally[(st.round, pos)][type(a).__name__] += 1
            if isinstance(a, Build):
                built[(st.round, pos)][a.industry.value] += 1
            apply_action(st, a)
        print(f"PROGRESS done={g + 1} total={n} unit=games t={time.time() - t0:.1f}",
              flush=True)
    Path(out).write_text(json.dumps({
        "games": n,
        "tally": {f"{r},{p}": dict(c) for (r, p), c in tally.items()},
        "built": {f"{r},{p}": dict(c) for (r, p), c in built.items()},
    }, indent=1))
    print(f"total {n} games -> {out}", flush=True)


if __name__ == "__main__":
    main()
