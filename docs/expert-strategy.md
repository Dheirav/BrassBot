# Expert strategy, and where our bot violates it

Summarised in my own words from a strategy guide by Mafiul Robin (400+ games,
tournament wins) on the Legendary Tactics channel
(https://www.youtube.com/watch?v=GZG5zzrM-wY), plus his coaching follow-up
(https://www.youtube.com/watch?v=SVYKyjFLhpM). Measurements are ours.

His claim for a player following this: **~70% win rate in a 4-player game**,
against a 25% baseline.

## The frame

Two things matter: **actions** and **victory points**. Actions are finite — 39 /
35 / 31 at 2 / 3 / 4 players — and winners average **more than 5 VP per action**.
Not income, not money, not VP at the end of the Canal Era. Only final VP.

This matches our yardstick's arithmetic exactly, derived independently.

## The rules, against our measurements

Re-measured on the current engine: 4p mirror, 200 games, 800 seats, seeds
0-199, after the four engine fixes (empty-network build, deterministic move
order, chosen discard, own-beer preference). VP 107.9, 11.96 builds a game.

| # | Expert rule | Ours | Verdict |
| --- | --- | --- | --- |
| 1 | Build **level 2+** in the Canal Era: they survive the wipe and score **twice** | 1.9 of 6.0 canal builds; mean level **1.38** | fails |
| 2 | Build **as few canals as possible**; ride other players' links | 4.7 canal links (band 2-4) | fails |
| 3 | Put **dead actions** (develop, loan, scout) in the Canal Era so the Rail Era is free for scoring | develops 2.0 canal / **2.7 rail**; loans 1.4 / 1.4 | **backwards** |
| 4 | **Iron and beer are universal** — failing to build enough of either loses the game | iron **1.9**, brewery 2.9 | iron thin |
| 5 | First develop is always **remove both level-1 breweries** | **iron+iron in half of all first develops**; the brewery pair is not in the top three | fails |
| 6 | **Never mix main industries** — you end up mid-level in several and score half | touches **4.52** industries | **exactly our failure** |
| 7 | **Make your own beer; don't live off merchant beer** | own **2.58** / opponent 1.45 / merchant 1.49 | now ok |
| 8 | **As few Sell actions as possible** — ideally one per era, flipping everything at once | **3.1 sells**, 1.62 tiles each | fails |
| 9 | Rail Era: **take link positions proactively**, they rival industries for VP | 7.95 rail links (band 7-10) | ok |
| 10 | Overbuild your own level-1 iron rather than building elsewhere — saves a link action | 0.20 overbuilds, **0.08** of them iron | fails |

Rule 7 has flipped, and it is worth being precise about why: the old reading was
"0.2 own barrels, a misconception he names and we commit". That was **our bug,
not our judgment**. `beer_plans` walked breweries in board order and drained
whatever came first alphabetically, so the bot could not prefer its own barrels
even when it wanted them. With the ordering fixed it takes own beer nearly twice
as often as an opponent's. We were never choosing merchant beer on purpose.

The lesson generalises: before reading a behaviour number as a strategic failure,
check that the bot was *able* to do the other thing.

Rules 3 and 8 remain genuine failures we arrived at independently from the
diagnostic, which is still a good sign for the diagnostic.

## What happened when agents actually played the guide

Three LLM agents played full 4p games through `tools/play.py`, each told to
follow this document. They scored **130, 119 and 116**, all winning their table —
above anything our bots reach. Their reports are the only evidence we have of the
guide being *executed* rather than scored against, and several rules did not
survive contact:

- **Rule 3 (dead actions in the Canal Era) is not free.** Coal rises from £1 to
  £6-8 over the Canal Era, which roughly doubles the cost of the links you then
  have to buy in the Rail Era. The guide never mentions this tax.
- **Rule 8 (one Sell per era) is blocked by the rules themselves** in the Canal
  Era, where one tile per town per player caps how much you can have standing
  ready to flip at once.
- **Rule 2 (as few canals as possible) conflicts with the guide's own
  manufacturer plan**: selling needs a merchant connection, and if you are riding
  other players' links nobody necessarily builds it.
- **"Build iron aggressively" was mostly unavailable.** One agent found no legal
  iron build for the entire Canal Era — every iron slot in its network was taken
  or blocked by the one-tile-per-town rule. That reframes our thin iron (1.9)
  as partly a board constraint rather than purely a preference.
- **The 76 VP link split looks unreachable at 4p.** Every Birmingham link was
  gone by Rail round 5 in one game; another finished 67 industry / 33 link, the
  reverse of the coached game. Links only pay when both ends are already dense.
- **Manufacturer level 3 has `link_vp` 0**, so manufacturers past the first two
  actively undermine the Rail-Era link plan. The guide's "no manufacturer in the
  rail era" is right for a reason it does not state.

Two agents independently found the beer bug above, and two independently found
that our move order was not deterministic. Playing the game surfaced four engine
bugs that thousands of self-play games never did, because self-play cannot notice
that a legal option was never offered.

## The 4-player recipe, concretely

He is specific about what to do at our target player count, and it is *cheap* —
**two develop actions in the whole game**:

1. **Develop 1**: remove both level-1 breweries.
2. **Develop 2**: remove one level-1 manufacturer, plus one level-1 coal *or*
   iron (whichever you have decided not to build).
3. Build **two level-2 manufacturers** and **two level-2 breweries** in the Canal
   Era, then sell both manufacturers using your own beer in **one** Sell action.
4. Build iron aggressively throughout — it is cheap for its VP and **flips with
   no Sell action** when anyone consumes it.
5. Keep canal links to the minimum.
6. In the Rail Era, spend actions on links, not on developing.

**Manufacturer is the 3-4 player industry** (cotton is the 2-player one; pottery
is high-risk in any count). The reason is the action budget: cotton III needs
five tiles cleared, which only 2p can afford. And the key detail that makes the
manufacturer line cheap — **both level-2 manufacturers need no coal**, so they can
be built anywhere without first paying an action for a link.

## Two rules our engine models but the bot ignores

- **Loans move income by LEVELS; flips move it by SPACES.** Doing loan-then-build
  versus build-then-loan in the same round can leave the marker a space higher or
  lower. Free VP for checking the order.
- **Turn order is a loop.** Spend least, go first. Alternate a cheap round
  (loan, beer) with an expensive one (quad rail) to take four actions
  back-to-back and stay out of opponents' way.

## What this changes

The bot's central failure now has an expert's name for it: it **mixes main
industries**. It touches 4.52 industries and finishes mid-level in all of them,
which is precisely the mistake he warns produces "half the points" of a committed
player. Our own numbers say the same thing — 4.2 VP per build against an expert
8-10.

## What the coached game actually looked like (4p, and it is not what I assumed)

From the follow-up coaching video, a full 4-player game played and won. The
final split was **76 VP from links, 57 from industry** — and the striking part:

> "we didn't make any manufacturer in the [rail era]"

They built roughly **four irons, two or three breweries, and exactly two level-2
manufacturers** — all in the Canal Era — and spent essentially the entire Rail
Era on links. Their whole industry output was ~6 tiles for 57 VP, or **~9.5 VP
per tile**. Ours is 12.0 builds for about 51 VP, or **4.2** — unchanged in rate
even though both the build count and the score have risen.

So the shape of a strong 4p game is: **few tiles, all level 2+, all flipped in
the Canal Era so they score twice — then links, links, links.**

### Manufacturer is chosen for being cheap, not for scoring

> "everything else — the beer, the iron and the links — will be the same whatever
> main industry you do... but you have a higher chance of winning when you went
> for manufacturer because you didn't have to put any effort other than taking a
> half action to develop level one manufacturer"

It is not the highest-scoring line. It is the line that costs **one develop
action**, leaving every other action free for iron, beer and links. That is a
different claim from the one I recorded earlier and it changes what to optimise.

### Income is not a goal — they won with the lowest income at the table

> "you look at all the other players, they have such high incomes compared to
> us... the game is won with victory points, not with income"

We weight income at `0.1125 x rounds`, worth ~1.7 VP per income level in the
early game — one of the largest terms we have — and the winner of that game had
the *worst* income on the board. That looked like a contradiction, so it was
tested directly.

**It is not one.** Sweeping the income weight head-to-head, one variant seat
against three baseline seats, raising it is monotonically worse (-4.2 at 0.17,
-15.8 at 0.3, -42.6 at 0.45) and lowering it buys nothing that survives
validation: 0.0563 read **+3.0 VP on the tune block and -1.1 on held-out seeds**.
The shipped 0.1125 sits at a flat optimum. Full table in `NEXT.md`.

Two agents separately reported the opposite of the guide — that a
merchant-connected coal mine flips on build, roughly pays for itself and jumps
income several spaces, so income is very much worth having. Both can be true: the
guide is arguing against *chasing* income, and our bot already ends on +13.7
income with 2.3 coal mines standing without being told to. It plays the line
already.

The distinction that matters: the agents were correcting **the guide**, not us.
An expert source being wrong does not imply we copied the error.

### Other concrete plays we do not make

- **Overbuild your own level-1 iron** with a higher-level iron rather than
  building elsewhere. The new site would need a link; the overbuild does not.
  Saving that action is worth more than the link's VP.
- **Place coal where your own links already are** — "you are not just getting VP
  for the coal, you are giving VP to your links."
- **Level 5 manufacturer carries a double link icon**; surround it with your own
  links.
- **Turn-order loop**: as last player take a loan or other cheap action to become
  first, then spend heavily on a quad rail (two double-rail actions) to fall back
  to last, and repeat. Four actions back to back.
- **Beer locations are taken fast.** Secure them proactively; an unflipped
  brewery you own still denies the site and still scores.

### Where our link VP actually goes

Their ~10-12 links produced **76 VP**; our 12.6 links produce about **57** (0.53
of 107.9 mean VP, from the yardstick's industry share) — roughly **4.5 each**
against their ~6-7. Link VP counts icons on *flipped* tiles in adjacent
locations, so their links score more because they are built **around industry
that was already flipped in the Canal Era**. Same board, different order of
operations.

The agents' games qualify this. Both reported that by the middle of the Rail Era
every link touching a dense town was already taken, leaving final link actions
worth 0-2 VP each. The deadline is earlier than the guide implies, and one agent
finished 67 industry / 33 link and still won — so the 76/57 split is one shape of
a strong game, not the only one.
