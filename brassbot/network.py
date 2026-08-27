"""Connectivity.

The rules use two different notions and conflating them is the classic Brass
implementation bug:

* **Connected** — "trace a route of link tiles (owned by *any* player)". This is
  what coal sourcing, opponents' beer, and sell legality use.
* **Your network** — locations holding *your* industry tiles, plus locations
  adjacent to *your* link tiles. This is what building from an industry card and
  placing a new link use.

A location with no link tiles touching it is connected only to itself, which is
why an isolated build site cannot reach market coal.
"""

from __future__ import annotations

from collections import deque

from .gamedata import Era
from .state import GameState


def link_adjacency(state: GameState) -> dict[str, set[str]]:
    """Adjacency over placed link tiles, regardless of owner.

    The Kidderminster-Worcester tile joins three locations, so every pair of
    locations on a link becomes adjacent.

    Cached against ``links.version``: move generation asks for this thousands of
    times per turn while the graph sits still.
    """
    cached = state._adj_cache
    if cached is not None and cached[0] == state.links.version:
        return cached[1]

    adj: dict[str, set[str]] = {}
    for link in state.data.links:
        if link.id not in state.links:
            continue
        for a in link.ends:
            for b in link.ends:
                if a != b:
                    adj.setdefault(a, set()).add(b)
    state._adj_cache = (state.links.version, adj)
    return adj


def distances_from(state: GameState, sources) -> dict[str, int]:
    """Distance in link tiles from any of ``sources`` to every reachable
    location. Sources are at distance 0.

    Memoised per source set, again against ``links.version`` -- coal planning
    asks the same question at every step of its recursion.
    """
    key = frozenset(sources)
    cached = state._dist_cache
    if cached is None or cached[0] != state.links.version:
        cached = (state.links.version, {})
        state._dist_cache = cached
    memo = cached[1]
    if key in memo:
        return memo[key]

    adj = link_adjacency(state)
    dist = {s: 0 for s in sources}
    queue = deque(dist)
    while queue:
        loc = queue.popleft()
        for nxt in adj.get(loc, ()):
            if nxt not in dist:
                dist[nxt] = dist[loc] + 1
                queue.append(nxt)
    memo[key] = dist
    return dist


def connected_locations(state: GameState, origin) -> set[str]:
    """Everything reachable from ``origin`` along placed links, including
    ``origin`` itself."""
    if isinstance(origin, str):
        origin = [origin]
    return set(distances_from(state, origin))


def player_network(state: GameState, player: int) -> set[str]:
    """The locations that count as this player's network."""
    network: set[str] = set()
    for town_id, _slot, tile in state.all_tiles():
        if tile.owner == player:
            network.add(town_id)
    for link in state.data.links:
        if state.links.get(link.id) == player:
            network.update(link.ends)
    return network


def is_connected_to_merchant(state: GameState, origin) -> bool:
    """Market coal requires a route to a merchant space. Merchant *spaces* count
    even when they hold no merchant tile (as at 2-3 players).

    Searched *from the merchants* rather than from the origin. The graph is
    undirected so the answer is identical, but the cache key is then the set of
    merchants -- constant for the whole game -- instead of a different origin per
    candidate action. Move generation asks this once per candidate line.
    """
    origins = [origin] if isinstance(origin, str) else origin
    reachable = distances_from(state, tuple(state.merchants))
    return any(o in reachable for o in origins)


def buildable_lines(state: GameState, player: int):
    """The lines this player may place a link tile on right now.

    A line must be undeveloped, must exist in the current era, and must touch
    the player's network -- unless the player has nothing on the board at all,
    in which case any line is legal.
    """
    network = player_network(state, player)
    unrestricted = not network
    for link in state.data.links:
        if link.id in state.links:
            continue
        if not (link.canal if state.era is Era.CANAL else link.rail):
            continue
        if unrestricted or any(end in network for end in link.ends):
            yield link
