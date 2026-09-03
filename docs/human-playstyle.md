# A human playstyle, measured

Distilled from six logged games on Boomforge — five by one player, one by
another — against that platform's bots. Five wins, one loss.

Every rule here carries the number it came from. Where a rule is the player's
stated reasoning rather than something measured, it says so. **This is not
verified strategy**: six games, one opponent pool, and the single loss has an
action profile indistinguishable from the wins, so the mix below is necessary at
best and certainly not sufficient.

Comparison columns are the Boomforge bots (18 seats) and our own heuristic.

## The core: links, and the beer that pays for them

**1. Links decide a 4p game.** Humans finish with 10.7 links worth **5.70 VP
each**; the Boomforge bots hold 7.2 at 4.50; our heuristic 8.8 at 5.11. That is
~61 VP of link scoring against ~32 — more than the margin of most games.

**2. Take double rails relentlessly.** 4.83 a game against the bots' ~2.2 and
our heuristic's 3.00. Two links for one action, £15 plus a coal each plus one
beer. Actions are the scarce resource — one is worth **4.59 VP** — so anything
that buys two links with one is close to free.

**3. Drink other people's beer.** A double rail's beer *cannot* come from a
merchant. It must come from a brewery: your own anywhere in your network, or **a
connected opponent's**. In one game the player took **five double rails having
built no brewery at all** — every barrel came from a rival. Humans build 1.67
rail breweries, *fewer* than the bots' 1.83, and take twice the doubles.

So when placing a link, ask what brewery it reaches, not only what it scores.
Our bot does not: its chosen links *lose* beer access on average (-0.42 barrels)
and in **50% of link decisions** it picks one with less access than an
alternative offered.

## Industry

**4. Skip cotton entirely.** Zero cotton builds across six games; the Boomforge
bots build 1.5 a game.

**5. Manufacturer deep, not wide.** 0.5 built a game reaching **level 4**; the
bots build 1.6 reaching 3.2. The reason is in the tile data: **manufacturer L3
and L7 are the only sellable tiles in the game needing NO beer** (L7 is 9 VP).
Everything else needs a barrel at every level.

**6. Iron early.** Built at 0.24 through the game against the bots' 0.43. A mine
or works placed into a short market sells its cubes on placement — sometimes for
more than it cost — and flips for VP and income at once.

  *Caveat, found by playing it:* "early" is not always reachable. An iron works
  costs coal, and coal off the market needs a merchant connection you may not
  have on turn one. On one agent board the rule was mechanically impossible for
  the whole opening. It describes what these players managed, not what a board
  always allows.

**7. Coal to taste, not to plan.** 3.2 a game, and the player's own account is
that they skip it when the market has no deficit to exploit and no good spot to
use it.

## Sequencing

**8. Pair a build with its link in the same turn.** 48% of two-action turns
against the bots' 26%. A turn is two of your own actions with no opponent
between them — the only window nobody can interrupt.

**9. Develop *then* build.** The humans' order is develop→build (10.3% of
turns); the bots' is build→develop (8.9%). Clear the mat first, then use what it
opened. The measured gap is small; what carries the weight is *when* — a develop
in the last two Canal-Era turns is too late to build on top of, which is rule 10.

**10. Clear level-1 tiles before the era ends.** They are canal-only: carry one
into the Rail Era and that industry is blocked until you develop it away. One
Develop removes two tiles. (Our own measurement: forcing a single Canal-Era
brewery develop is worth **+7.7 VP**.)

## What does *not* matter

**11. Canal-era VP is not a target.** Across five wins it ranged **13 to 45**,
and the highest canal score at the table finished last in two of the six games.
The yardstick's "expert 70-80 entering the Rail Era" comes from a quote scoped to
"a heavy industry player" and does not describe this line at all.

**12. Selling is rare.** 0-2 sales a game, and **two of the six wins involved no
sales whatsoever**. Our heuristic sells 1-5. Converting through links beats
converting through merchants here.

  *This is the rule that costs the most when read as an order.* It is a
  consequence, not a policy: these players sell little because they convert
  through links instead, not because selling is bad. An unflipped tile scores
  nothing and is removed at the era boundary regardless — so a sale that flips
  tiles before the Canal Era ends is not an exception to the style, it is the
  arithmetic the style depends on. An agent given "sell rarely" as an imperative
  skipped exactly that sale and finished last.

## The player's own reasoning, unmeasured

- **Pick the industry nobody is contesting.** Pottery was taken in one game
  specifically because the others took textiles and manufactured goods, leaving
  both the tiles and the merchant demand free. Measured support is thin but real:
  a contested pottery flips 44% of the time against 87% uncontested.
- **Compress a plan into as few turns as possible.** A plan spanning turns is
  exposed to six opponent actions at 4p. The one game lost was lost that way — a
  brewery-then-sell plan whose merchant slot was taken before it could finish.
- **Everything you hold on the board can be taken; money and cards cannot.**
  Beer sitting on your brewery is public. 41.6% of our bot's own barrels are
  drunk by opponents.

## Where this is weakest

Six games. One opponent pool. And the decisive caveat: the action mix in the
lost game is inside the range of the wins on every count — doubles, builds,
loans, develops. Whatever separated 155 from 101 is *placement and timing*, which
none of these rules capture.
