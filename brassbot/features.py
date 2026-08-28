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




SELLABLE = [i for i in Industry if i.is_sellable]

EXTRA_NAMES = (
    [f"track_cleared_{i.value}" for i in Industry]
    + [f"tiles_to_next_level_{i.value}" for i in Industry]
    + [f"next_vp_{i.value}" for i in Industry]
    + [f"vp_two_levels_up_{i.value}" for i in SELLABLE]
    + ["dominant_share", "industries_touched", "dominant_next_vp",
       "dominant_built", "sellable_spread"]
)


def extra_features(state, seat: int) -> list[float]:
    """Track position and plan progress.

    The cotton finding is the motivation: cotton's payoff sits at level 3, five
    tiles up the track, and nothing in the original 45 features says how far up a
    track you are or what waits at the top. `tiles_to_next_level` is literally
    the quantity the expert guide's argument turns on.
    """
    data, p = state.data, state.players[seat]
    cleared, to_next, next_vp, two_up = [], [], [], []
    for ind in Industry:
        mat = p.mat[ind]
        total = sum(mat) or 1
        low = p.lowest_level(ind)
        cleared.append(1.0 - sum(mat) / float(_track_total(data, p, ind) or total))
        to_next.append(float(mat[low - 1]) if low else 0.0)
        next_vp.append(float(data.tile(ind, low).vp) if low else 0.0)
    for ind in SELLABLE:
        low = p.lowest_level(ind)
        target = (low or 0) + 2
        spec = None
        if low:
            try:
                spec = data.tile(ind, target)
            except Exception:
                spec = None
        two_up.append(float(spec.vp) if spec else 0.0)

    built = {i: 0 for i in Industry}
    for _t, _s, tile in state.all_tiles():
        if tile.owner == seat:
            built[tile.industry] += 1
    sell_built = [built[i] for i in SELLABLE]
    total_sell = sum(sell_built)
    dominant = max(SELLABLE, key=lambda i: built[i])
    low_d = p.lowest_level(dominant)
    return cleared + to_next + next_vp + two_up + [
        (max(sell_built) / total_sell) if total_sell else 0.0,
        float(sum(1 for i in Industry if built[i])),
        float(data.tile(dominant, low_d).vp) if low_d else 0.0,
        float(built[dominant]),
        float(max(sell_built) - min(sell_built)),
    ]


_TOTALS: dict = {}


def _track_total(data, player, industry) -> int:
    """How many tiles the industry starts with, cached across calls."""
    if industry not in _TOTALS:
        _TOTALS[industry] = sum(player.mat[industry]) or 1
    return _TOTALS[industry]


ALL_NAMES: list[str] = NAMES + EXTRA_NAMES


def extract_extended(state, seat: int) -> list[float]:
    """The full feature vector: the evaluation's own quantities, plus track
    position. Trees reach 0.614 within-stage on NAMES alone and 0.617 on these,
    so the extras are close to free -- they are kept because they are what a
    linear model can use (0.569 -> 0.583) and what a human can read."""
    return extract(state, seat) + extra_features(state, seat)
