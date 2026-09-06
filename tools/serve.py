"""A local web UI for playing against the bots.

    PYTHONPATH=. .venv/bin/python tools/serve.py --seed 1 --players 4 --opponent heuristic
    then open http://localhost:8765

Stdlib only, so it runs in the project venv with no extra dependencies. The game
lives in this process; there is one game at a time and no persistence, which is
all a single-player local tool needs.

Written because `tools/play.py` renders the board as text, and four separate
agents reported that a bare `show` does not carry enough to choose between two
listed moves -- it hides which card an action discards and where its coal comes
from. Seeing the board is also the fastest way to understand what the bot is
doing, which text never quite manages.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "ui"))

from layout import ALL as COORDS  # noqa: E402

import brassbot.engine as _engine  # noqa: E402
from brassbot.actions import Build, Develop, Network, Sell  # noqa: E402
from brassbot.bots import make  # noqa: E402
from brassbot.engine import (apply_action, legal_actions, score_era,  # noqa: E402
                              winners)
from brassbot.state import new_game  # noqa: E402
from tools.play import describe  # noqa: E402

UI = Path(__file__).resolve().parent / "ui" / "index.html"

GAME: dict = {}


def start(seed: int, players: int, opponent: str) -> None:
    GAME["state"] = new_game(players, seed=seed)
    GAME["bots"] = [make(opponent, seed=seed * 10 + i) for i in range(players)]
    GAME["seat"] = 0
    GAME["log"] = []
    advance()


def advance() -> None:
    """Let the bots play until it is the human's turn, or the game ends."""
    state, bots, seat = GAME["state"], GAME["bots"], GAME["seat"]
    while not state.finished and state.current.idx != seat:
        actor = state.current.idx
        actions = legal_actions(state)
        if not actions:
            break
        action = bots[actor].choose(state, actions)
        GAME["log"].append({"seat": actor, "text": describe(state, action)})
        apply_action(state, action)


def project_vp(state):
    """VP each seat would have if the era were scored right now.

    Banked VP is near zero for everyone through the Canal Era, so the raw
    number tells a player almost nothing about where they stand. Scoring
    mutates -- it removes links as they score -- so this runs on a clone, and
    never lets a display aid break the game.
    """
    probe = state.clone()
    try:
        scored = score_era(probe)
    except Exception:
        return [q.vp for q in state.players]
    return ([q.vp for q in probe.players] if scored is not None
            else [q.vp for q in state.players])


def mat_ladder(state, seat):
    """For each industry: the level that would be built next, and what is left.

    The mat decides what a Build actually places -- you always build the lowest
    level you still hold -- so a UI that hides it hides the single thing a
    player most needs to plan around.
    """
    p = state.players[seat]
    out = {}
    for industry, counts in p.mat.items():
        level = p.lowest_level(industry)
        spec = state.data.tile(industry, level) if level else None
        out[industry.value] = {
            "next": level,
            "remaining": sum(counts),
            "by_level": list(counts),
            "vp": spec.vp if spec else None,
            "cost": spec.cost if spec else None,
            "coal": spec.coal_cost if spec else None,
            "iron": spec.iron_cost if spec else None,
            "beer": spec.beer_to_sell if spec else None,
            "income": spec.income if spec else None,
            "link_vp": spec.link_vp if spec else None,
            # A canal-only tile is swept at the boundary whether it flipped or
            # not; the UI marks those so a player is not surprised by it.
            "canal_only": (spec is not None and spec.canal_era
                           and not spec.rail_era),
            "rail_only": (spec is not None and spec.rail_era
                          and not spec.canal_era),
        }
    return out


def snapshot() -> dict:
    state, seat = GAME["state"], GAME["seat"]
    tiles = []
    for town, slot, tile in state.all_tiles():
        tiles.append({
            "town": town, "slot": slot, "owner": tile.owner,
            "industry": tile.industry.value, "level": tile.level,
            "flipped": tile.flipped, "resources": tile.resources,
        })
    links = [{"id": lid, "owner": owner,
              "ends": list(state.data.link_by_id[lid].ends)}
             for lid, owner in state.links.items()]
    # Every line on the board, so unbuilt routes are still visible. Without
    # these the opening position renders as 27 disconnected dots.
    all_links = [{"id": l.id, "ends": list(l.ends),
                  "canal": l.canal, "rail": l.rail} for l in state.data.links]
    me = state.players[seat]
    proj = project_vp(state)
    moves = []
    if not state.finished and state.current.idx == seat:
        for i, action in enumerate(legal_actions(state)):
            # Which CARD an action spends, and enough structure for the UI to
            # group by it. A flat list of 87 strings is not a decision anyone
            # can make: in Brass you pick a card first and then see what it
            # lets you do, which is how the move list should read.
            m = {"index": i, "text": describe(state, action),
                 "kind": type(action).__name__, "card": getattr(action, "card", None)}
            if isinstance(action, Build):
                lvl = state.players[seat].lowest_level(action.industry)
                m.update(town=action.town, slot=action.slot,
                         industry=action.industry.value, level=lvl)
            elif isinstance(action, Network):
                m.update(lines=list(action.lines), double=len(action.lines) == 2)
            elif isinstance(action, Develop):
                # The levels these would REMOVE, so a player can see what a
                # develop actually costs them rather than only its name.
                seen, levels = {}, []
                for ind in action.industries:
                    n = seen.get(ind, 0)
                    base = state.players[seat].lowest_level(ind)
                    levels.append((base + n) if base else None)
                    seen[ind] = n + 1
                m.update(industries=[i2.value for i2 in action.industries],
                         levels=levels)
            elif isinstance(action, Sell):
                m.update(sales=[{"town": s.town, "merchant": s.merchant}
                                for s in action.sales],
                         own_beer=bool(getattr(action, "own_beer", False)),
                         tiles=len(action.sales))
            moves.append(m)
    return {
        "coords": COORDS,
        "towns": [{"id": t.id, "name": t.name,
                   "slots": [sorted(i.value for i in s) for s in t.slots],
                   "farm": t.farm_brewery}
                  for t in state.data.towns.values()],
        "merchants": {mid: [{"kind": s.kind, "beer": s.beer} for s in slots]
                      for mid, slots in state.merchants.items()},
        "all_merchants": list(state.data.merchants),
        "tiles": tiles,
        "links": links,
        "all_links": all_links,
        "era": state.era.value,
        "round": state.round,
        "rounds_this_era": state.rounds_this_era,
        "turn_order": list(state.turn_order),
        "current": state.current.idx,
        "seat": seat,
        "finished": state.finished,
        "winners": list(winners(state)) if state.finished else [],
        "coal_market": state.coal,
        "iron_market": state.iron,
        # Cubes left is not the number a player reasons with -- the PRICE is,
        # and a mine built into a short market sells its cubes on placement.
        "coal_price": state.data.coal.price_to_buy_one(state.coal),
        "iron_price": state.data.iron.price_to_buy_one(state.iron),
        "coal_cap": state.data.coal.capacity,
        "iron_cap": state.data.iron.capacity,
        "players": [{"idx": i, "vp": p.vp, "projected": proj[i],
                     "money": p.money, "income": p.income,
                     "spent": p.spent, "links_left": p.links_left,
                     "hand": len(p.hand),
                     "order": state.turn_order.index(i)
                              if i in state.turn_order else None}
                    for i, p in enumerate(state.players)],
        "hand": [{"kind": c.kind.value, "town": c.town,
                  "industries": sorted(i.value for i in (c.industries or ()))}
                 for c in me.hand],
        "mat": mat_ladder(state, seat),
        "moves": moves,
        "log": GAME["log"][-14:],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._send(json.dumps(snapshot()).encode(), "application/json")
        else:
            self._send(UI.read_bytes(), "text/html; charset=utf-8")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or "{}")
        if self.path.startswith("/api/move"):
            state = GAME["state"]
            actions = legal_actions(state)
            i = int(body.get("index", -1))
            if not state.finished and state.current.idx == GAME["seat"] \
                    and 0 <= i < len(actions):
                GAME["log"].append({"seat": GAME["seat"],
                                    "text": describe(state, actions[i])})
                apply_action(state, actions[i])
                advance()
        elif self.path.startswith("/api/new"):
            start(int(body.get("seed", 1)), int(body.get("players", 4)),
                  body.get("opponent", "heuristic"))
        self._send(json.dumps(snapshot()).encode(), "application/json")


def main() -> None:
    # Loan, Network, Develop, Sell and Pass all discard "any card from your
    # hand", but the engine generates each ONCE with the most expendable card
    # and offers alternatives only up to MAX_DISCARD_VARIANTS -- which defaults
    # to 1, because the bot's evaluation scores the variants bit-identically and
    # cannot tell them apart. A human very much can: this UI is built around
    # choosing which card to spend, and at 1 every card but one showed Build and
    # nothing else, which made legal moves look illegal.
    #
    # Set HERE and not at module scope. play.py learned that the hard way: at
    # import time it leaked into every analysis script that imported `describe`
    # and silently handed the BOT a three-times-larger move list.
    _engine.MAX_DISCARD_VARIANTS = 8      # a full hand

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--opponent", default="heuristic",
                    help="bot spec for the other seats, e.g. planner")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    start(args.seed, args.players, args.opponent)
    print(f"BrassBot UI on http://localhost:{args.port}  "
          f"({args.players}p, seed {args.seed}, opponents: {args.opponent})")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
