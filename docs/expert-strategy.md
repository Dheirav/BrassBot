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

| # | Expert rule | Ours | Verdict |
| --- | --- | --- | --- |
| 1 | Build **level 2+** in the Canal Era: they survive the wipe and score **twice** | mostly level 1-2 | fails |
| 2 | Build **as few canals as possible**; ride other players' links | 4.9 canal links (band 2-4) | fails |
| 3 | Put **dead actions** (develop, loan, scout) in the Canal Era so the Rail Era is free for scoring | 2.8-3.7 develops in *rail* | **backwards** |
| 4 | **Iron and beer are universal** — failing to build enough of either loses the game | iron 3.2, brewery 2.2 of 4 | fails |
| 5 | First develop is always **remove both level-1 breweries** | develops spread across 5 industries | fails |
| 6 | **Never mix main industries** — you end up mid-level in several and score half | touches 4.25 industries, all low | **exactly our failure** |
| 7 | **Make your own beer; don't live off merchant beer** | 0.2 own barrels | **named misconception** |
| 8 | **As few Sell actions as possible** — ideally one per era, flipping everything at once | 1.04 tiles per sell | **named misconception** |
| 9 | Rail Era: **take link positions proactively**, they rival industries for VP | 8.5 rail links (band 7-10) | ok |
| 10 | Overbuild your own level-1 iron rather than building elsewhere — saves a link action | rare | fails |

Three of our measured failures (3, 7, 8) are ones he calls out by name as
mistakes intermediate players make. We arrived at them independently from the
diagnostic, which is a good sign for the diagnostic.

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
industries**. It touches 4.25 industries and finishes mid-level in all of them,
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
per tile**. Ours is 10.1 tiles for 42.5 VP, or **4.2**.

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

**This contradicts our evaluation.** We weight income at `0.1125 x rounds`, worth
~1.7 VP per income level in the early game — one of the largest terms we have.
The winner of that game had the *worst* income on the board. Income is
instrumental: it buys actions, and it stops mattering the moment the actions run
out.

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

Their ~10-12 links produced **76 VP**; our 13.2 links produce **48.9** — about
3.7 each against their ~6-7. Link VP counts icons on *flipped* tiles in adjacent
locations, so their links score more because they are built **around industry
that was already flipped in the Canal Era**. Same board, different order of
operations.
