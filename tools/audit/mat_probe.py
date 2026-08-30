"""Instrumented self-play: record estimates and outcomes for audit."""
from __future__ import annotations

import pickle, sys
from concurrent.futures import ProcessPoolExecutor

import brassbot.engine as E
from brassbot.bots import make
from brassbot.bots.heuristic import HeuristicBot
from brassbot.gamedata import Era, Industry
from brassbot.state import new_game

INDS = list(Industry)


def run_game(args):
    seed, n_players, specs = args
    bots = [make(name, seed=seed * 1000 + i) for i, name in enumerate(specs)]
    state = new_game(n_players, seed=seed)
    data = state.data
    ev = HeuristicBot(seed=0)
    ev.w = ev.weights_for(n_players)

    # (town, slot) -> index into builds
    occupancy = {}
    builds = []          # dicts
    mats = []            # mat snapshots
    values = []          # per-round player/rival values
    rail_start = None
    link_zero_turns = [0] * n_players
    turns = [0] * n_players

    def snapshot_board():
        for town, slot, tile in state.all_tiles():
            key = (town, slot)
            idx = occupancy.get(key)
            sig = (tile.owner, tile.industry, tile.level)
            if idx is None or (builds[idx]["seat"], builds[idx]["industry"],
                               builds[idx]["level"]) != sig:
                builds.append(dict(seat=tile.owner, industry=tile.industry.value,
                                   level=tile.level, t=t[0], era=state.era.value,
                                   round=state.round, scored=0, flips=0,
                                   vp=data.tile(tile.industry, tile.level).vp))
                occupancy[key] = len(builds) - 1

    def snapshot_mats():
        for seat, p in enumerate(state.players):
            for ind in INDS:
                mat = p.mat[ind]
                rem = [(i + 1, data.tile(ind, i + 1).vp)
                       for i, c in enumerate(mat) for _ in range(c)]
                if not rem:
                    continue
                nxt_level, nxt_vp = rem[0]
                mats.append(dict(seat=seat, t=t[0], era=state.era.value,
                                 round=state.round, industry=ind.value,
                                 next_level=nxt_level, next_vp=nxt_vp,
                                 rem_vps=[v for _l, v in rem],
                                 rem_levels=[l for l, _v in rem]))

    def snapshot_values():
        ctx = ev._sale_context(state)
        owned, _ = ev.scan_board(state)
        vals = [ev.player_value(state, i, ctx, owned[i]) for i in range(n_players)]
        for seat in range(n_players):
            others = [v for i, v in enumerate(vals) if i != seat]
            values.append(dict(seat=seat, t=t[0], era=state.era.value,
                               round=state.round, mine=vals[seat],
                               best_rival=max(others),
                               mean_rival=sum(others) / len(others)))

    # wrap score_era to attribute banked VP to build events
    orig_score = E.score_era

    def traced_score(st):
        if st is not state:      # a bot's lookahead clone, not the real game
            return orig_score(st)
        for town, slot, tile in st.all_tiles():
            if tile.flipped:
                idx = occupancy.get((town, slot))
                if idx is not None:
                    builds[idx]["scored"] += data.tile(tile.industry, tile.level).vp
                    builds[idx]["flips"] += 1
        return orig_score(st)

    E.score_era = traced_score
    t = [0]
    try:
        prev = (state.era, state.round)
        snapshot_mats(); snapshot_values()
        while not state.finished:
            actions = E.legal_actions(state)
            seat = state.current.idx
            turns[seat] += 1
            if state.players[seat].links_left == 0:
                link_zero_turns[seat] += 1
            action = bots[seat].choose(state, actions)
            E.apply_action(state, action)
            t[0] += 1
            snapshot_board()
            cur = (state.era, state.round)
            if cur != prev and not state.finished:
                if prev[0] is Era.CANAL and cur[0] is Era.RAIL:
                    rail_start = dict(
                        t=t[0],
                        vp=[p.vp for p in state.players],
                        blocked=[[i.value for i in INDS
                                  if (lv := p.lowest_level(i)) is not None
                                  and not data.tile(i, lv).rail_era]
                                 for p in state.players],
                        mat_next=[{i.value: p.lowest_level(i) for i in INDS}
                                  for p in state.players],
                        links_left=[p.links_left for p in state.players],
                        money=[p.money for p in state.players],
                        income=[p.income for p in state.players],
                    )
                snapshot_mats(); snapshot_values()
                prev = cur
    finally:
        E.score_era = orig_score

    scores = [p.vp for p in state.players]
    order = sorted(range(n_players), key=lambda s: -scores[s])
    rank = [0] * n_players
    for r, s in enumerate(order):
        rank[s] = r
    return dict(seed=seed, n_players=n_players, scores=scores, rank=rank,
                builds=builds, mats=mats, values=values, rail_start=rail_start,
                links_left=[p.links_left for p in state.players],
                turns=turns, link_zero_turns=link_zero_turns,
                income=[p.income for p in state.players],
                era_scores=[dict(link_vp=list(r.link_vp), industry_vp=list(r.industry_vp))
                            for r in state.era_scores])


def main():
    n = int(sys.argv[1]); seed0 = int(sys.argv[2]); out = sys.argv[3]
    npl = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    spec = sys.argv[5] if len(sys.argv) > 5 else "heuristic"
    jobs = [(seed0 + i, npl, [spec] * npl) for i in range(n)]
    with ProcessPoolExecutor(max_workers=8) as pool:
        res = list(pool.map(run_game, jobs, chunksize=2))
    with open(out, "wb") as f:
        pickle.dump(res, f)
    print("games", len(res), "mean", sum(sum(r["scores"]) / npl for r in res) / len(res))


if __name__ == "__main__":
    main()
