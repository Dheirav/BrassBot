# Link scoring — settled from the component art

## The question

End-of-era link scoring reads:

> For each of your Link tiles, score 1 VP for each ⟨icon⟩ displayed in adjacent
> locations.

The icon is a symbol-font glyph that does not survive text extraction from
either the official Roxley rulebook or the Esoteric Order of Gamers summary, so
neither text source answers:

1. Do **unflipped** industry tiles display the icon, or only flipped ones?
2. Do **merchant locations** contribute icons of their own?

Both were resolved by reading the printed components directly.

## What the icon is

A black hexagon containing a dumbbell/link symbol (`⊷`).

Identified by cross-checking the player mat against our own tile data: the
banner beside **Coal Mine I** reads VP `1`, income `4`, and **two** hexagons;
beside **Coal Mine II** it reads VP `2`, income `7`, and **one** hexagon. Our
`link_vp` values for those tiles are 2 and 1. The match is exact across the mat,
which also independently confirms the `vp`, `income` and `link_vp` columns.

## Answer 1 — only flipped tiles

**The link icon is on the flipped face only.**

`docs/evidence/unflipped-tile-face.png` is an unflipped Coal Mine I at native
resolution. The tile shows exactly three things: the level (`I`), the artwork,
and two dark cubes in the bottom-right — the coal to place on it when built.
There is no VP number, no income number, and no link icon anywhere on it.

The `1 / 4 / ⊷⊷` banner sits *outside* the tile, on the parchment-coloured
player mat (`docs/evidence/player-mat-banner.png`). It is the mat's reference
for what that tile yields once flipped, not something printed on the tile.

This is consistent with the rulebook's description of the flipped face — "a
black top half and a VP icon in the bottom left corner" — and with the fact that
the rulebook explicitly qualifies *industry* scoring with "flipped" but does not
need to qualify link scoring: an unflipped tile displays nothing to count.

The design consequence is neat, and matters for the bot: **flipping a tile pays
twice** — the tile's own VP, plus switching on the link icons that every
adjacent link is counting.

## Answer 2 — merchants contribute 2 each

**Every merchant location displays 2 link icons**, permanently. Merchant spaces
are printed on the board and never flip.

Verified on the board scan for all five: Shrewsbury, Gloucester, Oxford,
Warrington, Nottingham (`docs/evidence/merchant-shrewsbury.png`,
`docs/evidence/merchant-warrington-nottingham.png`). The two hexagons sit above
each location's name banner. The count is per *location*, not per merchant slot
— Shrewsbury has a single merchant slot but still shows two icons.

So a link touching a merchant is worth a guaranteed 2 VP regardless of how the
board develops.

## Incidental confirmation

The pip clusters on each merchant slot mark the player counts at which that slot
is used: Shrewsbury 2/3/4, Warrington 3/4, Nottingham 4. That independently
confirms the `min_players` values already in `brass.json`.

## Where this lives in code

`brassbot/engine.py`:

```python
LINK_VP_COUNTS_UNFLIPPED_TILES = False
MERCHANT_LINK_ICONS = {"shrewsbury": 2, "gloucester": 2, "oxford": 2,
                       "warrington": 2, "nottingham": 2}
```

Pinned by `test_link_scoring_counts_flipped_tiles_regardless_of_owner`,
`test_unflipped_tiles_do_not_light_up_a_link` and
`test_every_merchant_shows_two_link_icons`.
