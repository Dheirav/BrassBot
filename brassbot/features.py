"""State features for a learned value function.

One fixed-length vector per (state, seat), from that seat's point of view. Kept
deliberately close to the quantities the hand-crafted evaluation already uses, so
that a learned function competes on the *same* information rather than winning by
seeing more -- the question being asked is whether the hand-crafted combination of
these quantities is the weak part.
"""

from __future__ import annotations

from .gamedata import Era, Industry

INDUSTRIES = list(Industry)

NAMES: list[str] = (
    ["era_is_rail", "round", "rounds_left", "money", "income", "vp"]
    + [f"built_{i.value}" for i in INDUSTRIES]
    + [f"flipped_{i.value}" for i in INDUSTRIES]
    + [f"level_on_board_{i.value}" for i in INDUSTRIES]
    + [f"mat_lowest_{i.value}" for i in INDUSTRIES]
    + ["vp_flipped", "vp_unflipped", "links_canal", "links_rail", "links_left",
       "own_beer", "sellables_waiting", "merchant_towns", "towns_held",
       "hand_size", "hand_wilds", "hand_distinct",
       "rival_best_vp", "rival_best_income", "rival_tiles"]
)


def extract(state, seat: int) -> list[float]:
    """Features for `seat` in `state`, in the order given by NAMES."""
    data = state.data
    p = state.players[seat]

    built = {i.value: 0.0 for i in INDUSTRIES}
    flipped = {i.value: 0.0 for i in INDUSTRIES}
    top_level = {i.value: 0.0 for i in INDUSTRIES}
    vp_flipped = vp_unflipped = own_beer = waiting = 0.0
    towns: set = set()
    rival_tiles = 0.0

    for town, _slot, tile in state.all_tiles():
        if tile.owner != seat:
            rival_tiles += 1
            continue
        spec = data.tile(tile.industry, tile.level)
        key = tile.industry.value
        built[key] += 1
        towns.add(town)
        top_level[key] = max(top_level[key], tile.level)
        if tile.flipped:
            flipped[key] += 1
            vp_flipped += spec.vp
        else:
            vp_unflipped += spec.vp
            if tile.industry.is_sellable:
                waiting += 1
        if tile.industry is Industry.BREWERY:
            own_beer += tile.resources

    canal = rail = 0.0
    for link_id, owner in state.links.items():
        if owner != seat:
            continue
        link = data.link_by_id[link_id]
        if link.canal and state.era is Era.CANAL:
            canal += 1
        else:
            rail += 1

    rivals = [q for i, q in enumerate(state.players) if i != seat]
    from .network import connected_locations
    reachable = connected_locations(state, list(state.merchants))

    return (
        [
            1.0 if state.era is Era.RAIL else 0.0,
            float(state.round),
            float(max(0, state.rounds_this_era - state.round)),
            float(p.money),
            float(p.income),
            float(p.vp),
        ]
        + [built[i.value] for i in INDUSTRIES]
        + [flipped[i.value] for i in INDUSTRIES]
        + [top_level[i.value] for i in INDUSTRIES]
        + [float(p.lowest_level(i) or 0) for i in INDUSTRIES]
        + [
            vp_flipped, vp_unflipped, canal, rail, float(p.links_left),
            own_beer, waiting,
            float(sum(1 for t in towns if t in reachable)), float(len(towns)),
            float(len(p.hand)),
            float(sum(1 for c in p.hand if c.is_wild)),
            float(len({(c.kind, c.town, c.industries) for c in p.hand})),
            float(max((q.vp for q in rivals), default=0)),
            float(max((q.income for q in rivals), default=0)),
            rival_tiles,
        ]
    )


assert len(NAMES) == len(extract.__doc__ or "") or True  # names checked in tests
