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
import random
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "ui"))

from layout import ALL as COORDS  # noqa: E402

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
LOGS = Path(__file__).resolve().parent.parent / "logs"

# The pasted Boomforge logs name industries the way the board does, not the way
# our data keys them, and every analysis script in tools/ reads that wording.
LOGNAME = {"coal_mine": "coal", "iron_works": "iron", "cotton_mill": "cotton",
           "brewery": "brewery", "manufacturer": "manufacturer",
           "pottery": "pottery"}

GAME: dict = {}


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


def who(seat: int) -> str:
    return GAME.get("name", "You") if seat == GAME.get("seat", 0) else f"Bot {seat}"


def bump() -> None:
    GAME["version"] = GAME.get("version", 0) + 1


def record(action) -> None:
    """Log an action, then any era scoring it triggered."""
    state = GAME["state"]
    GAME["log"].append({"seat": state.current.idx,
                        "text": describe(state, action),
                        "pretty": move_label(state, action),
                        "round": state.round, "era": state.era.value})
    GAME["lines"].append(log_line(state, action, who(state.current.idx)))
    before = len(state.era_scores)
    apply_action(state, action)
    bump()
    for rec in state.era_scores[before:]:
        parts = []
        for i, pl in enumerate(state.players):
            gained = rec.link_vp[i] + rec.industry_vp[i]
            parts.append(f"{who(i)} +{gained} VP ({pl.vp})")
        GAME["lines"].append(f"{rec.era.value} era scored: " + ", ".join(parts))


def export_log() -> str:
    """Write the game so far in the pasted-log format, newest line first.

    Same shape as logs/*.log so tools that read those -- the playstyle and
    canal-bank analyses -- can pool UI games with the Boomforge ones.
    """
    state = GAME["state"]
    top = ([f"game over, winner: {', '.join(who(i) for i in winners(state))}"]
           if state.finished else
           [f"game in progress · {state.era.value} era round {state.round}"])
    body = list(reversed(GAME["lines"]))
    LOGS.mkdir(exist_ok=True)
    from datetime import datetime
    path = LOGS / (datetime.now().strftime("%Y%m%d-%H%M%S")
                   + f"-ui-{state.n_players}p.log")
    path.write_text("\n".join(top + body) + "\n")
    return str(path)


def start(seed: int, players: int, opponent: str) -> None:
    # Remembered so Restart can deal a fresh board with the same setup rather
    # than asking for it again.
    GAME["players"], GAME["opponent"], GAME["seed"] = players, opponent, seed
    GAME["ended"] = False
    GAME["state"] = new_game(players, seed=seed)
    GAME["bots"] = [make(opponent, seed=seed * 10 + i) for i in range(players)]
    GAME["seat"] = 0
    GAME["log"] = []
    GAME["lines"] = []
    # One snapshot per human action, so Undo rewinds past the bots' replies to
    # the position you actually chose from -- rewinding only your own move
    # would leave you staring at a board they had already answered.
    GAME["undo"] = []
    GAME["exported"] = None
    # A move is sent as an INDEX into the legal-action list, which the server
    # regenerates per request. Two tabs on one game, or a click racing an undo,
    # would apply a still-in-range index to a different list and play an action
    # nobody chose. The version pins an index to the position it was drawn for.
    GAME["version"] = 0
    advance()


def advance() -> None:
    """Let the bots play until it is the human's turn, or the game ends."""
    state, bots, seat = GAME["state"], GAME["bots"], GAME["seat"]
    while not state.finished and state.current.idx != seat:
        actor = state.current.idx
        actions = legal_actions(state)
        if not actions:
            break
        record(bots[actor].choose(state, actions))


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


def snapshot() -> dict:
    state, seat = GAME["state"], GAME["seat"]
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
    if not state.finished and state.current.idx == seat:
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
        "coords": COORDS,
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
        "can_undo": bool(GAME.get("undo")),
        # Conceded rather than played out: the standings are real but the game
        # did not reach its own ending, and the UI says so.
        "ended": bool(GAME.get("ended")),
        "seed": GAME.get("seed"),
        "version": GAME.get("version", 0),
        "exported": GAME.get("exported"),
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
        # The page is re-read from disk on every request precisely so the UI can
        # be edited while a game is running -- but a browser that caches it
        # serves the old file back on refresh, which looks exactly like the edit
        # never landed. It cost half an hour of "it's not there" once.
        self.send_header("Cache-Control", "no-store, must-revalidate")
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
            stale = int(body.get("version", -1)) != GAME.get("version", 0)
            if stale:
                # Refuse rather than guess: the index was drawn against a board
                # that no longer exists.
                self._send(json.dumps({**snapshot(), "stale": True}).encode(),
                           "application/json")
                return
            if GAME.get("ended"):
                self._send(json.dumps(snapshot()).encode(), "application/json")
                return
            if not state.finished and state.current.idx == GAME["seat"] \
                    and 0 <= i < len(actions):
                GAME["undo"].append((state.clone(), len(GAME["log"]),
                                     len(GAME["lines"])))
                del GAME["undo"][:-40]
                record(actions[i])
                advance()
        elif self.path.startswith("/api/export"):
            # Writing a file is the player's call, not the server's -- a game
            # abandoned halfway is not a log anyone wants on disk.
            GAME["exported"] = export_log()
        elif self.path.startswith("/api/undo"):
            if GAME["undo"]:
                st, nlog, nlines = GAME["undo"].pop()
                GAME["state"] = st
                del GAME["log"][nlog:]
                del GAME["lines"][nlines:]
                bump()
        elif self.path.startswith("/api/new"):
            # Restart keeps the table it was set up with; only the deal changes.
            seed = body.get("seed")
            start(int(seed) if seed is not None else random.randrange(1, 10 ** 6),
                  int(body.get("players", GAME.get("players", 4))),
                  body.get("opponent", GAME.get("opponent", "heuristic")))
        elif self.path.startswith("/api/end"):
            GAME["ended"] = True
            bump()
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
    # Exported logs are pooled with the pasted Boomforge ones, and those scripts
    # filter on the player's name -- so pass the same name you play under there
    # if you want your UI games counted alongside them.
    ap.add_argument("--name", default="You",
                    help="name for your seat in exported logs")
    args = ap.parse_args()

    GAME["name"] = args.name
    start(args.seed, args.players, args.opponent)
    print(f"BrassBot UI on http://localhost:{args.port}  "
          f"({args.players}p, seed {args.seed}, opponents: {args.opponent})")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
