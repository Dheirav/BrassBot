# Committing to one industry costs about 20 VP

Nine agent games on 2026-09-04, fable model, seat 0 against three shipped
`heuristic` bots at 4p, driven through `tools/play.py`. Two constrained lines
were played on **the same three boards** so the comparison is paired, and three
unconstrained games on adjacent seeds give the baseline.

The bot's own 4p mirror mean is **131.3, SD 12.4** — that is what a seat in this
pool is worth and the only fair yardstick.

## The result

| line | seeds | mean | z | games |
| --- | --- | --- | --- | --- |
| unconstrained | 9201-03 | **131.3** | +0.00 | 116, 128, 150 |
| BRIC (brewery/rail/iron/coal) | 9301-03 | 112.3 | -1.53 | 89, 112, 136 |
| manufactured goods only | 9301-03 | 111.0 | -1.64 | 102, 110, 121 |

Paired, board by board:

| seed | BRIC | manufacturer | difference |
| --- | --- | --- | --- |
| 9301 | 112 | 102 | +10 |
| 9302 | 89 | 110 | **-21** |
| 9303 | 136 | 121 | +15 |
| mean | 112.3 | 111.0 | **+1.3 +- 11.3** |

**The two archetypes are indistinguishable** (+1.3 against an error of 11.3;
BRIC takes 2 of 3 boards and loses the third by 21). What separates them from
the baseline is not which industry was chosen but that one was chosen at all:
**19.7 VP, from the same model with the same tooling on the same opponent pool.**

## Why BRIC does not win, despite its mechanism working

The hypothesis was action economy, and it held in every game. Coal and iron
flip when their cubes are consumed *by anyone*; a brewery flips when its beer is
drunk *by anyone*. Measured:

| seed | tiles flipped by opponents | by market sale on the build | Sell actions spent |
| --- | --- | --- | --- |
| 9301 | 6 of 11 | 2 | 0 |
| 9302 | 7 of 14 | 3 | 0 |
| 9303 | 8 of 16 | 4 | 0 |

Half the flips cost the player nothing and a quarter were free on placement,
several cash-positive -- an iron works into a drained market paid £9 net for 3
VP. Zero Sell actions across 93 actions. The advantage is real.

It is not enough, for a reason one agent put exactly: **"the BRIC mat only has
~85 VP of tiles and I flipped 14 of 15 -- I was near the tile ceiling and still
scored 89."** Coal is 2-4 VP a tile and iron 5-9, so even perfect conversion
caps low. The balance must come from rails, and rail VP depends on *opponents'*
flipped tiles at both ends, which the player does not control. The heuristic
bots saturate rail spots by the mid Rail Era; one run finished with **9 of 14
link tiles unplaced** and no legal NETWORK move at all.

So the constraint never became unplayable -- it became **empty**. From rail
round 6 the legal list held no BRIC-compatible build or link, and the last four
actions were, in the agent's words, "manufactured busywork": a Scout, an iron
works, and two Develops spent solely to eat its own iron cubes so a tile would
flip. That game ran at **2.9 VP per action against the 4.6 benchmark** and ended
with £56 and income 22, both table-highs and both worth nothing.

Ceiling estimates from the three BRIC agents: 150-160, 130-140, 90-100. The
spread is the finding -- the line is **board-dependent**, not reliably strong.

## Why manufacturer fails, and it fails differently

Range 102-121 against BRIC's 89-136: **lower variance, no upside.** All three
games led or matched at the canal break (43, 39, 32 VP) and collapsed in the
Rail Era.

The deficit is never industry VP -- 67, 50 and 81, squarely in the opponents'
range. It is **links**: 40, 28 and 33 against opponents' 52-73. The causal chain
was independently reported by all three:

1. **Every VP costs two actions.** Build then Sell, where coal and iron cost one
   -- they flip by being consumed.
2. **Beer gates the ladder.** 9 of 11 tiles need a barrel and L5 needs two. The
   four manufacturer-accepting merchant barrels are a shared pool that empties by
   mid-rail, so the player must brew their own -- and the beer spent selling is
   the beer not spent on a double rail.
3. **Refusing coal is what kills the links.** Coal L1 stays jammed on the mat,
   blocking coal for the whole Rail Era, so every rail link pays market coal at
   £4-6 and costs £9-10 all-in. One agent afforded five links; another, two.
4. **Cards.** Manufacturer needs the dual cotton/manufacturer card (8 of 64) or a
   location card for one of ~15 towns. Draws end at rail R4.

**The L3/L7 question never arises in practice.** They are the only sellable
tiles needing no beer, which makes them look like the backbone of the line -- but
L7 sits behind L5, L5 and L6 on the mat, so "the no-beer tile is only reachable
after the most beer-hungry stretch of the ladder." Two of three games never
built it. Where L3 *was* built, its zero link icons did exactly the predicted
damage: it sat on the player's only hub and turned that end of every link to
nothing, forcing the hub to move.

## What this says about the bot

Every agent, in every game, named the same loss mechanism -- our heuristic takes
the hub links in the first one or two Rail-Era rounds, and a plan formed a round
earlier has nowhere to land. That is the bot's real weapon and it is **denial,
not scoring**. A mirror match cannot show it, because there every seat does it.

The corollary is the practical one: **flexibility is worth ~20 VP**, and the
strongest agent game (150, a win) came from a player that built iron, breweries,
coal, a manufacturer and a pottery as the board offered them -- and had four
breweries and a coal mine flipped for free by opponents while doing it. It got
BRIC's mechanism without paying BRIC's ceiling.

## Manufacturer DEPTH is worse than manufacturer breadth

The first experiment banned support industries, which turned out to test the ban
rather than the strategy. A second pair of games removed the ban -- build coal,
iron, breweries, anything -- and asked only that the ladder be driven as deep as
possible, ideally to L8. Combined with the strict runs, five games:

| seed | support | top level reached | score |
| --- | --- | --- | --- |
| 9303 | banned | L5 | 121 |
| 9502 | free | L6 | **126** |
| 9302 | banned | L6 | 110 |
| 9301 | banned | L8 | 102 |
| 9501 | free | L8 | **99** |

Mean by depth: **L5 121.0, L6 118.0, L8 100.5.** Correlation between ladder
depth and final score **r = -0.86** (n=5, suggestive not conclusive). Both games
that reached L8 finished worst, including the one with full freedom to support
it. **Climbing costs roughly 20 VP against stopping at L5/L6.**

### Why: the ladder pays no premium for depth

VP per pound all-in, costing market coal and iron at £5:

| manufacturer | VP/£ | | BRIC | VP/£ |
| --- | --- | --- | --- | --- |
| L2 | 0.33 | | brewery L1 | 0.40 |
| L3 | 0.18 | | brewery L2 | 0.42 |
| L4 | 0.23 | | brewery L3 | 0.50 |
| L5 | 0.38 | | **brewery L4** | **0.71** |
| L6 | 0.35 | | iron L1 | 0.30 |
| L7 | 0.35 | | iron L2 | 0.42 |
| L8 | **0.37** | | iron L3 | 0.50 |
| | | | iron L4 | 0.53 |

**Manufacturer L8 returns 0.37 VP per pound against L2's 0.33 -- a 12% gain for
climbing six levels.** Brewery nearly doubles across its ladder and iron rises
77%. The industries that reward depth are BRIC's; manufacturer's ladder is flat,
so there is no reason to be at the top of it. Brewery L4 is the best tile in the
game on this measure -- 0.71 VP/£, 5 income, 2 link icons, and it flips for free
when anyone drinks it.

Three compounding costs make it worse than flat:

1. **Income-poor exactly where expensive.** L5 gives +2 income spaces and L8
   gives +1, against L4/L6's +6. Every tile above L4 needed a loan -- an action
   *plus* -3 income. One run took five loans and ended on income 6 against
   opponents' 12-18.
2. **One sell action per tile.** The rungs sit in different towns and beer is
   scarce, so they cannot be batched. Seed 9501 spent **8 of its 31 actions
   selling** and only 5 on links, finishing with 16 rail link VP against
   opponents' 30, 56 and 51.
3. **Zero-icon anchors.** L3 and L7 show no link icons and L2/L4/L6/L8 show one,
   so manufacturer-anchored links return ~3 VP where a brewery end gives 4-6.

**Where the climb stops paying:** through L3 in the Canal Era it is good -- cheap,
double-scored, and L3 needs no beer. It goes negative from L4. Stop at L3-L5 and
spend the Rail Era on double rails anchored on breweries and merchants.

## The human logs already say all of this

Seven logged seats by two strong human players against this same bot pool,
scoring 129-155:

| | mean | values |
| --- | --- | --- |
| sell actions | **0.57** | 0, 0, 0, 0, 1, 1, 2 |
| double rails | **4.86** | 4, 4, 5, 5, 5, 5, 6 |
| network actions | 8.43 | 6, 7, 9, 9, 9, 9, 10 |
| loans | 3.57 | 2, 3, 4, 4, 4, 4, 4 |

Builds by industry across all seven seats: **coal 26, brewery 22, iron 14,
pottery 6, manufacturer 2, cotton 0.** That is **89% BRIC**, and four of the
seven games involved no Sell action at all.

**These players are already playing BRIC** -- not approximately, but the pure
archetype -- and they score above our agents' attempts at it. So BRIC is not
weak; the agent runs at 89-136 were playing it badly, and the visible difference
is brewery timing: the human seats build 22 breweries across 7 games and take
4.86 doubles, because the breweries come first and are what make the doubles
possible. They are not brewing to sell. They are brewing to fuel links and to
hold 2-icon anchors.

The one caution: this is what strong play *looks like*, not proof of what causes
it. This repo has already tried steering the bot onto an expert behaviour band --
loans -- and it raised yardstick agreement from 4 of 11 dimensions to 7 while
costing **25 VP**. Find the mechanism, do not copy the profile.

## Seven archetypes, seventeen games: commitment itself costs ~20 VP

All 4p, fable agents in seat 0 against three shipped `heuristic` bots, driven
through `tools/play.py`. The bot's own 4p mirror mean is **131.3, SD 12.4**.

| archetype | n | mean | z | games |
| --- | --- | --- | --- | --- |
| **unconstrained** | 3 | **131.3** | +0.00 | 116, 128, 150 |
| manufacturer, batched sells | 2 | 116.5 | -1.19 | 113, 120 |
| BLIC (cotton swapped for coal) | 2 | 115.5 | -1.27 | 110, 121 |
| manufacturer, depth to L8, support free | 2 | 112.5 | -1.52 | 99, 126 |
| BRIC (brewery/rail/iron/coal) | 3 | 112.3 | -1.53 | 89, 112, 136 |
| manufacturer, strict | 3 | 111.0 | -1.64 | 102, 110, 121 |
| BRIC + pottery | 2 | 103.0 | -2.28 | 101, 105 |

Pooled: constrained **111.8** (n=14), unconstrained **131.3** (n=3). **No
archetype's mean reaches the baseline.** The cost of naming your industries in
advance is about **19.5 VP**, and it does not much matter which ones you name.

### The mechanism, stated by the agent that found it

> "When the board denies the slots, this archetype has no fallback, whereas an
> opportunist builds whatever is open."

That is the whole result. Every archetype was beaten the same way: an opponent
takes the slot or the link, and a committed player has a dead turn where a
flexible one has an alternative. It is not that any industry set is wrong -- the
BRIC agents' flip counts and pottery's per-action returns were both excellent --
it is that commitment converts a contested slot from an inconvenience into a
lost action, at 4.59 VP each.

### Adding an industry makes it worse, not better

BRIC+P was the natural fix for BRIC's two measured failures: an 85 VP tile
ceiling, and running out of legal moves (one agent finished with 9 of 14 link
tiles unplaced and two forced passes). Pottery is the right supplement on paper
and delivered on its own terms -- **5.3 and 6.0 VP per action across the two
games, the best per-action figures of any industry tested, against a 4.59
baseline**, at 0.62 VP/£.

It still scored worst of all seven, because **both games took ZERO double
rails**. The archetype's engine is breweries -> beer -> doubles, and both agents
lost the brewery race: "the bots built 8 breweries and filled every town brewery
slot by rail round 6; my brewery ladder was locked behind the unbuilt canal-only
L1."

**There are only 10 brewery towns and 11 brewery slots on the whole board.**
That makes them the scarcest strategic resource in the game -- scarcer than beer
itself, because beer regenerates and slots do not. Whoever wins that race owns
the double-rail engine; the loser has no BRIC at all.

### Why BLIC (cotton) fails specifically

Tested because cotton raises the tile ceiling from 85 to 154 VP at equal VP/£.
It scored 110 and 121, inside classic BRIC's range. Three reasons, all measured:

1. **The ceiling was never the constraint.** One agent used 6 of 11 cotton tiles
   and 34 of the 154 VP: "the binding constraints were beer supply, coal price
   and cash."
2. **Cotton consumes what coal produces.** Rail-era cotton needs coal and every
   rail link needs coal, so dropping coal makes you a net buyer of the resource
   you stopped producing -- one agent spent ~£56 on market coal in the rail era
   while the bots' mines flipped cash-positive into the same shortage.
3. **Beer, not the sell action, is cotton's real tax.** The agent with the best
   batching of the whole session (4 Sell actions flipping 6 tiles, 0.67
   actions/tile) still finished last.

At **2 players** the case is worse still: the 2p deck contains **zero
cotton/manufacturer industry cards** (6 at 3p, 8 at 4p), so cotton can only be
placed from a location card or a Scout wild. Both 2p BLIC agents went five or
six rounds before their first cotton was placeable.

### The "2p is solved by BLIC" claim does not survive a real opponent

A widely-cited r/boardgames thread reports 190-220 consistently at 2p with BLIC,
against the official app's AI. Tested here against our heuristic:

| seed | BLIC agent | our bot |
| --- | --- | --- |
| 9801 | 155 | **186** |
| 9802 | 168 | **191** |

BLIC lands at or below the bot's own 2p mirror mean of 162.9, while **the bot
reaches the claimed band** -- with coal, breweries, iron and 13-14 rail links,
not BLIC. Both agents independently concluded the claim is an artefact of an
opponent that does not contest links, slots or barrels, which is what the
thread's own sceptics said ("the AI cannot be used to measure the effectiveness
of a strategy"). Note the bot's 186-191 is partly a gift: it took 13-14 links
because the constrained agent contested only 8.

Caveat on seed 9801: the agent disclosed that a debugging dump accidentally
printed the remaining draw pile in canal round 4. It reports not acting on it,
and 9802 was clean and agreed, but treat 9801 as compromised.

---

## SUPERSEDING THE ABOVE: the same questions at n=120

Everything above is from agent games at n=2-3 against an SD of 12.4, so the
error bars are +-7 to +-10 and no magnitude in it should be quoted. The
mechanisms are sound -- flip counts, card gating, what agents reported hitting --
but the numbers are not. Re-run as banned-industry bots through the real
harness, 120 seat-balanced 4p games a cell, 2v2 against the unconstrained
heuristic:

| archetype (banned from building) | delta | se | sigma |
| --- | --- | --- | --- |
| unconstrained *(null control)* | +0.11 | 1.04 | 0.1 |
| BRIC | **-11.30** | 1.22 | -9.3 |
| BRIC + pottery | -7.74 | 1.12 | -6.9 |
| BRIC + cotton | -5.84 | 1.28 | -4.6 |
| BRIC + manufactured goods | -4.18 | 1.20 | -3.5 |
| no coal | -9.80 | 1.32 | -7.4 |
| **no brewery** | **-16.28** | 1.10 | **-14.7** |

The null control reads +0.11 +- 1.04 at an even win share, so the harness is
sound and these are trustworthy to about +-1.2 VP.

**Two corrections to the agent-game conclusions above.**

1. **Adding a selling industry to BRIC HELPS.** Pure BRIC costs -11.30; any one
   supplement recovers 3.6 to 7.1 VP. The section above reports BRIC+pottery as
   the *worst* archetype at 103.0 -- that came from two games and is wrong. Cost
   scales monotonically with how much is banned, which is what "commitment
   removes fallback" predicts when measured properly.
2. **The ~19.5 VP "cost of commitment" figure above is not a measurement.** It
   pools 14 games across six strategies. The real per-archetype costs are the
   table here, 4 to 11 VP depending on how much you give up.

**The finding that matters most: banning breweries costs -16.28 +- 1.10, more
than banning all three selling industries combined.** Brewery is the single most
valuable industry in the game, and coal is second at -9.80. That is consistent
with everything else: brewery is the only ladder rewarding depth (0.40 -> 0.71
VP/GBP), the only tile showing 2 link icons at every level, the only tile an
opponent will flip for you, and the only legal source of double-rail beer.

**Read the supplement ordering carefully.** These are bans on OUR BOT, whose 37
weights are tuned for unconstrained play, so "BRIC+manu is cheapest" means the
bot misses cotton and pottery least -- a revealed preference, not a claim about
which supplement a committed player should choose. The agent games give the
opposite ordering because they measure a different thing: a player who commits
and plays to it. Both are valid answers to different questions.

### Everyone playing BRIC at once

Four agents, no bots, all four on a BRIC core, each with a different supplement
(this is the test the r/boardgames thread called for and nobody ran):

| seat | line | score |
| --- | --- | --- |
| 1 | BRIC + pottery | **120** |
| 0 | pure BRIC | 114 |
| 3 | BRIC + manufactured goods | 104 |
| 2 | BRIC + cotton | 97 |

**Nobody reached 131.3.** Contention costs everyone 11-34 VP; the table produces
differently-sized losers rather than a winner. Pure BRIC survived it in second
with **zero Sell actions**, 12 rail links from 5 double rails, and 4 instant
cash-positive market flips -- but a 12 VP canal era and six loans: "three
opponents contesting coal/iron/breweries didn't starve it of moves, they starved
it of income."

Pottery won for a reason that is not about pottery: "**pottery was the one thing
nobody else wanted**" -- the "any" merchants at Warrington and Nottingham were
never contested. In a crowded field a supplement's value is how few others want
it.

**All 11 brewery slots were gone by rail round 2.** The seat that secured one
finished last; the seats with 4 and 5 finished first and second. Seat 3 spent
the very first action of the game taking Coalbrookdale's brewery.

## Turn order is worth about one action, and is not worth building for

Turn order is by money spent -- least spent goes first next round -- so going
last in round N and first in round N+1 gives four consecutive actions, twice the
window `pair_search` exploits. The heuristic has 37 weights and **none reads
`spent`**, so it never plays for this.

Measured before building anything:

    the bot already gets 1.12 double turns a game; 72% of seats get one
    correlation of double turns with final score: r = +0.106

    forced FIRST every round   134.7
    forced LAST  every round   129.8
    value of turn position     +4.81 +- 1.86 VP (2.6 sigma), wins 64% of pairings

**+4.81 is an UPPER BOUND** -- it hands a seat first position free, where a real
bot must pay actions and money for it, and the bot already stumbles into a
double turn most games. Against `pair_search`'s +7.6 for a window half the size,
the headroom is smaller and much harder to capture.

**Recommendation: do not build the turn-order term.** The prize is one action,
capture would be well under 100%, and the correlation evidence was already weak.
Chase the -16.28 on breweries instead -- not as a term to invent, but as a
signal that brewery slots are the scarcest asset in the game.
