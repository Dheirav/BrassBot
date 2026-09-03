"""Rebuild a real game's final board from its log and score it with OUR engine.

The only external check this project has. Every other reference for correct play
is a quote from a guide or an agent's write-up, and self-play cannot catch a
scoring error at all -- every bot would be wrong in the same direction and
nothing would look strange.

The rebuild is exact for what the log records, and reconciles: every logged build
ends as placed, overbuilt, wiped at the era change, or reported as failed, and
the resulting tile count matches the prediction in all six logs so far. Slot
choice inside a town is not in the log and does not need to be -- link scoring
reads the town's tiles, not the slot index.

What the log does NOT record is which tiles ended FLIPPED, because resource tiles
flip silently as the board consumes their cubes. So this brackets rather than
asserts:

    low    only tiles the log shows being sold
    high   every tile flipped

RESULT on six games, 24 seats: no scoring bug found. Our totals land within about
+-10 VP of the reported ones on scores of 70-130, and the errors are MIXED IN
SIGN -- sometimes over, sometimes under. A missing or double-counted rule would
be one-signed and much larger, so this rules out a big systematic error without
proving the small ones absent. Nine of 24 seats fall outside the bracket, all
explicable by the two known residuals: four builds in 256 that greedy slot choice
could not place, and the unknown flip state of resource tiles.

To tighten it further you would have to track resource consumption to determine
flips exactly, which means simulating who supplied each cube -- not in the log.

    PYTHONPATH=. .venv/bin/python tools/check_scoring.py logs/*.log
"""
from __future__ import annotations

import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from brassbot.engine import build_targets, score_era                       # noqa: E402
from brassbot.evaluate import new_game                      # noqa: E402
from brassbot.gamedata import Era, Industry                 # noqa: E402
from brassbot.state import Tile                             # noqa: E402
from tools.import_log import parse                          # noqa: E402

INDUSTRY = {"brewery": Industry.BREWERY, "coal": Industry.COAL_MINE,
            "iron": Industry.IRON_WORKS, "cotton": Industry.COTTON_MILL,
            "manufacturer": Industry.MANUFACTURER, "pottery": Industry.POTTERY}


def town_id(name, towns, merchants=()):
    """'Burton-upon-Trent' -> 'burton_on_trent', 'Farm Brewery (S)' -> farm_southern.

    Merchant locations are legal link endpoints but are not towns, so they are
    matched too -- a link to Oxford is a link, not a parse failure.
    """
    n = name.strip().lower()
    if "farm" in n:
        return "farm_southern" if "(s)" in n else "farm_northern"
    key = re.sub(r"[^a-z]+", "_", n.replace("-upon-", "_on_")).strip("_")
    if key in towns or key in merchants:
        return key
    # fall back on a loose match, so a new spelling is reported not guessed
    for t in list(towns) + list(merchants):
        if t.replace("_", "") == key.replace("_", ""):
            return t
    return None


def rebuild(moves, players, upper_bound, trace=None):
    """Place every logged tile and link, using the engine's own placement rules.

    Slot choice inside a town is not in the log, but it does not matter: link
    scoring reads the TOWN's tiles, not the slot index. What does matter is
    getting overbuilds and the era wipe right, and those are reconciled --
    every logged build must end as placed, overbuilt, wiped, or reported.
    """
    state = new_game(len(players), seed=1)
    seat = {p: i for i, p in enumerate(players)}
    for t in state.tiles:
        state.tiles[t] = [None] * len(state.tiles[t])
    state.links.clear()

    sold = set()
    for m in moves:
        if m.kind == "sell":
            for t in m.detail.get("towns", []):
                sold.add(town_id(t, state.data.towns, state.data.merchants))

    by_ends = [(frozenset(l.ends), l.id) for l in state.data.links]
    tally = {"built": 0, "placed": 0, "overbuilt": 0, "wiped": 0, "failed": 0,
             "links": 0, "links_placed": 0, "links_cleared": 0}
    unknown, wiped_done = set(), False

    for m in moves:
        if m.who not in seat:
            continue
        if m.era == "rail" and not wiped_done:
            wiped_done = True
            for town, slots in state.tiles.items():
                for i, t in enumerate(slots):
                    if t is not None and t.level == 1:
                        slots[i] = None
                        tally["wiped"] += 1
            tally["links_cleared"] += len(state.links)
            state.links.clear()

        if m.kind == "build":
            tally["built"] += 1
            tid = town_id(m.detail["town"], state.data.towns, state.data.merchants)
            ind = INDUSTRY.get(m.detail["industry"])
            if tid is None or ind is None:
                unknown.add(f"{m.detail['town']}/{m.detail['industry']}")
                tally["failed"] += 1
                continue
            lvl = m.detail["level"]
            options = list(build_targets(state, seat[m.who], tid, ind, lvl))
            if not options:
                # No legal placement: the log shows a build our rules refuse.
                unknown.add(f"no-slot:{tid}/{ind.value}L{lvl}")
                tally["failed"] += 1
                continue
            idx, overbuilt = options[0]
            if overbuilt is not None:
                tally["overbuilt"] += 1
            else:
                tally["placed"] += 1
            era = Era.CANAL if m.era == "canal" else Era.RAIL
            state.tiles[tid][idx] = Tile(seat[m.who], ind, lvl, era,
                                         flipped=upper_bound or tid in sold)
        elif m.kind == "network":
            for ends in m.detail["links"]:
                tally["links"] += 1
                a, b = (town_id(e, state.data.towns, state.data.merchants)
                        for e in ends[:2])
                if not a or not b:
                    unknown.add("|".join(map(str, ends[:2]))); continue
                want = frozenset((a, b))
                lid = next((i for e, i in by_ends if want <= e), None)
                if lid is None:
                    unknown.add(f"{a}|{b}"); continue
                state.links[lid] = seat[m.who]
                tally["links_placed"] += 1

    state.era = Era.RAIL
    if trace is not None:
        trace.update(tally)
    return state, unknown


def main(argv=None):
    files = argv or sys.argv[1:]
    if not files:
        print(__doc__); return 1
    print(f"  {'log':<26}{'player':<17}{'reported':>9}{'low':>7}{'high':>7}  verdict")
    for f in files:
        moves, players, scores = parse(open(f, encoding="utf-8").read())
        if not players:
            players = list(dict.fromkeys(m.who for m in moves))
        rep = {}
        # "+92 VP (110)" -- the AWARD is what score_era computes; the bracket is
        # the running total including the canal era.
        for who, award in re.findall(r"([^,]+?) \+(\d+) VP \(\d+\)",
                                     scores.get("rail", "")):
            rep[who.strip()] = int(award)
        if not rep:
            print(f"  {pathlib.Path(f).name:<26}no final scores in log"); continue
        bounds = {}
        for ub in (False, True):
            st, unknown = rebuild(moves, players, ub)
            before = [p.vp for p in st.players]
            score_era(st)
            for i, p in enumerate(players):
                bounds.setdefault(p, []).append(st.players[i].vp - before[i])
        for p in players:
            lo, hi = bounds[p]
            got = rep.get(p)
            ok = "ok" if got is not None and lo <= got <= hi else "OUTSIDE"
            print(f"  {pathlib.Path(f).name[:24]:<26}{p[:16]:<17}"
                  f"{got if got is not None else '?':>9}{lo:>7}{hi:>7}  {ok}")
        if unknown:
            print(f"    unmapped: {sorted(map(str, unknown))[:5]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
