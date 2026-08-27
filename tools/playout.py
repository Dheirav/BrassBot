"""Single-game playout with a round-by-round trace, for debugging the engine.

For measuring bot strength use tools/evaluate.py instead -- this prints one
game, not a distribution.
"""
import argparse
import sys

from brassbot.bots import REGISTRY, make
from brassbot.engine import apply_action, legal_actions
from brassbot.state import new_game


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bot", nargs="?", default="greedy", choices=sorted(REGISTRY))
    ap.add_argument("-s", "--seed", type=int, default=0)
    ap.add_argument("-q", "--quiet", action="store_true", help="final scores only")
    args = ap.parse_args(argv)

    state = new_game(4, seed=args.seed)
    bots = [make(args.bot, seed=args.seed * 1000 + i) for i in range(4)]
    last = None

    while not state.finished:
        key = (state.era, state.round)
        if key != last and not args.quiet:
            built = sum(1 for _ in state.all_tiles())
            flipped = sum(1 for _, _, t in state.all_tiles() if t.flipped)
            print(f"{state.era.value:<5} r{state.round}: tiles={built:<3} flipped={flipped:<3} "
                  f"links={len(state.links):<3} "
                  f"money={[p.money for p in state.players]} "
                  f"income={[p.income for p in state.players]}")
            last = key
        actions = legal_actions(state)
        if not actions:
            raise RuntimeError(f"no legal action at era={state.era} round={state.round}")
        apply_action(state, bots[state.current.idx].choose(state, actions))

    print("final:", sorted((p.vp for p in state.players), reverse=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
