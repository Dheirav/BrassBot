"""Play a game one move at a time from the command line.

Built so a person -- or an agent with a shell -- can play a seat against the bots
without holding the game in their head. State persists between invocations, so
each call is one decision.

    tools/play.py new --seed 1 --out /tmp/g.pkl     # you are seat 0
    tools/play.py show /tmp/g.pkl                   # board, hand, legal moves
    tools/play.py move /tmp/g.pkl 7                 # play move 7, opponents reply

Opponents are played by the `heuristic` bot unless --opponent names another,
e.g. `--opponent planner` to face the strongest bot we have (slower per move). After your move the game runs on
until it is your turn again, so `show` always presents a decision that is yours.
"""
import argparse
import pickle
import sys

from brassbot.actions import Build, Develop, Loan, Network, Pass, Scout, Sell
from brassbot.bots import make
from brassbot.engine import apply_action, legal_actions
from brassbot.gamedata import Era
from brassbot.state import new_game

SEAT = 0


def _card(state, seat: int, idx: int) -> str:
    """The card an action spends. Every action discards one, and which one it is
    was invisible here -- four agents reported losing the exact card their plan
    needed to an action that never said what it was taking."""
    hand = state.players[seat].hand
    if not 0 <= idx < len(hand):
        return "?"
    c = hand[idx]
    if c.town:
        return c.town
    if c.industries:
        return "/".join(sorted(i.value for i in c.industries))
    return c.kind.value


def _plan(plan, label: str) -> str:
    """Where a resource actually comes from.

    Free coal out of an opponent's mine and 8 pounds of market coal used to
    render identically, which makes two listed moves impossible to choose
    between.
    """
    if not plan:
        return ""
    bits = []
    for d in plan:
        if d.kind == "market":
            bits.append(f"market GBP{d.cost}")
        elif d.kind == "merchant_beer":
            bits.append(f"{d.merchant} barrel")
        else:
            bits.append(str(d.town))
    return f" {label}<{'+'.join(bits)}>"


def describe(state, action) -> str:
    # The ACTING player, not seat 0: describing a bot's move against your own
    # mat and hand gave the wrong tile level and the wrong card.
    seat = state.current.idx
    p = state.players[seat]
    if isinstance(action, Build):
        lvl = p.lowest_level(action.industry)
        spec = state.data.tile(action.industry, lvl)
        bits = [f"cost {spec.cost}"]
        if spec.coal_cost:
            bits.append(f"{spec.coal_cost} coal")
        if spec.iron_cost:
            bits.append(f"{spec.iron_cost} iron")
        occupied = state.tiles[action.town][action.slot]
        over = " (overbuild)" if occupied is not None else ""
        return (f"BUILD {action.industry.value} L{lvl} at {action.town}{over}"
                f"  [{', '.join(bits)}, {spec.vp} VP, +{spec.income} income]"
                f"  card:{_card(state, seat, action.card)}"
                f"{_plan(action.coal, 'coal')}{_plan(action.iron, 'iron')}")
    if isinstance(action, Network):
        kind = "canal" if state.era is Era.CANAL else "rail"
        return (f"NETWORK {kind}: " + " + ".join(action.lines)
                + f"  card:{_card(state, seat, action.card)}"
                + _plan(action.coal, "coal") + _plan(action.beer, "beer"))
    if isinstance(action, Develop):
        return ("DEVELOP " + " + ".join(i.value for i in action.industries)
                + f"  card:{_card(state, seat, action.card)}"
                + _plan(action.iron, "iron"))
    if isinstance(action, Sell):
        return ("SELL " + ", ".join(
            f"{state.tiles[s.town][s.slot].industry.value} at {s.town}"
            f" -> {s.merchant}#{s.mslot}" for s in action.sales)
            + f"  card:{_card(state, seat, action.card)}")
    if isinstance(action, Loan):
        return f"LOAN  [+30 money, -3 income levels]  card:{_card(state, seat, action.card)}"
    if isinstance(action, Scout):
        gone = ", ".join(_card(state, seat, i)
                         for i in (action.card, *action.extra))
        return f"SCOUT [take wild location + wild industry]  discards:{gone}"
    if isinstance(action, Pass):
        return f"PASS  card:{_card(state, seat, action.card)}"
    return str(action)


def render(state) -> str:
    p = state.players[SEAT]
    out = [f"=== {state.era.value.upper()} era, round {state.round}/"
           f"{state.rounds_this_era} | actions left this turn: {state.actions_left} ==="]
    out.append(f"YOU (seat 0): {p.money} money, income {p.income}, {p.vp} VP, "
               f"{p.links_left} link tiles left")
    out.append("  hand: " + ", ".join(sorted(repr(c) for c in p.hand)))
    mat = ", ".join(f"{i.value}:L{p.lowest_level(i)}" for i in state.data.tiles
                    if p.lowest_level(i))
    out.append("  next tile on your mat: " + mat)

    others = ", ".join(f"seat {i}: {q.vp} VP / income {q.income} / {q.money} money"
                       for i, q in enumerate(state.players) if i != SEAT)
    out.append("OPPONENTS: " + others)

    board = []
    for town, slots in state.tiles.items():
        here = [f"{('YOU' if t.owner == SEAT else 's' + str(t.owner))}"
                f":{t.industry.value[:4]}L{t.level}{'*' if t.flipped else ''}"
                for t in slots if t is not None]
        if here:
            board.append(f"{town}[{' '.join(here)}]")
    out.append("BOARD (* = flipped): " + ("; ".join(board) if board else "empty"))
    links = [f"{lid}={'YOU' if o == SEAT else 's' + str(o)}"
             for lid, o in state.links.items()]
    out.append("LINKS: " + ("; ".join(links) if links else "none"))
    out.append(f"MARKETS: coal {state.coal}/14 (next costs "
               f"{state.data.coal.price_to_buy_one(state.coal)}), "
               f"iron {state.iron}/10 (next costs "
               f"{state.data.iron.price_to_buy_one(state.iron)})")
    merch = "; ".join(f"{m}:" + ",".join(f"{s.kind}{'+beer' if s.beer else ''}"
                                         for s in slots)
                      for m, slots in state.merchants.items())
    out.append("MERCHANTS: " + merch)
    return "\n".join(out)


def advance(state, bots):
    """Run the game on until it is our turn, or it ends."""
    while not state.finished and state.current.idx != SEAT:
        actions = legal_actions(state)
        if not actions:
            break
        apply_action(state, bots[state.current.idx].choose(state, actions))


def show(state):
    if state.finished:
        scores = [p.vp for p in state.players]
        print(f"GAME OVER. Final scores by seat: {scores}")
        print(f"You (seat 0) scored {scores[SEAT]}. "
              f"Best opponent: {max(s for i, s in enumerate(scores) if i != SEAT)}.")
        return
    print(render(state))
    actions = legal_actions(state)
    print(f"\nLEGAL MOVES ({len(actions)}) -- reply with: tools/play.py move <file> <n>")
    for i, a in enumerate(actions):
        print(f"  {i:>3}: {describe(state, a)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new"); n.add_argument("--seed", type=int, default=1)
    n.add_argument("--players", type=int, default=4); n.add_argument("--out", required=True)
    n.add_argument("--opponent", default="heuristic",
                   help="bot spec for the other seats, e.g. planner")
    s = sub.add_parser("show"); s.add_argument("file")
    m = sub.add_parser("move"); m.add_argument("file"); m.add_argument("index", type=int)
    args = ap.parse_args(argv)

    if args.cmd == "new":
        state = new_game(args.players, seed=args.seed)
        bots = [make(args.opponent, seed=args.seed * 10 + i)
                for i in range(args.players)]
        advance(state, bots)
        with open(args.out, "wb") as fh:
            # The opponent spec is saved with the game: `move` rebuilds the
            # bots from scratch each invocation and must rebuild the same ones.
            pickle.dump((state, args.seed, args.players, args.opponent), fh)
        show(state)
        return 0

    with open(args.file, "rb") as fh:
        loaded = pickle.load(fh)
        # Older saves predate the opponent field.
        state, seed, players = loaded[:3]
        opponent = loaded[3] if len(loaded) > 3 else "heuristic"
    bots = [make(opponent, seed=seed * 10 + i) for i in range(players)]

    if args.cmd == "move":
        actions = legal_actions(state)
        if not 0 <= args.index < len(actions):
            print(f"error: move must be 0..{len(actions) - 1}", file=sys.stderr)
            return 1
        print(f"you played: {describe(state, actions[args.index])}")
        apply_action(state, actions[args.index])
        advance(state, bots)
        with open(args.file, "wb") as fh:
            pickle.dump((state, seed, players, opponent), fh)
    show(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
