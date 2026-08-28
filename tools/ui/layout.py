"""Board coordinates for the web UI.

The game data carries no positions -- only a `region` per town -- so these are
placed by hand to match the printed board's geography closely enough to be
recognisable: Birmingham central, the Black Country west, Staffordshire and
Derbyshire north, the merchants around the edges where they belong.

Coordinates are in a 0-1000 x 0-800 space; the page scales them.
"""

TOWNS = {
    # Staffordshire / north
    "stoke_on_trent": (330, 70),
    "leek": (430, 40),
    "stone": (330, 170),
    "uttoxeter": (450, 160),
    # Derbyshire / north-east
    "belper": (610, 90),
    "derby": (620, 190),
    # Midlands
    "stafford": (300, 260),
    "burton_on_trent": (520, 260),
    "cannock": (350, 340),
    "tamworth": (500, 360),
    "walsall": (390, 420),
    "nuneaton": (620, 400),
    # Black Country / west
    "coalbrookdale": (170, 330),
    "wolverhampton": (290, 420),
    "dudley": (280, 500),
    "kidderminster": (250, 590),
    "worcester": (280, 690),
    # Birmingham region
    "birmingham": (450, 500),
    "coventry": (640, 520),
    "redditch": (470, 640),
    # Farm breweries
    "farm_northern": (200, 180),
    "farm_southern": (620, 690),
}

MERCHANTS = {
    "warrington": (250, 30),
    "nottingham": (750, 120),
    "shrewsbury": (60, 420),
    "oxford": (720, 660),
    "gloucester": (400, 780),
}

ALL = {**TOWNS, **MERCHANTS}
