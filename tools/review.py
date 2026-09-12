"""Replay a logged UI game and review the decisions one at a time.

    PYTHONPATH=. .venv/bin/python tools/review.py logs/<game>.replay.json

Counting actions across whole games cannot answer "what should I have done":
two games with identical build and link counts can be a 155 and a 101. This
looks at decisions instead. The engine is deterministic, so the seed and the
chosen indices reconstruct the game exactly, including the hand and the market
that the pasted Boomforge logs can never recover.

At each of your turns it enumerates what was legal, scores every option the way
the bot scores a position, and reports where your choice ranked.

Read the gaps, not the ranks. The bot is not obviously stronger than you, so a
disagreement means "worth a look", and the many decisions where everything
scores within a point of each other mean nothing at all.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import brassbot.engine as _engine  # noqa: E402
from brassbot.bots.heuristic import HeuristicBot  # noqa: E402
from brassbot.engine import apply_action, legal_actions  # noqa: E402

# What tools/serve.py sets before it plays. Every replay so far came from that
# server, so a file that predates the "engine" key gets these rather than the
# engine defaults, which produce a shorter list and a divergence on move two.
SERVE_KNOBS = {"MAX_DISCARD_VARIANTS": 8, "SCOUT_POOL": 8, "MAX_SCOUT_VARIANTS": 56}
from brassbot.state import new_game  # noqa: E402
from play import describe  # noqa: E402


def score_options(bot, state, seat, actions):
    """What each option is worth, by the bot's own position value.

    One ply: apply the action and read the resulting position. That is the same
    quantity `pair_search` searches over, without the second half of the turn,
    so it ranks single moves on the measure the bot actually optimises.
    """
    out = []
    for a in actions:
        probe = state.clone()
        apply_action(probe, a)
        out.append(bot.position_value(probe, seat))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay", help="a .replay.json written by the UI's Export log")
    ap.add_argument("-n", "--worst", type=int, default=8,
                    help="how many of the widest gaps to print")
    ap.add_argument("--all", action="store_true", help="print every decision")
    args = ap.parse_args(argv)

    rep = json.loads(Path(args.replay).read_text())
    seat, name = rep["seat"], rep.get("name", "You")
    # The indices were drawn against a list built with these settings; replaying
    # with any others reads the wrong action.
    for k, v in rep.get("engine", SERVE_KNOBS).items():
        setattr(_engine, k, v)
    state = new_game(rep["players"], seed=rep["seed"])
    judge = HeuristicBot(seed=0)

    mine = [i for i in range(len(rep["actions"]))]
    total = len(rep["actions"])
    print(f"  {name}, seat {seat}, {rep['players']}p, seed {rep['seed']}, "
          f"{total} actions", flush=True)
    print(f"PROGRESS done=0 total={total} unit=actions t=0", flush=True)

    t0, reviewed = time.time(), []
    for step, idx in enumerate(rep["actions"]):
        actions = legal_actions(state)
        if not actions:
            break
        if idx >= len(actions):
            print(f"  replay diverged at action {step}: index {idx} of "
                  f"{len(actions)} legal", flush=True)
            return 2
        chosen = actions[idx]
        if state.current.idx == seat and len(actions) > 1:
            vals = score_options(judge, state, seat, actions)
            best = max(range(len(vals)), key=lambda i: vals[i])
            order = sorted(range(len(vals)), key=lambda i: -vals[i])
            reviewed.append({
                "step": step, "era": state.era.value, "round": state.round,
                "played": describe(state, chosen).split("card:")[0].strip(),
                "best": describe(state, actions[best]).split("card:")[0].strip(),
                "rank": order.index(idx) + 1, "of": len(actions),
                "gap": vals[best] - vals[idx],
            })
        apply_action(state, chosen)
        if step % 10 == 0:
            print(f"PROGRESS done={step} total={total} unit=actions "
                  f"t={time.time()-t0:.1f}", flush=True)

    finals = [p.vp for p in state.players]
    print(f"\n  replayed to the end: final VP {finals}, "
          f"{'finished' if state.finished else 'INCOMPLETE'}")
    if not reviewed:
        print("  no decisions to review")
        return 0

    top = sum(1 for r in reviewed if r["rank"] == 1)
    import statistics as st
    print(f"\n  {len(reviewed)} of your decisions had a real choice")
    print(f"  agreed with the bot's first pick: {top} ({100*top/len(reviewed):.0f}%)")
    print(f"  median gap to its pick: {st.median(r['gap'] for r in reviewed):.2f}"
          f"   mean {st.mean(r['gap'] for r in reviewed):.2f}")

    show = reviewed if args.all else sorted(reviewed, key=lambda r: -r["gap"])[:args.worst]
    print(f"\n  {'the widest gaps' if not args.all else 'every decision'}:")
    for r in show:
        print(f"    {r['era']:<5} r{r['round']:<2} #{r['step']:<3} "
              f"rank {r['rank']:>3}/{r['of']:<3} gap {r['gap']:>6.2f}")
        print(f"        you  {r['played'][:78]}")
        if r["rank"] != 1:
            print(f"        bot  {r['best'][:78]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
