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

from brassbot.bots import make  # noqa: E402
from brassbot.engine import apply_action, legal_actions, winners  # noqa: E402
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
        GAME["log"].append(f"P{actor}: {describe(state, action)}")
        apply_action(state, action)


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
    moves = []
    if not state.finished and state.current.idx == seat:
        for i, action in enumerate(legal_actions(state)):
            moves.append({"index": i, "text": describe(state, action),
                          "kind": type(action).__name__})
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
        "players": [{"idx": i, "vp": p.vp, "money": p.money, "income": p.income,
                     "spent": p.spent, "links_left": p.links_left,
                     "hand": len(p.hand)} for i, p in enumerate(state.players)],
        "hand": [{"kind": c.kind.value, "town": c.town,
                  "industries": sorted(i.value for i in (c.industries or ()))}
                 for c in me.hand],
        "mat": {ind.value: list(counts) for ind, counts in me.mat.items()},
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
                GAME["log"].append(f"You: {describe(state, actions[i])}")
                apply_action(state, actions[i])
                advance()
        elif self.path.startswith("/api/new"):
            start(int(body.get("seed", 1)), int(body.get("players", 4)),
                  body.get("opponent", "heuristic"))
        self._send(json.dumps(snapshot()).encode(), "application/json")


def main() -> None:
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
