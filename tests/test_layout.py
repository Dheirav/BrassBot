"""The map's coordinates, checked against the box the UI draws them in.

Two of these were found by eye, in a screenshot, after they shipped: merchant
boxes at Shrewsbury and Nottingham hung 14 units out over the score track, which
is drawn in the frame around the board. Eyeballing a 26-town map does not scale,
and the drawing rules are simple arithmetic, so they are asserted here instead.

The numbers below mirror `tools/ui/index.html`. If a shape's size changes there,
it changes here, and the point of the pairing is that the test fails loudly
rather than the map quietly growing a defect nobody looks at.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "ui"))

from layout import ALL  # noqa: E402

from brassbot.gamedata import load  # noqa: E402

# BOARD in index.html: the paper the map is drawn on. Outside it is the track.
X0, Y0, X1, Y1 = 28, 30, 782, 774

# Shape sizes, as index.html draws them.
MERCHANT_W, MERCHANT_UP, MERCHANT_DOWN = 92, 22, 32
SLOT_W, TILE_UP, TILE_DOWN = 32, 13, 14
NAME_UP = 20  # the town name sits above its tiles

# Being a unit inside the edge is not the same as looking like it. Warrington
# sat 3 units off the top border, which reads as touching the score track and
# was reported as an overlap twice.
CLEARANCE = 6


@pytest.fixture(scope="module")
def data():
    return load()


def _over(box, pad=CLEARANCE):
    x0, y0, x1, y1 = box
    return [f"{name} ({gap:.0f} short)" for name, gap, bad in (
        ("left", X0 + pad - x0, x0 < X0 + pad),
        ("top", Y0 + pad - y0, y0 < Y0 + pad),
        ("right", x1 - (X1 - pad), x1 > X1 - pad),
        ("bottom", y1 - (Y1 - pad), y1 > Y1 - pad)) if bad]


def test_every_town_has_a_coordinate(data):
    missing = [t for t in data.towns if t not in ALL]
    missing += [m for m in data.merchants if m not in ALL]
    assert not missing, f"no coordinate for {missing}"


def test_merchant_boxes_stay_off_the_score_track(data):
    """A merchant is a fixed 92x54 box, and the track is drawn in the frame."""
    over = {}
    for mid in data.merchants:
        x, y = ALL[mid]
        sides = _over((x - MERCHANT_W / 2, y - MERCHANT_UP,
                       x + MERCHANT_W / 2, y + MERCHANT_DOWN))
        if sides:
            over[mid] = (ALL[mid], sides)
    assert not over, f"merchant boxes hang over the track: {over}"


def test_town_tiles_and_names_stay_off_the_score_track(data):
    """Tiles are SLOT_W apart, and the name rides above the leftmost of them."""
    over = {}
    for tid, town in data.towns.items():
        x, y = ALL[tid]
        half = len(town.slots) * SLOT_W / 2
        sides = _over((x - half, y - NAME_UP, x + half, y + TILE_DOWN))
        if sides:
            over[tid] = (ALL[tid], sides)
    assert not over, f"town tiles hang over the track: {over}"


def test_no_two_towns_draw_on_top_of_each_other(data):
    """Overlapping footprints, which is what put a farm brewery in a link line.

    Merchants get their full box; towns get their tiles plus the name above.
    """
    boxes = {}
    for mid in data.merchants:
        x, y = ALL[mid]
        boxes[mid] = (x - MERCHANT_W / 2, y - MERCHANT_UP,
                      x + MERCHANT_W / 2, y + MERCHANT_DOWN)
    for tid, town in data.towns.items():
        x, y = ALL[tid]
        half = len(town.slots) * SLOT_W / 2
        boxes[tid] = (x - half, y - TILE_UP, x + half, y + TILE_DOWN)

    names = sorted(boxes)
    clashes = []
    for i, a in enumerate(names):
        ax0, ay0, ax1, ay1 = boxes[a]
        for b in names[i + 1:]:
            bx0, by0, bx1, by1 = boxes[b]
            ox = min(ax1, bx1) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > 0 and oy > 0:
                clashes.append(f"{a}/{b} overlap {ox:.0f}x{oy:.0f}")
    assert not clashes, "; ".join(clashes)


def test_a_farm_brewery_sits_beside_what_it_links_to(data):
    """Both farm breweries have exactly one link, so both must sit on it.

    The southern one was drawn at x=620 and the northern at (200, 180), each on
    the far side of the board from the only thing it connects to, so those links
    rendered as spokes reaching across empty map to a brewery nobody could
    associate with either end.
    """
    farms = [t for t in ALL if t.startswith("farm_")]
    assert farms, "no farm breweries found"
    far = []
    for farm in farms:
        fx, fy = ALL[farm]
        for link in data.links:
            if farm not in link.ends:
                continue
            for other in link.ends:
                if other == farm:
                    continue
                ox, oy = ALL[other]
                span = max(abs(fx - ox), abs(fy - oy))
                if span > 200:
                    far.append(f"{farm} is {span} from {other}, which it links to")
    assert not far, "; ".join(far)
