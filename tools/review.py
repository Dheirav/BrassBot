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

from brassbot.bots.heuristic import HeuristicBot  # noqa: E402
from brassbot.engine import apply_action, legal_actions  # noqa: E402
from brassbot.gamedata import Era, Industry  # noqa: E402
from brassbot.network import connected_locations  # noqa: E402
from brassbot.state import new_game  # noqa: E402
from play import describe  # noqa: E402
# `knobs` applies what tools/serve.py sets before it plays. Every replay so far
# came from that server, so a file that predates the "engine" key gets those
# rather than the engine defaults, which produce a shorter list and a
# divergence on move two.
from seatswap import Sources, knobs, play as swap, table  # noqa: E402


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


def beer_plan(state, seat):
    """Barrels this seat could reach, against what its unsold tiles will need.

    Praveen lost a game by 42 with two level-5 manufacturers on the board and
    one brewery, ever: an L5 needs two beer and a merchant slot holds one, so
    both were unsellable from the moment they were built. Nothing in the UI
    said so, and nothing in the review did either. The count is deliberately
    generous -- every merchant barrel on the board, not only the reachable
    ones -- so it warns when the shortfall is certain rather than merely likely.
    """
    own = sum(t.resources for _, _, t in state.all_tiles()
              if t.owner == seat and t.industry is Industry.BREWERY)
    merchant = sum(slot.beer for slot in state.merchant_slots())
    need = sum(state.data.tile(t.industry, t.level).beer_to_sell or 0
               for _, _, t in state.all_tiles()
               if t.owner == seat and not t.flipped and t.industry.is_sellable)
    return own, merchant, need


def carried(state, seat):
    """Level 2+ tiles this seat holds, and what they would score again.

    Across nine complete games canal-era VP did not predict the result at all
    (wins at 13, 13, 28, 30; losses at 8, 12, 18, 19, 24), while this did:
    wins carried 38 and 40 VP of level 2+ tiles across the boundary, losses 11
    to 29. A brewery held unflipped for the Rail Era's first round reads as
    zero on the canal scoreboard and 5 to 7 at the rail one.
    """
    tiles = [t for _, _, t in state.all_tiles()
             if t.owner == seat and t.level >= 2]
    return len(tiles), sum(state.data.tile(t.industry, t.level).vp for t in tiles)


def warnings_for(state, seat):
    """Checks that fire on the position, not on the choice.

    Each returns a KIND as well as its text, and the report prints the first
    time each kind was true. A beer shortfall stays true for the rest of the
    game and its numbers drift, so printing every wording of it buries
    everything else.
    """
    out = []
    own, merchant, need = beer_plan(state, seat)
    if need > own + merchant:
        out.append(("beer-short",
                    f"{need} beer needed to sell the tiles you have built and "
                    f"only {own + merchant} exists anywhere ({own} yours, "
                    f"{merchant} merchant). Some of them cannot be sold at all."))
    elif need > own:
        out.append(("beer-borrowed",
                    f"{need} beer needed and only {own} of it yours; the rest "
                    f"is merchant beer that anyone selling first can take."))
    # The last canal round, once: what crosses the boundary scores twice.
    if state.era is Era.CANAL and state.round == state.rounds_this_era:
        k, vp = carried(state, seat)
        if vp < 30:
            out.append(("thin-boundary",
                        f"carrying {k} level 2+ tiles worth {vp} VP into the "
                        f"Rail Era, where they score a second time. Games won "
                        f"in this corpus carried about seven, worth 35 to 40."))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay", help="a .replay.json written by the UI's Export log")
    ap.add_argument("-n", "--worst", type=int, default=8,
                    help="how many of the widest gaps to print")
    ap.add_argument("--all", action="store_true", help="print every decision")
    ap.add_argument("--against-bot", action="store_true",
                    help="also play the bot from your seat and put the two "
                         "games side by side, VP by source")
    args = ap.parse_args(argv)

    rep = json.loads(Path(args.replay).read_text())
    seat, name = rep["seat"], rep.get("name", "You")
    # The indices were drawn against a list built with these settings; replaying
    # with any others reads the wrong action.
    knobs(rep)
    state = new_game(rep["players"], seed=rep["seed"])
    judge = HeuristicBot(seed=0)
    # The replay is traced whether or not the swap is asked for: it is cheap,
    # and it is what makes the swap's table comparable.
    src = Sources(state, rep["players"])
    src.__enter__()

    total = len(rep["actions"])
    print(f"  {name}, seat {seat}, {rep['players']}p, seed {rep['seed']}, "
          f"{total} actions", flush=True)
    print(f"PROGRESS done=0 total={total} unit=actions t=0", flush=True)

    t0, reviewed, flags = time.time(), [], {}
    for step, idx in enumerate(rep["actions"]):
        actions = legal_actions(state)
        if not actions:
            break
        if idx >= len(actions):
            print(f"  replay diverged at action {step}: index {idx} of "
                  f"{len(actions)} legal", flush=True)
            src.__exit__()
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
        if state.current.idx == seat:
            for kind, text in warnings_for(state, seat):
                flags.setdefault(kind, {"era": state.era.value,
                                        "round": state.round,
                                        "step": step, "text": text})
        src.step(state.current.idx, chosen)
        if step % 10 == 0:
            print(f"PROGRESS done={step} total={total} unit=actions "
                  f"t={time.time()-t0:.1f}", flush=True)

    src.__exit__()
    finals = [p.vp for p in state.players]
    print(f"\n  replayed to the end: final VP {finals}, "
          f"{'finished' if state.finished else 'INCOMPLETE'}")
    if state.finished:
        src.check()
    if not reviewed:
        print("  no decisions to review")
        return 0

    top = sum(1 for r in reviewed if r["rank"] == 1)
    import statistics as st
    print(f"\n  {len(reviewed)} of your decisions had a real choice")
    print(f"  agreed with the bot's first pick: {top} ({100*top/len(reviewed):.0f}%)")
    print(f"  median gap to its pick: {st.median(r['gap'] for r in reviewed):.2f}"
          f"   mean {st.mean(r['gap'] for r in reviewed):.2f}")

    if flags:
        print("\n  what the position was telling you, the first turn it was true:")
        for f in sorted(flags.values(), key=lambda f: f["step"]):
            print(f"    {f['era']:<5} r{f['round']:<2}  {f['text']}")

    show = reviewed if args.all else sorted(reviewed, key=lambda r: -r["gap"])[:args.worst]
    print(f"\n  {'the widest gaps' if not args.all else 'every decision'}:")
    for r in show:
        print(f"    {r['era']:<5} r{r['round']:<2} #{r['step']:<3} "
              f"rank {r['rank']:>3}/{r['of']:<3} gap {r['gap']:>6.2f}")
        print(f"        you  {r['played'][:78]}")
        if r["rank"] != 1:
            print(f"        bot  {r['best'][:78]}")

    if args.against_bot and state.finished:
        # The seated bot gets the seed the server would have given that seat,
        # so this is the game the bot would have played had it sat there.
        t1 = time.time()
        swapped, theirs = swap(rep["seed"], rep["players"],
                               rep.get("opponent", "heuristic"),
                               rep["seed"] * 10 + seat, seat)
        vp = [p.vp for p in swapped.players]
        rank = 1 + sum(1 for j, v in enumerate(vp) if j != seat and v > vp[seat])
        print(f"\n  the bot from your seat, same deal, same opponents "
              f"({time.time() - t1:.0f}s): final VP {vp}, seat {seat} = {vp[seat]}, "
              f"finished #{rank}")
        print(f"  you scored {finals[seat]}, finished "
              f"#{1 + sum(1 for j, v in enumerate(finals) if j != seat and v > finals[seat])}")
        print("\n  where the difference came from, VP by source (tiles or links built):")
        print(table(name, src, seat, theirs))
        print("\n  read the big rows. A source the bot never scored and you did is "
              "something\n  it cannot plan for; one you both scored is a difference "
              "of degree.")
    elif args.against_bot:
        print("\n  --against-bot skipped: the replay did not reach the end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
