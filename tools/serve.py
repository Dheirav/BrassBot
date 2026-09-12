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
import errno
import importlib
import json
import os
import random
import sys
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "ui"))

import layout as _layout  # noqa: E402

import brassbot.engine as _engine  # noqa: E402
from brassbot.actions import (Build, Develop, Loan, Network,  # noqa: E402
                              Pass, Scout, Sell)
from brassbot.bots import make  # noqa: E402
from brassbot.engine import (apply_action, legal_actions, link_icons_at,  # noqa: E402
                              score_era, winners)
from brassbot.gamedata import (Era, Industry,  # noqa: E402
                                highest_space_of_level)
from brassbot.network import is_connected_to_merchant  # noqa: E402
from brassbot.resources import plan_cost  # noqa: E402
from brassbot.state import new_game  # noqa: E402
from tools.play import describe  # noqa: E402

UI = Path(__file__).resolve().parent / "ui" / "index.html"
# Overridable so the test suite does not write into the analysis corpus. A
# finished game now exports itself, and the suite plays several to completion,
# so without this every run dropped a handful of junk games into logs/ beside
# the real ones -- which the playstyle scripts read.
LOGS = Path(os.environ.get("BRASSBOT_LOGS")
            or Path(__file__).resolve().parent.parent / "logs")

# The pasted Boomforge logs name industries the way the board does, not the way
# our data keys them, and every analysis script in tools/ reads that wording.
LOGNAME = {"coal_mine": "coal", "iron_works": "iron", "cotton_mill": "cotton",
           "brewery": "brewery", "manufacturer": "manufacturer",
           "pottery": "pottery"}

# One game per room, so several people can play at once without sharing a
# board. A room is created the first time it is asked for and the plain URL
# lands in "main". Each carries its own lock: ThreadingHTTPServer means two
# requests for the same room really can arrive together.
GAMES: dict = {}
GAMES_LOCK = threading.Lock()
# The running server, so /api/shutdown can stop the loop it is being served
# from. There is exactly one per process, which is why a module global is
# honest here rather than lazy.
SERVER = None
STOPPING = threading.Event()
DEFAULTS: dict = {"players": 4, "opponent": "heuristic", "name": "You"}


def room_of(path: str, body: dict | None = None) -> str:
    """The room named by ?room= or the request body, else "main".

    Restricted to a short alphanumeric alphabet: the name reaches a filename
    through the export path, so it must never carry a separator.
    """
    raw = str(body.get("room")) if body and body.get("room") else \
        (parse_qs(urlparse(path).query).get("room") or ["main"])[0]
    return "".join(c for c in raw.lower() if c.isalnum())[:12] or "main"


def game_for(room: str) -> dict:
    with GAMES_LOCK:
        g = GAMES.get(room)
        if g is None:
            g = {"lock": threading.Lock(), "room": room, "name": DEFAULTS["name"]}
            GAMES[room] = g
            start(g, random.randrange(1, 10 ** 6),
                  DEFAULTS["players"], DEFAULTS["opponent"])
        return g


def town_name(state, tid: str) -> str:
    t = state.data.towns.get(tid)
    return t.name if t else tid.replace("_", " ").title()


def card_name(state, action) -> str:
    c = getattr(action, "card", None)
    if c is None or c >= len(state.current.hand):
        return ""
    card = state.current.hand[c]
    if card.town:
        return town_name(state, card.town)
    if card.industries:
        return " / ".join(LOGNAME.get(i.value, i.value) for i in card.industries)
    return card.kind.value


def log_line(state, action, who: str) -> str:
    """One action in the wording the pasted Boomforge logs use.

    `describe` is the debug view -- levels, net cost, income spaces -- which is
    right for playing and wrong for a log that tools/ parsers read. Exported
    games have to look like the real ones or they cannot be pooled with them.
    """
    card = card_name(state, action)
    tail = f" · card: {card}" if card else ""
    p = state.current
    if isinstance(action, Build):
        lvl = p.lowest_level(action.industry)
        ind = LOGNAME.get(action.industry.value, action.industry.value)
        return f"{who} built {ind} {lvl} at {town_name(state, action.town)}{tail}"
    if isinstance(action, Network):
        joined = " and ".join(
            "–".join(town_name(state, e) for e in state.data.link_by_id[l].ends)
            for l in action.lines)
        return f"{who} linked {joined}{tail}"
    if isinstance(action, Sell):
        parts = []
        for sale in action.sales:
            parts.append(f"{town_name(state, sale.town)}"
                         f" (beer: merchant at {town_name(state, sale.merchant)})"
                         if sale.merchant else town_name(state, sale.town))
        return f"{who} sold at {', '.join(parts)}{tail}"
    if isinstance(action, Develop):
        inds = " + ".join(LOGNAME.get(i.value, i.value) for i in action.industries)
        return f"{who} developed {inds}{tail}"
    if isinstance(action, Loan):
        return f"{who} took a £30 loan (income −3 levels){tail}"
    if isinstance(action, Scout):
        return f"{who} scouted for wild cards{tail}"
    if isinstance(action, Pass):
        return f"{who} passed{tail}"
    return f"{who} {type(action).__name__.lower()}{tail}"


def move_label(state, action) -> str:
    """The move in the log's own words, with no actor.

    The list used to show `describe()`, which is the debug view -- net cost,
    income spaces, the card id -- and reads nothing like the game. The prose
    renderer already exists for the exported log; this borrows it.
    """
    return log_line(state, action, "").strip()


def who(g: dict, seat: int) -> str:
    return g.get("name", "You") if seat == g.get("seat", 0) else f"Bot {seat}"


def bump(g: dict) -> None:
    g["version"] = g.get("version", 0) + 1


def record(g: dict, action, index: int | None = None) -> None:
    """Log an action, then any era scoring it triggered.

    `index` is the action's position in the legal-move list it was chosen from.
    Stored, because the engine is deterministic: the seed plus every chosen
    index replays the whole game exactly, hands and market included, which the
    prose log can never do. It also survives a retune, since the indices are
    what was actually played rather than what the bot would pick today.
    """
    state = g["state"]
    if index is not None:
        g.setdefault("replay", []).append(index)
    tally(g, action)
    g["log"].append({"seat": state.current.idx,
                        "text": describe(state, action),
                        "pretty": move_label(state, action),
                        "round": state.round, "era": state.era.value})
    g["lines"].append(log_line(state, action, who(g, state.current.idx)))
    before = len(state.era_scores)
    apply_action(state, action)
    settle_spend(g)
    bump(g)
    for rec in state.era_scores[before:]:
        parts = []
        for i, pl in enumerate(state.players):
            gained = rec.link_vp[i] + rec.industry_vp[i]
            parts.append(f"{who(g, i)} +{gained} VP ({pl.vp})")
        g["lines"].append(f"{rec.era.value} era scored: " + ", ".join(parts))


def tally(g: dict, action) -> None:
    """Count what each seat did, by era, for the end-of-game breakdown.

    The era scoring records what each player GOT; this records what they DID
    to get it, which is the half a person learns from. Kept per era because
    the two halves of a game are different games: a Canal Era of loans and
    breweries and a Rail Era of double links look identical summed.
    """
    state = g["state"]
    seat, era = state.current.idx, state.era.value
    st = g.setdefault("stats", {})
    me = st.setdefault(seat, {"actions": {}, "built": {}, "developed": {},
                              "loans": 0, "spent": 0, "sold": 0,
                              "links": {"canal": 0, "rail": 0}})
    kind = type(action).__name__
    per = me["actions"].setdefault(era, {})
    per[kind] = per.get(kind, 0) + 1
    if isinstance(action, Build):
        k = action.industry.value
        me["built"][k] = me["built"].get(k, 0) + 1
    elif isinstance(action, Network):
        me["links"][era] += len(action.lines)
    elif isinstance(action, Develop):
        for ind in action.industries:
            me["developed"][ind.value] = me["developed"].get(ind.value, 0) + 1
    elif isinstance(action, Loan):
        me["loans"] += 1
    elif isinstance(action, Sell):
        me["sold"] += len(action.sales)
    me["_money_before"] = state.players[seat].money


def settle_spend(g: dict) -> None:
    """After an action is applied: what it cost, net of anything it paid."""
    st = g.get("stats", {})
    for seat, me in st.items():
        if "_money_before" in me:
            delta = me.pop("_money_before") - g["state"].players[seat].money
            if delta > 0:
                me["spent"] += delta


def summary(g: dict) -> dict:
    """The breakdown a finished game is worth reading.

    Per seat: what each era scored and from what, what was built and how much
    of it ever flipped, how the actions split, loans, spend, and where the
    money and income ended. `era_scores` is the engine's own record of the
    scoring; nothing here is recomputed from the board.
    """
    state = g["state"]
    n = state.n_players
    st = g.get("stats", {})
    order = sorted(range(n), key=lambda i: (-state.players[i].vp,
                                            -state.players[i].income,
                                            -state.players[i].money))
    eras = [{"era": r.era.value,
             "link_vp": list(r.link_vp), "industry_vp": list(r.industry_vp),
             "links": list(r.links_scored), "flipped": list(r.tiles_flipped),
             "stranded": list(r.tiles_stranded)}
            for r in state.era_scores]
    seats = []
    for i, p in enumerate(state.players):
        me = st.get(i, {})
        # The only VP that arrive outside an era scoring are merchant sell
        # bonuses, Shrewsbury's 4 and Nottingham's 3, so the residual IS that
        # figure. Exact by construction, and the first test run of this
        # function found the breakdown 3 short before it existed.
        scored = sum(e["link_vp"][i] + e["industry_vp"][i] for e in eras)
        seats.append({
            "bonus_vp": p.vp - scored,
            "idx": i, "name": who(g, i), "rank": order.index(i) + 1,
            "vp": p.vp, "income": p.income, "money": p.money,
            "eras": [{"era": e["era"], "link_vp": e["link_vp"][i],
                      "industry_vp": e["industry_vp"][i],
                      "links": e["links"][i], "flipped": e["flipped"][i],
                      "stranded": e["stranded"][i]} for e in eras],
            "actions": me.get("actions", {}),
            "built": me.get("built", {}),
            "developed": me.get("developed", {}),
            "links_built": me.get("links", {"canal": 0, "rail": 0}),
            "loans": me.get("loans", 0), "spent": me.get("spent", 0),
            "sold": me.get("sold", 0),
        })
    return {"finished": state.finished, "ended": bool(g.get("ended")),
            "winners": [who(g, i) for i in winners(state)] if state.finished else [],
            "seats": seats}


def export_log(g: dict) -> str:
    """Write the game so far in the pasted-log format, newest line first.

    Same shape as logs/*.log so tools that read those -- the playstyle and
    canal-bank analyses -- can pool UI games with the Boomforge ones.
    """
    state = g["state"]
    top = ([f"game over, winner: {', '.join(who(g, i) for i in winners(state))}"]
           if state.finished else
           [f"game in progress · {state.era.value} era round {state.round}"])
    body = list(reversed(g["lines"]))
    LOGS.mkdir(exist_ok=True)
    from datetime import datetime
    tag = "" if g.get("room", "main") == "main" else f"-{g['room']}"
    # Named once per game and then reused, so replaying to the end after an undo
    # rewrites that game's log rather than leaving a second copy of it.
    path = Path(g["exported"]) if g.get("exported") else \
        LOGS / (datetime.now().strftime("%Y%m%d-%H%M%S")
                + f"{tag}-ui-{state.n_players}p.log")
    path.write_text("\n".join(top + body) + "\n")
    # Everything a review needs to reconstruct the game exactly. The prose log
    # is for reading and for pooling with the pasted ones; this is for analysis.
    path.with_suffix(".replay.json").write_text(json.dumps({
        "seed": g.get("seed"), "players": state.n_players,
        "opponent": g.get("opponent", "heuristic"),
        "seat": g.get("seat", 0), "name": g.get("name", "You"),
        "finished": state.finished,
        # An index means nothing without the list it indexes. The server widens
        # the engine's move list so a person can choose any card, and a replay
        # run against the engine's defaults gets a shorter list and reads the
        # wrong action from the second move on. Recorded so the reader need not
        # know how this server happened to be configured.
        "engine": {"MAX_DISCARD_VARIANTS": _engine.MAX_DISCARD_VARIANTS,
                   "SCOUT_POOL": _engine.SCOUT_POOL,
                   "MAX_SCOUT_VARIANTS": _engine.MAX_SCOUT_VARIANTS},
        "actions": list(g.get("replay", [])),
    }, indent=1) + "\n")
    return str(path)


def start(g: dict, seed: int, players: int, opponent: str) -> None:
    # Remembered so Restart can deal a fresh board with the same setup rather
    # than asking for it again.
    g["players"], g["opponent"], g["seed"] = players, opponent, seed
    g["ended"] = False
    g["state"] = new_game(players, seed=seed)
    g["bots"] = [make(opponent, seed=seed * 10 + i) for i in range(players)]
    g["seat"] = 0
    g["log"] = []
    g["lines"] = []
    # One snapshot per human action, so Undo rewinds past the bots' replies to
    # the position you actually chose from -- rewinding only your own move
    # would leave you staring at a board they had already answered.
    g["undo"] = []
    g["replay"] = []
    g["stats"] = {}
    g["exported"] = None
    # A move is sent as an INDEX into the legal-action list, which the server
    # regenerates per request. Two tabs on one game, or a click racing an undo,
    # would apply a still-in-range index to a different list and play an action
    # nobody chose. The version pins an index to the position it was drawn for.
    g["version"] = 0
    advance(g)


def advance(g: dict) -> None:
    """Let the bots play until it is the human's turn, or the game ends."""
    state, bots, seat = g["state"], g["bots"], g["seat"]
    while not state.finished and state.current.idx != seat:
        actor = state.current.idx
        actions = legal_actions(state)
        if not actions:
            break
        chosen = bots[actor].choose(state, actions)
        record(g, chosen, actions.index(chosen))
    autosave(g)


def autosave(g: dict) -> str | None:
    """Write a finished game out without being asked.

    A game that reaches its own ending is worth keeping every time, and the
    moment you are least likely to click Export is the moment the winner
    appears. Only on a real ending: a game abandoned halfway is not a log
    anybody wants on disk, and that one stays a deliberate press of the button.
    """
    if not (g["state"].finished or g.get("ended")):
        return None
    first = g.get("exported") is None
    g["exported"] = export_log(g)
    # Said once, in the terminal the server runs in, because whoever wants to
    # know a file appeared is usually not the person looking at the browser.
    if first:
        print(f"saved {g['exported']}", flush=True)
    return g["exported"]


def project_vp(state):
    # After the Rail era `finished` is set but the tiles are still on the board,
    # so projecting again would score every flipped tile a second time -- and
    # the headline number would disagree with the game-over panel beside it.
    if state.finished:
        return [p.vp for p in state.players]

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
    # Resources bought from the market get dearer per cube, so pricing them all
    # at the first cube's price is a LOWER bound -- and connected sources of our
    # own are free, which pushes the other way. It is a hint, not a quote, and
    # the UI says so.
    coal_price = state.data.coal.price_to_buy_one(state.coal)
    iron_price = state.data.iron.price_to_buy_one(state.iron)
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
            # Cubes the tile places when built. A coal mine that puts 2 on the
            # board into a short market sells them on placement and pays you.
            "produces": (spec.beer_produced(state.era) if spec and spec.beer_to_sell is None
                         and spec.industry is Industry.BREWERY
                         else (spec.resource_produced if spec else 0)),
            # A canal-only tile is swept at the boundary whether it flipped or
            # not; the UI marks those so a player is not surprised by it.
            "canal_only": (spec is not None and spec.canal_era
                           and not spec.rail_era),
            "rail_only": (spec is not None and spec.rail_era
                          and not spec.canal_era),
            "cash": (None if spec is None else
                     spec.cost + spec.coal_cost * coal_price
                     + spec.iron_cost * iron_price),
            # The whole remaining pile, not just the tile on top of it. You
            # cannot plan a Develop without it: the question a Develop answers
            # is "what is underneath", and every level's numbers differ.
            "stack": [
                {"level": lv, "left": n, "cost": t.cost, "vp": t.vp,
                 "coal": t.coal_cost, "iron": t.iron_cost,
                 "beer": t.beer_to_sell, "income": t.income,
                 "link_vp": t.link_vp,
                 "canal_only": t.canal_era and not t.rail_era,
                 "rail_only": t.rail_era and not t.canal_era}
                for lv, n, t in ((i + 1, c, state.data.tile(industry, i + 1))
                                 for i, c in enumerate(counts))
            ],
        }
    for entry in out.values():
        entry["short"] = (None if entry["cash"] is None
                          else max(0, entry["cash"] - p.money))
    return out


def _slots(market, held):
    """The ladder as it physically sits: one entry per space, cheapest first,
    saying what that space costs and whether a cube is in it."""
    empty = market.capacity - held
    return [{"price": pr, "cube": i >= empty}
            for i, pr in enumerate(market.prices)]


def _draws(state, plan):
    """Serialise a resource plan with its provenance.

    Connected coal is drawn from ANY player's mine, so naming the owner
    matters -- taking an opponent's cube flips their tile for them.
    """
    out = []
    for d in plan:
        owner = None
        if d.kind == "tile" and d.town is not None:
            t = state.tiles[d.town][d.slot]
            owner = t.owner if t else None
        out.append({"kind": d.kind, "town": d.town, "owner": owner,
                    "resource": d.resource, "merchant": d.merchant,
                    "cost": d.cost})
    return out


def _ladder(market, held, n: int = 6):
    """What the next `n` cubes cost, one at a time.

    A single "next price" understates a multi-cube buy -- the market empties as
    you take from it, so three coal for a double rail is not three times the
    first price, and the mat's cash estimate says so.
    """
    out, h = [], held
    for _ in range(n):
        out.append(market.price_to_buy_one(h))
        h = max(0, h - 1)
    return out


def _with_buildable(state, seat, mat, moves):
    """Mark the industries a Build is legal for, and say why when it is not.

    "Blocked" collapses four different situations that call for four different
    turns: no tile left, no card that names it, not enough cash, or nothing
    reachable to put it on. The legal move list settles WHETHER; these settle
    WHICH, so the player is told the thing they would have to change.
    """
    live = {m["industry"] for m in moves if m["kind"] == "Build"}
    hand = state.players[seat].hand
    for name, entry in mat.items():
        entry["buildable"] = name in live
        if entry["buildable"]:
            entry["reason"] = None
            continue
        if entry["next"] is None:
            entry["reason"] = "none left"
            continue
        # Era first: a canal-only tile in the Rail Era cannot be placed at any
        # price or from any position, so naming cash or reach as the blocker
        # sends the player to fix something that is not the problem.
        if entry["canal_only"] and state.era is not Era.CANAL:
            entry["reason"] = "canal-only — gone this era"
            continue
        if entry["rail_only"] and state.era is not Era.RAIL:
            entry["reason"] = "rail-only — not until rail"
            continue
        industry = Industry(name)
        # Could any card in hand name this industry at a town with a free slot?
        # An industry card says the industry outright; a location card allows
        # whatever that town's empty slots accept.
        playable = False
        for card in hand:
            if card.industries and industry in card.industries:
                playable = True
                break
            if card.is_wild:
                playable = True
                break
            if card.town:
                town = state.data.towns.get(card.town)
                slots = state.tiles.get(card.town, ())
                if town and any(tile is None and industry in spec
                                for tile, spec in zip(slots, town.slots)):
                    playable = True
                    break
        if not playable:
            entry["reason"] = "no card for it"
        elif entry["short"]:
            entry["reason"] = f"short £{entry['short']}"
        else:
            entry["reason"] = "no slot in reach"
    return mat


_LAYOUT_MTIME = None


def coords() -> dict:
    """The map coordinates, re-read when the file changes.

    index.html is re-read from disk on every request precisely so the UI can be
    edited while a game is running. The coordinates were the exception: imported
    once at startup, so moving a town did nothing at all until someone restarted
    the server -- which looks exactly like the edit never landing. It cost a
    round of "the markets still overlap the frame" on a map that had already
    been fixed on disk.
    """
    global _LAYOUT_MTIME
    try:
        stamp = Path(_layout.__file__).stat().st_mtime
    except OSError:
        return _layout.ALL
    if stamp != _LAYOUT_MTIME:
        if _LAYOUT_MTIME is None:
            _LAYOUT_MTIME = stamp          # imported at startup, already fresh
        else:
            try:
                importlib.reload(_layout)
            except Exception as exc:
                # A save in progress is a truncated file, and stamping it would
                # mean never looking again. Leave the stamp alone so the next
                # request retries, and keep serving the coordinates we have.
                print(f"layout.py not reloaded: {exc}", flush=True)
            else:
                _LAYOUT_MTIME = stamp
    return _layout.ALL


def snapshot(g: dict) -> dict:
    state, seat = g["state"], g["seat"]
    tiles = []
    for town, slot, tile in state.all_tiles():
        tiles.append({
            "town": town, "slot": slot, "owner": tile.owner,
            "industry": tile.industry.value, "level": tile.level,
            "flipped": tile.flipped, "resources": tile.resources,
            "vp": state.data.tile(tile.industry, tile.level).vp,
        })
    links = [{"id": lid, "owner": owner,
              "ends": list(state.data.link_by_id[lid].ends)}
             for lid, owner in state.links.items()]
    # Every line on the board, so unbuilt routes are still visible. Without
    # these the opening position renders as 27 disconnected dots.
    # What each line would score RIGHT NOW. Link VP is the icons showing at
    # both ends and counts tiles regardless of owner, so this number rises when
    # anyone flips a tile beside it -- the single least visible thing in the
    # game, and the reason a link bought early scores against a bare board.
    all_links = [{"id": l.id, "ends": list(l.ends),
                  "canal": l.canal, "rail": l.rail,
                  "vp": sum(link_icons_at(state, e) for e in l.ends)}
                 for l in state.data.links]
    me = state.players[seat]
    proj = project_vp(state)
    moves = []
    if not state.finished and not g.get("ended") \
            and state.current.idx == seat:
        for i, action in enumerate(legal_actions(state)):
            # Which CARD an action spends, and enough structure for the UI to
            # group by it. A flat list of 87 strings is not a decision anyone
            # can make: in Brass you pick a card first and then see what it
            # lets you do, which is how the move list should read.
            m = {"index": i, "text": describe(state, action),
                 "kind": type(action).__name__, "card": getattr(action, "card", None),
                 "pretty": move_label(state, action)}
            if isinstance(action, Build):
                lvl = state.players[seat].lowest_level(action.industry)
                spec = state.data.tile(action.industry, lvl)
                # Every cube already knows where it came from -- resources.Draw
                # carries kind/town/cost -- so provenance is a serialisation
                # job, not a calculation. "1 iron (market GBP5)" is a different
                # decision from "1 iron (Coalbrookdale, yours)".
                # A mine or works dumps its cubes into the market on the build
                # and is PAID for them, so the printed cost overstates what a
                # build takes out of your pocket -- sometimes by all of it.
                revenue = 0
                if (action.industry is Industry.COAL_MINE
                        and is_connected_to_merchant(state, action.town)):
                    revenue, _ = state.data.coal.revenue_from_selling(
                        state.coal, spec.resource_produced)
                elif action.industry is Industry.IRON_WORKS:
                    revenue, _ = state.data.iron.revenue_from_selling(
                        state.iron, spec.resource_produced)
                outlay = spec.cost + plan_cost(action.coal) + plan_cost(action.iron)
                m.update(town=action.town, slot=action.slot,
                         industry=action.industry.value, level=lvl,
                         price=spec.cost, coal=_draws(state, action.coal),
                         iron=_draws(state, action.iron), outlay=outlay,
                         revenue=revenue, net=outlay - revenue,
                         overbuild=state.tiles[action.town][action.slot] is not None)
            elif isinstance(action, Network):
                n = len(action.lines)
                # A double rail is GBP15 + coal each + a beer that must come
                # from a BREWERY. Picking it blind and reading the cost in the
                # log afterwards is the wrong order.
                price = state.data.constants[
                    "rail_double_link_cost" if n == 2 else
                    ("canal_link_cost" if state.era is Era.CANAL
                     else "rail_link_cost")]
                m.update(lines=list(action.lines), double=n == 2,
                         price=price,
                         coal=_draws(state, action.coal),
                         beer=_draws(state, action.beer),
                         outlay=price + plan_cost(action.coal)
                                + plan_cost(action.beer),
                         net=price + plan_cost(action.coal)
                             + plan_cost(action.beer), revenue=0)
            elif isinstance(action, Develop):
                m.update(price=0, iron=_draws(state, action.iron),
                         outlay=plan_cost(action.iron),
                         net=plan_cost(action.iron), revenue=0)
                # The levels these would REMOVE, so a player can see what a
                # develop actually costs them rather than only its name.
                # Removing two of one industry does NOT step up a level each
                # time: brewery holds TWO level-1 tiles, so developing both
                # removes L1 and L1. Incrementing the level per removal printed
                # "brewery L1 + brewery L2" for a pair that is really L1 + L1,
                # and a player looking for L1+L1 concluded it was not offered.
                seen, levels = {}, []
                for ind in action.industries:
                    n = seen.get(ind, 0)
                    counts, lvl, skip = state.players[seat].mat[ind], None, n
                    for i, c in enumerate(counts):
                        if not c:
                            continue
                        if skip < c:
                            lvl = i + 1
                            break
                        skip -= c
                    levels.append(lvl)
                    seen[ind] = n + 1
                m.update(industries=[i2.value for i2 in action.industries],
                         levels=levels)
            elif isinstance(action, Scout):
                # Scouting discards THREE cards: the one played plus two more.
                # Without these the options are twenty identical sentences and
                # you cannot tell which two you are giving up.
                m.update(extra=list(action.extra))
            elif isinstance(action, Sell):
                m.update(beer=_draws(state, getattr(action, "beer", ())),
                         price=0, revenue=0,
                         sales=[{"town": s.town, "merchant": s.merchant}
                                for s in action.sales],
                         own_beer=bool(getattr(action, "own_beer", False)),
                         tiles=len(action.sales))
            moves.append(m)
    return {
        "coords": coords(),
        "towns": [{"id": t.id, "name": t.name,
                   "slots": [sorted(i.value for i in s) for s in t.slots],
                   "farm": t.farm_brewery}
                  for t in state.data.towns.values()],
        "merchants": {mid: [{"kind": s.kind, "beer": s.beer} for s in slots]
                      for mid, slots in state.merchants.items()},
        # Which merchant to sell into is one of the few free choices in a Sell,
        # and the bonus is the whole basis for it -- a Gloucester sale is a free
        # Develop. Sending bare ids made that invisible.
        "all_merchants": [{"id": mid, "bonus": m.bonus_type,
                           "amount": m.bonus_amount}
                          for mid, m in state.data.merchants.items()],
        "tiles": tiles,
        "links": links,
        "all_links": all_links,
        "era": state.era.value,
        "round": state.round,
        "rounds_this_era": state.rounds_this_era,
        "turn_order": list(state.turn_order),
        # A finished game has no player to move: the engine leaves turn_pos one
        # past the end, so asking raises. snapshot() is the first thing the UI
        # requests after the final action, so this crashed the page exactly when
        # the game ended -- and only a game played to its natural end, which is
        # why hand testing never hit it.
        "current": (state.current.idx
                    if not state.finished
                    and state.turn_pos < len(state.turn_order) else -1),
        # The first Canal round is one action and every other turn is two, so
        # without this you cannot tell whether the board in front of you is
        # still yours to change.
        "actions_left": state.actions_left,
        "seat": seat,
        "finished": state.finished,
        "winners": list(winners(state)) if state.finished else [],
        "coal_market": state.coal,
        "iron_market": state.iron,
        # Cubes left is not the number a player reasons with -- the PRICE is,
        # and a mine built into a short market sells its cubes on placement.
        "coal_price": state.data.coal.price_to_buy_one(state.coal),
        "iron_price": state.data.iron.price_to_buy_one(state.iron),
        "coal_slots": _slots(state.data.coal, state.coal),
        "iron_slots": _slots(state.data.iron, state.iron),
        "coal_empty_price": state.data.coal.empty_price,
        "iron_empty_price": state.data.iron.empty_price,
        "coal_prices": _ladder(state.data.coal, state.coal),
        "iron_prices": _ladder(state.data.iron, state.iron),
        "coal_cap": state.data.coal.capacity,
        "iron_cap": state.data.iron.capacity,
        "players": [{"idx": i, "vp": p.vp, "projected": proj[i],
                     "money": p.money, "income": p.income,
                     "income_space": p.income_space,
                     # The track is nonlinear and a loan moves the marker by
                     # LEVELS, so "how many flips until the next level" is not
                     # something you can read off the level alone.
                     "income_to_next": max(
                         0, highest_space_of_level(p.income) - p.income_space + 1),
                     "spent": p.spent, "links_left": p.links_left,
                     "hand": len(p.hand),
                     "order": state.turn_order.index(i)
                              if i in state.turn_order else None}
                    for i, p in enumerate(state.players)],
        "hand": [{"kind": c.kind.value, "town": c.town,
                  "industries": sorted(i.value for i in (c.industries or ()))}
                 for c in me.hand],
        "mat": _with_buildable(state, seat, mat_ladder(state, seat), moves),
        # Every seat's next tile, so an opponent one develop from a level-3
        # cotton is visible rather than a surprise.
        # Our own row carries `buildable`, taken from the legal move list, so
        # "can build now" is exact rather than inferred from cash. Opponents get
        # the ladder without it -- affordability is only meaningful on the seat
        # that is actually to move.
        "mats": [_with_buildable(state, i, mat_ladder(state, i), moves) if i == seat
                 else mat_ladder(state, i)
                 for i in range(state.n_players)],
        "deck": len(state.deck),
        "discard": sum(len(p.discard) for p in state.players),
        "wild_city": state.wild_location,
        "wild_ind": state.wild_industry,
        "can_undo": bool(g.get("undo")),
        "room": g.get("room", "main"),
        "rooms": sorted(GAMES),
        # Conceded rather than played out: the standings are real but the game
        # did not reach its own ending, and the UI says so.
        "ended": bool(g.get("ended")),
        "seed": g.get("seed"),
        "version": g.get("version", 0),
        "stale": bool(g.pop("stale_reply", False)),
        "exported": g.get("exported"),
        # Only once there is something to sum up. The client shows it in place
        # of the move list, which is empty at exactly the same moment.
        "summary": (summary(g) if state.finished or g.get("ended") else None),
        # Whether what is on disk is the finished game or a mid-game snapshot,
        # so the UI can say "saved" instead of prompting for a press.
        "autosaved": bool(g.get("exported")
                          and (g["state"].finished or g.get("ended"))),
        # Every table shares one process, so stopping the server stops all of
        # them. Every open page needs to say so rather than sit there polling a
        # socket that has gone.
        "stopping": STOPPING.is_set(),
        "moves": moves,
        "log": g["log"][-14:],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, body: bytes, kind: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        # The page is re-read from disk on every request precisely so the UI can
        # be edited while a game is running -- but a browser that caches it
        # serves the old file back on refresh, which looks exactly like the edit
        # never landed. It cost half an hour of "it's not there" once.
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/state"):
            g = game_for(room_of(self.path))
            with g["lock"]:
                self._send(json.dumps(snapshot(g)).encode(), "application/json")
        else:
            self._send(UI.read_bytes(), "text/html; charset=utf-8")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or "{}")
            if not isinstance(body, dict):
                body = {}
        except ValueError:
            body = {}
        g = game_for(room_of(self.path, body))
        # One request at a time per table. Threading means two clicks really can
        # arrive together, and every branch below mutates the game.
        with g["lock"]:
            self._handle(g, body)
            self._send(json.dumps(snapshot(g)).encode(), "application/json")

    def _handle(self, g: dict, body: dict) -> None:
        if self.path.startswith("/api/move"):
            state = g["state"]
            actions = legal_actions(state)
            i = int(body.get("index", -1))
            if int(body.get("version", -1)) != g.get("version", 0):
                # Refuse rather than guess: the index was drawn against a board
                # that no longer exists.
                g["stale_reply"] = True
                return
            if g.get("ended"):
                return
            if not state.finished and state.current.idx == g["seat"] \
                    and 0 <= i < len(actions):
                g["undo"].append((state.clone(), len(g["log"]), len(g["lines"]),
                                  len(g.get("replay", [])),
                                  json.loads(json.dumps(g.get("stats", {})))))
                del g["undo"][:-40]
                record(g, actions[i], i)
                advance(g)
        elif self.path.startswith("/api/export"):
            # Writing a file is the player's call, not the server's -- a game
            # abandoned halfway is not a log anyone wants on disk.
            g["exported"] = export_log(g)
        elif self.path.startswith("/api/undo"):
            if g["undo"]:
                st, nlog, nlines, nrep, stats = g["undo"].pop()
                g["state"] = st
                del g["log"][nlog:]
                del g["lines"][nlines:]
                del g.setdefault("replay", [])[nrep:]
                # JSON round-trip turned the seat keys into strings.
                g["stats"] = {int(k): v for k, v in stats.items()}
                bump(g)
        elif self.path.startswith("/api/new"):
            # Restart keeps the table it was set up with; only the deal changes.
            seed = body.get("seed")
            start(g, int(seed) if seed is not None else random.randrange(1, 10 ** 6),
                  int(body.get("players", g.get("players", 4))),
                  body.get("opponent", g.get("opponent", "heuristic")))
        elif self.path.startswith("/api/end"):
            g["ended"] = True
            autosave(g)
            bump(g)
        elif self.path.startswith("/api/shutdown"):
            # shutdown() blocks until serve_forever() returns, and serve_forever
            # is the loop currently waiting on THIS request, so calling it here
            # deadlocks the process against itself. A daemon thread lets the
            # response go out first and the loop end after it.
            STOPPING.set()
            if SERVER is not None:
                threading.Thread(target=SERVER.shutdown, daemon=True).start()


def _lan_addresses() -> list:
    """Best-effort local addresses to hand someone on the same network."""
    import socket
    out = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))       # no packet is sent; this just picks
        out.append(sock.getsockname()[0])   # the interface that would be used
        sock.close()
    except OSError:
        pass
    return out


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

    # Same reasoning for Scout, which discards THREE cards. The engine draws its
    # triples from the SCOUT_POOL most "expendable" cards by a hand-written
    # ranking, so with a full hand the two cards it judged least expendable
    # could never be scouted away. That is a sensible prune for a bot whose
    # evaluation cannot price a card -- widening it there measured null in all
    # four arms tried -- and it is not the bot's decision to make for a person.
    # The rules let you discard any three.
    _engine.SCOUT_POOL = 8                # every card in hand is a candidate
    _engine.MAX_SCOUT_VARIANTS = 56       # C(8,3), so no triple is cut

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--opponent", default="heuristic",
                    help="bot spec for the other seats, e.g. planner")
    ap.add_argument("--port", type=int, default=8765)
    # 127.0.0.1 by default: this is an unauthenticated dev server, so opening it
    # to the network has to be a deliberate act. --host 0.0.0.0 serves the LAN.
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 to let other devices on your network play")
    # Exported logs are pooled with the pasted Boomforge ones, and those scripts
    # filter on the player's name -- so pass the same name you play under there
    # if you want your UI games counted alongside them.
    ap.add_argument("--name", default="You",
                    help="name for your seat in exported logs")
    args = ap.parse_args()

    DEFAULTS.update(players=args.players, opponent=args.opponent,
                    name=args.name)
    # "main" is dealt from --seed so a solo session stays reproducible; every
    # other room gets its own random deal when someone first asks for it.
    main_game = {"lock": threading.Lock(), "room": "main", "name": args.name}
    GAMES["main"] = main_game
    start(main_game, args.seed, args.players, args.opponent)

    # Bind BEFORE announcing. The banner used to print first, so a port that
    # was already taken still advertised "share this: http://<ip>:8765" and then
    # died three lines later with the traceback scrolled past it.
    global SERVER
    try:
        SERVER = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"cannot listen on {args.host}:{args.port} -- {exc}", flush=True)
        if exc.errno == errno.EADDRINUSE:
            print("  something is already on that port. Stop it, or pass "
                  "--port with a free one.", flush=True)
        raise SystemExit(1)

    # flush=True throughout: stdout is block-buffered when it is not a terminal,
    # so redirected to a log the address you need to share never appears.
    print(f"BrassBot UI on http://{args.host}:{args.port}  "
          f"({args.players}p, seed {args.seed}, opponents: {args.opponent})",
          flush=True)
    if args.host != "127.0.0.1":
        for ip in _lan_addresses():
            print(f"  share this: http://{ip}:{args.port}", flush=True)
            print(f"  a second table: http://{ip}:{args.port}/?room=alice",
                  flush=True)
        print("  every room is its own game: one player against three bots, "
              "and rooms cannot see each other.", flush=True)
        print("  NOTE: no accounts and no passwords. Anyone who can reach this "
              "port can play, and can open any room.", flush=True)
    # Threaded: a bot's turn takes real time, and on one thread it would block
    # every other table's requests behind it.
    try:
        SERVER.serve_forever()
    except KeyboardInterrupt:
        pass
    SERVER.server_close()
    print("BrassBot UI stopped. Unexported games are gone.", flush=True)


if __name__ == "__main__":
    main()
