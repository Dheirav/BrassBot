"""Render a game position to a standalone SVG file.

    PYTHONPATH=. .venv/bin/python tools/render.py --seed 1 --players 4 --moves 40 --out board.svg

Same picture the web UI draws, but written to a file -- useful for looking at a
position without a browser session, and for saving what a game looked like at a
given point.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "ui"))

from layout import ALL as C  # noqa: E402

from brassbot.bots import make  # noqa: E402
from brassbot.engine import apply_action, legal_actions  # noqa: E402
from brassbot.state import new_game  # noqa: E402

COL = ["#4da3ff", "#e05c5c", "#5fc98a", "#c88ce0"]
SHORT = {"coal_mine": "CO", "iron_works": "IR", "brewery": "BR",
         "cotton_mill": "CT", "manufacturer": "MF", "pottery": "PO"}


def render(state) -> str:
    o = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 860" '
         'width="1000" height="860"><rect width="1000" height="860" fill="#12141a"/>']
    def spokes(ends, stroke, width, dash=""):
        """Draw a link as spokes from its centroid.

        One link -- kidderminster-worcester-farm_southern -- joins THREE
        locations, so a link is not always a line between two points.
        """
        cx = sum(C[e][0] for e in ends) / len(ends)
        cy = sum(C[e][1] for e in ends) / len(ends)
        return "".join(
            f'<line x1="{C[e][0]}" y1="{C[e][1]}" x2="{cx:.0f}" y2="{cy:.0f}"'
            f' stroke="{stroke}" stroke-width="{width}" stroke-linecap="round"{dash}/>'
            for e in ends)

    built = dict(state.links)
    for link in state.data.links:
        if link.id not in built:
            o.append(spokes(link.ends, "#2c3242", 2, ' stroke-dasharray="5 5"'))
    for lid, owner in built.items():
        o.append(spokes(state.data.link_by_id[lid].ends, COL[owner], 4))

    for mid in state.data.merchants:
        x, y = C[mid]
        live = state.merchants.get(mid)
        kinds = " ".join((("-" if s.kind == "blank" else SHORT.get(s.kind, "ANY"))
                          + ("*" if s.beer else "")) for s in live) if live else "unused"
        o.append(f'<rect x="{x-46}" y="{y-17}" width="92" height="34" rx="8" fill="#242938"'
                 f' stroke="{"#e0a458" if live else "#333a4a"}"/>'
                 f'<text x="{x}" y="{y-3}" text-anchor="middle" font-family="sans-serif"'
                 f' font-size="10" font-weight="600" fill="#e6e8ee">{mid[:10]}</text>'
                 f'<text x="{x}" y="{y+9}" text-anchor="middle" font-family="sans-serif"'
                 f' font-size="9" fill="#8b93a7">{kinds}</text>')

    at = {(t, s): tile for t, s, tile in state.all_tiles()}
    for town in state.data.towns.values():
        x, y = C[town.id]
        n, w = len(town.slots), 26
        total = n * w
        o.append(f'<text x="{x}" y="{y-16}" text-anchor="middle" font-family="sans-serif"'
                 f' font-size="9" fill="#8b93a7">{town.name}</text>')
        for i, slot in enumerate(town.slots):
            sx = x - total / 2 + i * w
            tile = at.get((town.id, i))
            fill = COL[tile.owner] if tile else "#1e222c"
            op = 0.45 if tile and not tile.flipped else 1
            o.append(f'<rect x="{sx}" y="{y-11}" width="{w-3}" height="23" rx="4"'
                     f' fill="{fill}" fill-opacity="{op}" stroke="#39405280"/>')
            label = (SHORT[tile.industry.value] + str(tile.level) if tile
                     else "".join(SHORT[i2.value][0] for i2 in sorted(slot, key=lambda z: z.value)))
            o.append(f'<text x="{sx+(w-3)/2}" y="{y+3}" text-anchor="middle"'
                     f' font-family="sans-serif" font-size="10" font-weight="600"'
                     f' fill="{"#e6e8ee" if tile else "#8b93a7"}">{label}</text>')

    line = "  ".join(f"P{i}: {p.vp}VP  GBP{p.money}  inc {p.income}"
                     for i, p in enumerate(state.players))
    o.append(f'<text x="20" y="836" font-family="sans-serif" font-size="14"'
             f' fill="#e6e8ee">{state.era.value} round {state.round} —  {line}</text>')
    o.append("</svg>")
    return "\n".join(o)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--players", type=int, default=4)
    ap.add_argument("--moves", type=int, default=40)
    ap.add_argument("--bot", default="heuristic")
    ap.add_argument("--out", default="board.svg")
    a = ap.parse_args()
    state = new_game(a.players, seed=a.seed)
    bot = make(a.bot)
    for _ in range(a.moves):
        if state.finished:
            break
        apply_action(state, bot.choose(state, legal_actions(state)))
    Path(a.out).write_text(render(state))
    print(f"wrote {a.out} — {state.era.value} round {state.round}, "
          f"scores {[p.vp for p in state.players]}")


if __name__ == "__main__":
    main()
