"""Parse a Boomforge (formerly Brassforge) game log into structured moves.

The site logs newest-first, one action a line, in the shape

    Dheirav Prakash built brewery 2 at Uttoxeter · card: Uttoxeter
    Bot 2 linked Uttoxeter-Stone and Derby-Uttoxeter · card: Cannock

with round headers, an era-change marker and a final scoring line. This reads it
back into chronological order and reports each player's action mix, so a real
game can be compared against what our bots do.

Why bother: every strong-play reference the project has is a quote from a guide
or an agent's write-up, and two of those turned out to be strategy-conditional
claims read as universal law. A log is evidence about what was actually played.

    PYTHONPATH=. .venv/bin/python tools/import_log.py game.log
    PYTHONPATH=. .venv/bin/python tools/import_log.py game.log --moves
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

# The site uses an en dash between link ends and a Unicode minus in income.
DASH = "[-‐-―−]"

RE_LINK = re.compile(rf"^(?P<who>.+?) linked (?P<links>.+?) · card: (?P<card>.+)$")
RE_BUILD = re.compile(
    r"^(?P<who>.+?) built (?P<ind>[a-z_]+) (?P<lvl>\d+) at (?P<town>.+?) · card: (?P<card>.+)$")
RE_LOAN = re.compile(r"^(?P<who>.+?) took a £(?P<amt>\d+) loan .*?· card: (?P<card>.+)$")
RE_DEV = re.compile(r"^(?P<who>.+?) developed (?P<inds>.+?) · card: (?P<card>.+)$")
RE_SELL = re.compile(r"^(?P<who>.+?) sold at (?P<town>.+?) · card: (?P<card>.+)$")
RE_BEER = re.compile(r"\(beer: (?P<beer>[^)]*)\)")
# Scout names the cards it took, plural, and discards more than one.
RE_SCOUT = re.compile(r"^(?P<who>.+?) scouted.*?· cards?: (?P<card>.+)$")
RE_PASS = re.compile(r"^(?P<who>.+?) passed\b")
RE_UNDO = re.compile(r"^(?P<who>.+?) undid their .*action\.?$")
RE_ROUND = re.compile(r"^Round (?P<n>\d+) income, (?P<rest>.+)$")
RE_SCORED = re.compile(r"^(?P<era>\w+) era scored: (?P<rest>.+)$")
RE_ERA = re.compile(r"^rail era begins")
RE_START = re.compile(r"^game started: (?P<players>.+)$")
RE_OVER = re.compile(r"^game over, winner: (?P<winner>.+)$")
# Shortfall recovery: the engine sells tiles to cover unpayable income.
RE_RECOVER = re.compile(r"^(?P<who>.+?) recovered £(?P<amt>\d+)")


@dataclass
class Move:
    who: str
    kind: str
    era: str
    round: int | None = None
    card: str | None = None
    detail: dict = field(default_factory=dict)


def parse(text: str) -> tuple[list[Move], list[str], dict]:
    # Newest-first on the page; play order is the reverse.
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][::-1]
    moves: list[Move] = []
    players: list[str] = []
    scores: dict = {}
    era, rnd = "canal", None

    for ln in lines:
        m = RE_START.match(ln)
        if m:
            players = [p.strip() for p in m.group("players").split(",")]
            continue
        m = RE_OVER.match(ln)
        if m:
            scores["winner"] = m.group("winner")
            continue
        if RE_ERA.match(ln):
            era, rnd = "rail", None
            continue
        m = RE_SCORED.match(ln)
        if m:
            scores[m.group("era")] = m.group("rest")
            continue
        m = RE_ROUND.match(ln)
        if m:
            # The header follows the round it closes, so the NEXT round is n+1
            # in the canal era; the site counts them down as it prints.
            rnd = int(m.group("n"))
            continue
        m = RE_RECOVER.match(ln)
        if m:
            # Not an action -- the engine forcing a sale to cover income.
            continue
        m = RE_UNDO.match(ln)
        if m:
            # An undo retracts the previous action by that player.
            for i in range(len(moves) - 1, -1, -1):
                if moves[i].who == m.group("who"):
                    moves.pop(i)
                    break
            continue

        for kind, rx in (("network", RE_LINK), ("build", RE_BUILD),
                         ("loan", RE_LOAN), ("develop", RE_DEV),
                         ("sell", RE_SELL), ("scout", RE_SCOUT)):
            m = rx.match(ln)
            if not m:
                continue
            g = m.groupdict()
            detail = {}
            if kind == "network":
                ends = re.split(r"\s+and\s+", g["links"])
                detail["links"] = [re.split(DASH, e) for e in ends]
                detail["double"] = len(ends) == 2
            elif kind == "build":
                detail.update(industry=g["ind"], level=int(g["lvl"]), town=g["town"])
            elif kind == "develop":
                detail["industries"] = [x.strip() for x in g["inds"].split("+")]
            elif kind == "sell":
                where = g["town"]
                detail["beer"] = RE_BEER.findall(where)
                # Strip the beer clauses, then the remainder is the town list.
                towns = RE_BEER.sub("", where)
                detail["towns"] = [t.strip() for t in towns.split(",") if t.strip()]
                detail["town"] = detail["towns"][0] if detail["towns"] else where
            elif kind == "loan":
                detail["amount"] = int(g["amt"])
            moves.append(Move(g["who"], kind, era, rnd, g.get("card"), detail))
            break
        else:
            if not RE_PASS.match(ln):
                print(f"  [unparsed] {ln}", file=sys.stderr)
            else:
                moves.append(Move(RE_PASS.match(ln).group("who"), "pass", era, rnd))
    return moves, players, scores


def summarise(moves, players, scores):
    if not players:
        players = sorted({m.who for m in moves})
    print(f"{len(moves)} actions, {len(players)} players\n")
    for era_name in ("canal", "rail"):
        rows = [m for m in moves if m.era == era_name]
        if not rows:
            continue
        print(f"  === {era_name} era: {len(rows)} actions ===")
        head = ["build", "network", "develop", "loan", "sell", "scout", "pass"]
        print(f"    {'player':<18}" + "".join(f"{h:>9}" for h in head)
              + f"{'doubles':>9}{'tiles dev':>11}")
        for p in players:
            mine = [m for m in rows if m.who == p]
            c = Counter(m.kind for m in mine)
            dbl = sum(1 for m in mine if m.detail.get("double"))
            devt = sum(len(m.detail.get("industries", [])) for m in mine
                       if m.kind == "develop")
            print(f"    {p:<18}" + "".join(f"{c.get(h, 0):>9}" for h in head)
                  + f"{dbl:>9}{devt:>11}")
        print()
    for key, line in scores.items():
        label = "WINNER" if key == "winner" else f"{key} era scored"
        print(f"  {label}: {line}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logfile")
    ap.add_argument("--moves", action="store_true", help="print every parsed move")
    ap.add_argument("--player", help="print only this player's moves")
    args = ap.parse_args(argv)

    moves, players, scores = parse(open(args.logfile, encoding="utf-8").read())
    if args.moves or args.player:
        for i, m in enumerate(moves, 1):
            if args.player and m.who != args.player:
                continue
            print(f"  {i:>3} {m.era:<6} r{m.round or '?':<3} {m.who:<18} "
                  f"{m.kind:<8} {m.detail} card={m.card}")
        print()
    summarise(moves, players, scores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
