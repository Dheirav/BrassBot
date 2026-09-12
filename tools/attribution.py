"""How much VP each action actually produced, and how much each kind of action
correlates with a seat's final score.

Two different questions, kept apart because they have different standing.

The first is exact. Every VP in Brass is scored off one tile or one link, and
each of those was placed by one action, except the few a Sell earns directly as
a merchant bonus (Shrewsbury 4, Nottingham 3). So a Build's, a Network's or a
Sell's realised VP is a fact of the record, not an estimate: the tile placed
at step 41 scored 5 in the Canal Era and 5 again in the Rail Era. A Loan,
Develop or Scout places nothing and so scores nothing here, by construction.
That is the point, not a limitation: it separates what scored from what merely
made scoring possible. The sum over a seat's actions is asserted equal to its
final VP, and the first run of this failed that check by exactly one seat's
merchant bonuses.

The second is a correlation. For the enablers, the only measure available is
how a seat's final VP moves with how many of each action it took, across many
games. That is an association between a policy's choices and its outcomes, and
it says nothing about what would have happened had the choice gone the other
way. It is reported as such.

    PYTHONPATH=. .venv/bin/python tools/attribution.py 40 runs/attribution.json
    PYTHONPATH=. .venv/bin/python tools/attribution.py --report runs/attribution.json
"""
from __future__ import annotations

import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import brassbot.engine as engine  # noqa: E402
from brassbot.actions import Build, Network, Sell  # noqa: E402
from brassbot.bots import make  # noqa: E402
from brassbot.engine import apply_action, legal_actions, link_icons_at  # noqa: E402
from brassbot.state import new_game  # noqa: E402


def play(seed: int, rows: list, finals: list) -> None:
    """One self-play game, appending one row per action with its realised VP."""
    st = new_game(4, seed=seed)
    bots = [make("heuristic", seed=seed * 10 + i) for i in range(4)]
    origin_tile: dict = {}   # (town, slot) -> row index of the Build
    origin_link: dict = {}   # line id -> row index of the Network
    first = len(rows)
    # VP an era scoring hands out INSIDE the current action, so a Sell that
    # happens to close the era is not credited with the whole scoring.
    scored_now = [0] * 4

    real = engine.score_era

    def scoring(s):
        # The bot's search calls score_era on cloned probe states. Only the
        # game's own state is a scoring that happened.
        if s is not st:
            return real(s)
        for link in s.data.links:
            owner = s.links.get(link.id)
            if owner is None:
                continue
            vp = sum(link_icons_at(s, e) for e in link.ends)
            r = origin_link.get(link.id)
            if r is not None:
                rows[r]["vp"] += vp
                rows[r]["scored_in"].append(s.era.value)
            scored_now[owner] += vp
        for town, slot, tile in s.all_tiles():
            if tile.flipped:
                vp = engine.spec_for(s, tile).vp
                r = origin_tile.get((town, slot))
                if r is not None:
                    rows[r]["vp"] += vp
                    rows[r]["scored_in"].append(s.era.value)
                scored_now[tile.owner] += vp
        return real(s)

    engine.score_era = scoring
    try:
        step = 0
        while not st.finished:
            acts = legal_actions(st)
            if not acts:
                break
            who = st.current.idx
            a = bots[who].choose(st, acts)
            row = {"game": seed, "seat": who, "step": step,
                   "era": st.era.value, "round": st.round,
                   "kind": type(a).__name__, "vp": 0, "scored_in": []}
            if isinstance(a, Build):
                row["industry"] = a.industry.value
                row["level"] = st.players[who].lowest_level(a.industry)
                row["overbuild"] = st.tiles[a.town][a.slot] is not None
                origin_tile[(a.town, a.slot)] = len(rows)
            elif isinstance(a, Network):
                row["lines"] = len(a.lines)
                for line in a.lines:
                    origin_link[line] = len(rows)
            rows.append(row)
            before, scored_now[who] = st.players[who].vp, 0
            apply_action(st, a)
            bonus = st.players[who].vp - before - scored_now[who]
            if bonus:
                row["vp"] += bonus
                row["bonus"] = bonus
            step += 1
    finally:
        engine.score_era = real
    for i, p in enumerate(st.players):
        finals.append({"game": seed, "seat": i, "vp": p.vp,
                       "rows": [r for r in range(first, len(rows))
                                if rows[r]["seat"] == i]})


def run(n: int, out: str) -> None:
    rows, finals, t0 = [], [], time.time()
    for g in range(n):
        play(7000 + g, rows, finals)
        print(f"PROGRESS done={g + 1} total={n} unit=games t={time.time() - t0:.1f}",
              flush=True)
    # rows reference each other by index; finals keep only the indices
    Path(out).write_text(json.dumps({"games": n, "rows": rows, "finals": finals}))
    print(f"total {n} games, {len(rows)} actions -> {out}", flush=True)


def report(path: str) -> None:
    d = json.loads(Path(path).read_text())
    rows, finals = d["rows"], d["finals"]
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0

    print(f"{d['games']} self-play games, {len(rows)} actions, "
          f"{len(finals)} seat-games, mean final VP {mean([f['vp'] for f in finals]):.1f}\n")

    # ---- exact: what each placing action realised -------------------------
    print("EXACT ATTRIBUTION: realised VP per action that placed something")
    print("(a Loan, Develop or Scout places nothing and is 0 by construction)\n")
    builds = [r for r in rows if r["kind"] == "Build"]
    links = [r for r in rows if r["kind"] == "Network"]
    sells = [r for r in rows if r["kind"] == "Sell"]
    total_vp = sum(f["vp"] for f in finals)
    print(f"  of {total_vp} VP scored in all: "
          f"{100 * sum(r['vp'] for r in builds) / total_vp:.0f}% from tiles, "
          f"{100 * sum(r['vp'] for r in links) / total_vp:.0f}% from links, "
          f"{100 * sum(r['vp'] for r in sells) / total_vp:.1f}% merchant bonuses\n")

    print("  BUILDS, by era built and industry:  n   mean VP   never scored")
    by = collections.defaultdict(list)
    for r in builds:
        by[(r["era"], r["industry"])].append(r)
    for (era, ind), rs in sorted(by.items(), key=lambda kv: (kv[0][0], -mean([r["vp"] for r in kv[1]]))):
        z = sum(1 for r in rs if r["vp"] == 0)
        print(f"    {era:5} {ind:13} {len(rs):>4}   {mean([r['vp'] for r in rs]):>5.2f}   "
              f"{100 * z / len(rs):>4.0f}%")

    print("\n  BUILDS in the Canal Era, by level (L1 is swept at the boundary):")
    by = collections.defaultdict(list)
    for r in builds:
        if r["era"] == "canal":
            by[r["level"]].append(r)
    for lv, rs in sorted(by.items()):
        twice = sum(1 for r in rs if len(r["scored_in"]) == 2)
        print(f"    L{lv}  n {len(rs):>4}  mean VP {mean([r['vp'] for r in rs]):>5.2f}  "
              f"scored in both eras {100 * twice / len(rs):>3.0f}%  "
              f"never {100 * sum(1 for r in rs if r['vp'] == 0) / len(rs):>3.0f}%")

    print("\n  LINKS, by era and round built:   n   mean VP per action")
    by = collections.defaultdict(list)
    for r in links:
        by[(r["era"], r["round"])].append(r)
    for (era, rd), rs in sorted(by.items()):
        print(f"    {era:5} r{rd:<2}  {len(rs):>4}   {mean([r['vp'] for r in rs]):>5.2f}"
              f"   ({mean([r['lines'] for r in rs]):.2f} lines each)")

    # ---- correlation: final VP against action counts ------------------------
    print("\nCORRELATION: a seat's final VP against how many of each action it took")
    print("(association across seat-games, not the effect of choosing differently)\n")
    kinds = ["Build", "Network", "Develop", "Sell", "Loan", "Scout", "Pass"]
    X, y = [], []
    for f in finals:
        c = collections.Counter(rows[r]["kind"] for r in f["rows"])
        X.append([c.get(k, 0) for k in kinds])
        y.append(f["vp"])
    ybar = mean(y)
    print(f"  {'action':8} {'mean n':>7} {'r':>6}   VP per extra one (simple)")
    for j, k in enumerate(kinds):
        xs = [row[j] for row in X]
        xbar = mean(xs)
        sxx = sum((x - xbar) ** 2 for x in xs)
        sxy = sum((x - xbar) * (v - ybar) for x, v in zip(xs, y))
        syy = sum((v - ybar) ** 2 for v in y)
        if sxx == 0:
            print(f"  {k:8} {xbar:>7.2f}      —   (never varies)")
            continue
        r = sxy / (sxx * syy) ** 0.5
        print(f"  {k:8} {xbar:>7.2f} {r:>6.2f}   {sxy / sxx:>+6.2f}")
    # multiple regression, so each coefficient is net of the others
    try:
        import numpy as np
        A = np.array([[1.0] + row for row in X])
        coef, *_ = np.linalg.lstsq(A, np.array(y, dtype=float), rcond=None)
        pred = A @ coef
        ss_res = float(((np.array(y) - pred) ** 2).sum())
        ss_tot = float(((np.array(y) - ybar) ** 2).sum())
        print(f"\n  jointly (least squares, R² {1 - ss_res / ss_tot:.2f}):")
        for j, k in enumerate(kinds):
            print(f"    {k:8} {coef[j + 1]:>+6.2f} VP per extra one, holding the others fixed")
    except ImportError:
        print("\n  (numpy not in this venv; joint fit skipped)")


if __name__ == "__main__":
    if sys.argv[1] == "--report":
        report(sys.argv[2])
    else:
        run(int(sys.argv[1]), sys.argv[2])
