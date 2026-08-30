"""Attribute every VP a seat scores back to the action that produced it.

Two ledgers:

  R (receipts)   -- who literally banks the points. A flipped tile's VP goes to
                    the Build that placed it; a link's VP to the Network that
                    placed it; a merchant bonus to the Sell that drank the beer.
                    Sums exactly to final VP (plus debt penalties).

  E (enablement) -- every point needs more than one action. A tile's VP needs a
                    Build and a flip; a link's icon from a tile needs a Network,
                    a Build and a flip; a merchant icon needs only the Network.
                    Each point is split equally among its necessary actions
                    (the Shapley value of a unanimity game). The flip may be an
                    OPPONENT's action, in which case the point is booked to
                    "free" rather than to any action of ours.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict

import brassbot.engine as E
from brassbot.actions import Build, Develop, Loan, Network, Pass, Scout, Sell
from brassbot.bots import make
from brassbot.gamedata import Era
from brassbot.state import new_game

REAL = None            # the one state whose scoring we record
ACTS = []              # list of action records, in play order
TILE_OF = {}           # id(tile) -> (tile, build_action_index)
FLIP_OF = {}           # id(tile) -> action index that flipped it
ROWS = []              # raw attribution rows


def _rec(idx, era, kind, amount, ledger):
    if idx is None:
        return
    ACTS[idx][ledger][era] += amount


_orig_score_era = E.score_era
_orig_merchant_bonus = E._merchant_bonus


def score_era(state):
    if state is REAL:
        era = state.era.value
        # --- links -------------------------------------------------------
        for link in state.data.links:
            owner = state.links.get(link.id)
            if owner is None:
                continue
            nidx = LINK_OF.get(link.id)
            for end in link.ends:
                if end in state.data.merchants:
                    icons = E.MERCHANT_LINK_ICONS.get(end, 0)
                    _rec(nidx, era, "link_merchant", icons, "R")
                    _rec(nidx, era, "link_merchant", icons, "E")
                    continue
                for tile in state.tiles.get(end, ()):
                    if tile is None or not tile.flipped:
                        continue
                    icons = E.spec_for(state, tile).link_vp
                    if not icons:
                        continue
                    _rec(nidx, era, "link_tile", icons, "R")
                    # three necessary actions: the network, the build, the flip
                    third = icons / 3.0
                    _rec(nidx, era, "link_tile", third, "E")
                    binfo = TILE_OF.get(id(tile))
                    bidx = binfo[1] if binfo else None
                    fidx = FLIP_OF.get(id(tile))
                    for who in (bidx, fidx):
                        if who is None or ACTS[who]["seat"] != owner:
                            FREE[owner][era] += third
                        else:
                            _rec(who, era, "link_tile", third, "E")
        # --- tiles -------------------------------------------------------
        for _town, _slot, tile in state.all_tiles():
            if not tile.flipped:
                continue
            vp = E.spec_for(state, tile).vp
            owner = tile.owner
            binfo = TILE_OF.get(id(tile))
            bidx = binfo[1] if binfo else None
            _rec(bidx, era, "tile", vp, "R")
            half = vp / 2.0
            fidx = FLIP_OF.get(id(tile))
            for who in (bidx, fidx):
                if who is None or ACTS[who]["seat"] != owner:
                    FREE[owner][era] += half
                else:
                    _rec(who, era, "tile", half, "E")
    return _orig_score_era(state)


def merchant_bonus(state, player, merchant_id):
    if state is REAL:
        m = state.data.merchants[merchant_id]
        if m.bonus_type == "vp" and CURRENT[0] is not None:
            era = state.era.value
            _rec(CURRENT[0], era, "merchant_bonus", m.bonus_amount, "R")
            _rec(CURRENT[0], era, "merchant_bonus", m.bonus_amount, "E")
    return _orig_merchant_bonus(state, player, merchant_id)


_orig_apply_build = E._apply_build
_orig_flip_tile = E.flip_tile


def apply_build(state, player, action):
    r = _orig_apply_build(state, player, action)
    if state is REAL and CURRENT[0] is not None:
        tile = state.tiles[action.town][action.slot]
        if tile is not None:
            TILE_OF[id(tile)] = (tile, CURRENT[0])
    return r


def flip_tile(state, tile):
    if state is REAL and CURRENT[0] is not None and not tile.flipped:
        KEEP.append(tile)
        FLIP_OF.setdefault(id(tile), CURRENT[0])
    return _orig_flip_tile(state, tile)


E.score_era = score_era
E._merchant_bonus = merchant_bonus
E._apply_build = apply_build
E.flip_tile = flip_tile
KEEP = []

CURRENT = [None]
LINK_OF = {}
FREE = None


def run(seat_bots, seed, n_players=4):
    global REAL, ACTS, TILE_OF, FLIP_OF, LINK_OF, FREE
    bots = [make(name, seed=seed * 1000 + s) for s, name in enumerate(seat_bots)]
    state = new_game(n_players, seed=seed)
    REAL = state
    ACTS = []
    TILE_OF = {}
    FLIP_OF = {}
    LINK_OF = {}
    FREE = [defaultdict(float) for _ in range(n_players)]
    KEEP.clear()

    while not state.finished:
        actions = E.legal_actions(state)
        seat = state.current.idx
        action = bots[seat].choose(state, actions)
        idx = len(ACTS)
        CURRENT[0] = idx
        rec = {
            "seq": idx, "seat": seat, "era": state.era.value,
            "round": state.round, "type": type(action).__name__,
            "R": defaultdict(float), "E": defaultdict(float),
            "n": 1,
        }
        if isinstance(action, Network):
            rec["n"] = len(action.lines)
            for line in action.lines:
                LINK_OF[line] = idx
        elif isinstance(action, Sell):
            rec["n"] = len(action.sales)
        elif isinstance(action, Develop):
            rec["n"] = len(action.industries)
        ACTS.append(rec)

        E.apply_action(state, action)

        CURRENT[0] = None

    finals = [p.vp for p in state.players]
    pens = [p.vp_penalties for p in state.players]
    return state, ACTS, FREE, finals, pens


def _key(rec, ledger):
    return sum(rec[ledger].values())


def main(games=200, seed0=0, n_players=4, bot="heuristic"):
    seats = [bot] * n_players
    # (type, era_taken) -> list of per-action VP
    perR = defaultdict(list)
    perE = defaultdict(list)
    counts = Counter()
    free_total = 0.0
    final_total = 0.0
    seat_rows = []
    check = []
    for g in range(games):
        state, acts, free, finals, pens = run(seats, seed0 + g, n_players)
        for rec in acts:
            k = (rec["type"], rec["era"])
            perR[k].append(_key(rec, "R"))
            perE[k].append(_key(rec, "E"))
            counts[k] += 1
        for s in range(n_players):
            own = defaultdict(float)
            cnt = Counter()
            for rec in acts:
                if rec["seat"] == s:
                    own[rec["type"]] += _key(rec, "R")
                    cnt[rec["type"]] += 1
            seat_rows.append({"seed": seed0 + g, "seat": s, "vp": finals[s],
                              "pen": pens[s], "counts": dict(cnt),
                              "R": dict(own),
                              "free": sum(free[s].values())})
            check.append(sum(own.values()) - pens[s] - finals[s])
        free_total += sum(sum(f.values()) for f in free)
        final_total += sum(finals)
    import json
    out = {"perR": {f"{k[0]}|{k[1]}": v for k, v in perR.items()},
           "perE": {f"{k[0]}|{k[1]}": v for k, v in perE.items()},
           "counts": {f"{k[0]}|{k[1]}": v for k, v in counts.items()},
           "seat_rows": seat_rows,
           "reconcile_max_abs": max(abs(c) for c in check),
           "free_total": free_total, "final_total": final_total,
           "games": games, "n_players": n_players}
    print(json.dumps(out))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=50)
    ap.add_argument("-s", type=int, default=0)
    ap.add_argument("-p", type=int, default=4)
    ap.add_argument("--bot", default="heuristic")
    a = ap.parse_args()
    main(a.n, a.s, a.p, a.bot)
