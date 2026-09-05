# NEXT — BrassBot

Live handover document. Current state, then what to pick up.

## Read this first

The rest of this document is a research journal, ordered by discovery. Sections
marked SUPERSEDED or RESOLVED were true when written and are not now. This block
is the current state; `docs/architecture.md` is where the code lives.

### Where the bot stands, 200 games a cell, report seeds

Refreshed 2026-09-04, after the pair search, the `blocked` fix and the re-tune.

| fmt | pool | all seats | SD | P10 | best |
| --- | --- | --- | --- | --- | --- |
| 4p | mirror | 131.3 +- 0.4 | 12.4 | 116 | 172 |
| 4p | vs greedy | 146.7 +- 1.1 | 15.0 | 129 | 184 |
| 3p | mirror | 144.8 +- 0.6 | 14.5 | 128 | 185 |
| 3p | vs greedy | 148.0 +- 1.4 | 19.3 | 121 | 193 |
| 2p | mirror | 162.9 +- 0.9 | 17.0 | 141 | 203 |
| 2p | vs greedy | 157.0 +- 1.4 | 19.6 | 134 | 217 |

That is +19.7 at 4p, +15.0 at 3p and +24.5 at 2p against the table this
replaced. The SD column is the one to quote against any new result: a change
worth less than about 1 VP is invisible in a 12-17 point spread without paired
seeds.

The previous table's figures are kept nowhere -- they were 111.6 / 133.9 /
129.8 / 138.0 / 138.4 / 136.5 and are superseded.

The mirror win rate is mechanical -- 25/33/50% is what identical seats must
produce -- so it is a sanity check, not a result. Read the vs-greedy row for
absolute strength: it is measured against a fixed opponent.

### The planner's lead has COLLAPSED: +14.78 -> +3.09, replicated

**2026-09-04.** Re-measured seat-balanced 2v2 at 4p after pair_search, three
disjoint blocks of 60 games:

| block | delta | se | win share |
| --- | --- | --- | --- |
| seed 0 | +3.67 | 1.75 | 62% |
| seed 1000 | +3.74 | 1.72 | 57% |
| seed 2000 | +2.12 | 1.55 | 57% |
| **pooled** | **+3.09** | **0.96** | 3.2 sigma |

Heterogeneity chi2 = 0.64 on 2 df: the blocks agree. **The lead fell 79%.**

The two bots share an evaluation, so lookahead is the only thing that ever
separated them -- and the heuristic now does two plies of it exactly, inside the
turn, for almost nothing. `pair_search` did not merely add VP; it ate most of
what the planner's 8-action horizon was being paid for. That is the same lesson
`blocked_lookahead` taught in reverse, and it generalises: **a cheap exact
search over the part of the game you control beats an expensive approximate
search over the part you do not.**

**This kills the distillation plan.** It was justified by ~15 VP of horizon
value out of reach of the live bot; at +3.09 there is little left to distil and
the planner costs ~180x per move to get it. Distillation is not worth building
now. What is still true is the *shape* of the finding -- see the beam-collapse
note further down, which said the planner is closer to "re-rank the one-ply
shortlist" than to a real 8-ply search. That reading now looks correct.

The section that follows is kept as written and is SUPERSEDED.

`planner` beats `heuristic` by **+14.78 +- 0.73** over three blocks (20.3 sigma,
~80% win share). The two share an evaluation -- `planner.py` scores its leaves
with `HeuristicBot` -- so the ONLY difference between them is that one looks
eight actions ahead and the other looks one.

Two things follow. **No amount of weight tuning can close this gap**, because
every evaluation gain lifts both bots equally; the old +25 came down to +14.78
partly because `blocked_lookahead` is a one-ply approximation of "an era
boundary is coming", which an 8-action horizon sees natively. And the remaining
~15 VP is the value of sequences a one-ply score cannot represent: the pottery
ladder, beer held across the boundary, a loan taken because you know what next
turn buys.

That makes **distillation** the right target -- train the evaluation on what the
planner CHOSE, so a one-ply bot inherits the horizon at no runtime cost. The
planner is ~180x slower per move, so it cannot be the live bot for advice during
a real game.

The old version of this table had eight headers over nine columns, so one figure
was unlabelled. The mirror win% is mechanical -- 25/33/50% is what identical
seats must produce -- and is a sanity check, not a result.

The planner (beam search) reaches about 133 head to head at 4p. Human tournament
**winners** score 142-184, median 158.

Compare **winning seat** against tournament figures: those are winners' scores,
and quoting our table average against them overstates the gap by ~30%. The gap to
a median tournament win is roughly 30 VP.

### What is true now

- **The biggest evaluation win was link valuation.** Links were scored only by
  neighbours that had already flipped, when 96% flip by rail scoring. Crediting
  unflipped neighbours is worth **+11 VP head to head**.
- **Only agents playing find rules bugs.** Seventeen so far, none from self-play,
  which cannot notice a legal move that was never offered. Roughly a third of
  what agents report does not survive checking, so verify before fixing.
- **The planner is the only search that pays**, about +25 VP head to head over
  the heuristic it was measured against -- though its beam collapses to one
  distinct first action by ply 2-4, so it is closer to "re-rank the one-ply
  shortlist" than to an eight-ply search.
- **Weight terms invented to patch a symptom lose.** Eleven tried, all at or
  below zero. Every term that has ever worked came instead from measuring what
  the term is actually PAID and comparing it to what the bot believes: links,
  beer, the loan charge, the mat.
- **One action is worth 4.59 +- 0.67 VP** (canal 5.33, rail 3.78), measured by
  overriding a single decision with a Pass on paired seeds. That is the exchange
  rate to price any term against. One evaluation unit is worth **0.76 VP**
  (`VP lost = 0.764 x eval deficit`, R2 = 0.999 over three generic
  perturbations). A random legal move recovers 42% of an action's value, so the
  whole evaluation is worth 2.68 VP per decision over a die roll -- and the
  bot's #1 pick beats its own #2 by **0.30 +- 0.56**, i.e. nothing. The top of
  the 53-candidate shortlist is flat, which is the beam-collapse finding
  arrived at from the other side, and it is why so many term ideas measure zero:
  they re-order candidates that are worth the same.

### The 1-vs-3 harness flatters any change by about +0.5 VP

Three deliberately near-neutral **placebos** measured **+0.74, +0.39, +0.47** on
the report block. The odd seat out gains simply by not contending for the same
slots as three copies of itself, roughly in proportion to how much its play
differs. Signs survive this; sizes do not.

Use the seat-balanced **2v2** (six pairings, every seat variant in half of them)
before believing a magnitude. It has repeatedly cut a 1v3 result by 2-3x, and
once to nothing:

| change | 1v3 | 2v2, seat-balanced | verified, 3 blocks |
| --- | --- | --- | --- |
| `loan_bias` 1.5 | +2.85 +- 0.59 | +1.86 +- 0.94 | **+1.22 +- 0.35** |
| beer split | +3.01 +- 0.53 | +1.60 +- 0.54 | **+1.93 +- 0.35** |
| `mat_potential` 0.25 -> 0.125 | +2.66 +- 0.68 | +1.0 | **-1.44 +- 0.38** |

The last column is three fresh blocks of 480 games, measured in the tree the
change actually ships in. `mat_potential` was shipped on the middle column and
had to be reverted: by the time it was re-measured, `loan_bias`, `beer_rail`,
`off_plan_bias` and a generation fix had all landed. **Anything measured against
a snapshot has to be re-measured in the tree it will ship in.** At 2p the same
change is +2.97, so it lives in `PROFILES` now.

A null control run alongside these returned **-0.17 +- 0.37** with normal
heterogeneity, so the harness itself is sound and these numbers mean what they
say.

### The per-format profiles were fitted by the biased tuner, and one cost 10 VP

`PROFILES` overrode `unflipped` at 0.1875 for 2p and 0.2812 for 3p against a
default of 0.375. Removing both is **+10.08 +- 0.62 at 2p** and **+2.34 +- 0.57
at 3p**, three blocks each. That is the largest single change in the project and
it is a deletion. They were fitted when the tuner still scored one seat against
three copies of the baseline -- a harness that pays ~+0.5 for any change -- which
is enough for coordinate descent to adopt an override that loses ten points.

`tuned_2p.json` and `tuned_3p.json` advertise `held_up=True` and +10.8 at 2p.
Evaluated properly: the income cut both files agree on is worth **nothing**
(-0.17 at 2p, +0.17 at 3p), adopting either wholesale would have undone the
confirmed beer fix, and what looked like their gain was mostly this same
override being reverted. Two runs of a biased tuner agreeing is not evidence.

**Rule: prefer a DEFAULTS value over a profile entry unless the split has been
measured seat-balanced.**

### Open, in the order I would take them

1. Re-tune the full vector through the fixed tuner. Note it will be far stingier
   -- a 2 sigma gate on a paired difference is a much higher bar than the old
   "beat one baseline noise estimate", so expect most weights kept. Budget
   overnight: the duel needs roughly double the games for the same precision.
2. Re-measure the planner: its +25 was against the pre-fix evaluation, and the
   heuristic it is compared against is far stronger now.
3. More agent playtests. Highest measured yield for rules bugs, and a poll costs
   41% fewer tokens since the move list was collapsed.
4. `docs/options-swot.md` weighs the larger bets, including the port.

**Do not** chase the action ledger's double-rail gap (8.73 VP an action against
4.08 for a single). It is a selection effect: when a double is on offer the bot
already takes it 82% of the time, and only 36 of 338 rail singles had one
available. The gate is beer (41.9% of the misses) and cash (35.5%), which is
what `beer_rail` and `loan_bias` address. Measured, dead end, recorded.

### The biased tuner's other picks were audited, and they are fine

`unflipped` was the exception, not the rule. The last re-tune before the harness
was fixed (`c7bd27e`, which reported +11.8 and delivered +4) set exactly three
weights, and reverting each of them seat-balanced over three blocks at 4p and 2p
costs points or does nothing:

| reverted | 4p | 2p |
| --- | --- | --- |
| `income` 0.08438 -> 0.1125 | -0.30 +- 0.38 | -0.05 +- 0.79 |
| `canal_double` 0.5 -> 0.0 | **-2.25 +- 0.38** | **-4.99 +- 0.71** |
| `commit` 1 -> -1 | +0.19 +- 0.38 | -1.46 +- 0.73 |

So the vector does not need distrusting wholesale, `canal_double` is strongly
load-bearing at both counts having never been measured alone, and `commit` earns
its place at 2p while being neutral at 4p.

`income` is the third time a resource's measured windfall value has failed to
transfer to its weight -- after `money` scoring -21.5 when priced at what a grant
of it is worth, and the `income_curve` exponent. **What a resource is worth as a
windfall is not the rate you should trade for it.**

### The biggest single gain: a penalty that fired an era too late

`blocked` charges for an industry locked out by a stranded canal-only tile, but
it only ever fired `if state.era is Era.RAIL`. By then the only answer left is a
Rail-Era develop, and those measure worth nothing -- so the bot reliably acted an
era late: 0.25 brewery develops in canal against 0.54 in rail, 44% of seats
entering the Rail Era with brewery blocked, 0.42 barrels a seat destroyed on
level-1 breweries the wipe removes, and 86% of seats starting the Rail Era with
no beer at all.

`blocked_lookahead` = 1.0 charges a fraction of the same penalty DURING the Canal
Era, ramping to full weight at the boundary:

| | 4p | 3p | 2p |
| --- | --- | --- | --- |
| gain | **+7.87 +- 0.38** | **+10.16 +- 0.51** | **+16.28 +- 1.00** |

Eight of the eleven level-1 tiles are canal-only and developable, so this is not
only about breweries.

Its ceiling was known before the weight existed: FORCING one Canal-Era brewery
develop measures **+7.73 +- 0.61** over four blocks and 2,400 games, and the
weight recovers +7.87 of it. The evaluation could express this the whole time --
the penalty just fired in the era after the one where the answer had to be
played. That also explains the mat audit's "correctly sized but nearly inert":
correctly sized, and firing after the decision it should have shaped.

**Found because a player described how they play** -- develop the level-1
breweries away before the boundary so the industry stays open and the beer
survives. Three of their observations converged on the same action before anyone
looked at the code.

### Agent playtests: the engine is sound, strength is unmeasured

Two agents played full 4p games on recorded seeds (7301, 8842) and found **no
rules bugs**. One verified the recently-changed double-rail generation by hand --
costs correct to the pound, and beer reachability correctly evaluated against the
POST-action network, so a brewery reachable only because the second link is being
placed is properly allowed.

They scored 74 and 81 against bots at 101-123, but **that is not a strength
result**: both were briefed to hunt bugs rather than win, and one was told to
steer toward double rails and selling regardless of whether those were best. An
agent playing to expose the move generator is not an agent playing to score.
The earlier cohort that scored 130/119/116 was also coached from
`docs/expert-strategy.md`, so no clean comparison exists yet in either direction.

Both independently misread the interface in the same two ways, now fixed in
`tools/play.py`: `p.vp` shows only BANKED points (every seat reads 0 mid-canal
while one is 19 ahead), and a forced tile liquidation on an income shortfall was
printed nowhere at all.

### A single positive block is not a lead

Three separate ideas -- `scout_bias`, `income_curve`, `off_plan_bias` -- each
measured well on their first block and pooled to nothing over four or five:
+0.36, +0.31 +- 0.30, -0.10 +- 0.33. At 240 games the standard error is about
+-0.9, so a first reading of +1.3 is simply what noise looks like. Measure on
three blocks from the start; it costs no more than measuring once and then
chasing the result.

The corollary bit twice in one day: `liquidity_scale` measured +2.48 alone and
-0.82 once `loan_bias` existed, because both price the same thing; and
`mat_potential` measured +2.66, then -1.44, then +6.57 at 2p. **A weight is a
number conditional on the rest of the vector and on the player count.**

### Re-tuning once the vector was complete: +4, not the +11.8 it claimed

The 174-candidate re-tune that found nothing ran before `link_flip_canal` and
`link_flip_rail` existed. Run again with them in the vector -- 194 candidates,
60 games each, two passes -- it moved three weights and reported **+11.8 on its
validation block**.

Measured independently, head to head against the previous defaults, 200 games a
block:

| block | delta |
| --- | --- |
| validation 20000+ (the tuner's own) | **+3.46** |
| report 0+ (unseen by the tuner) | **+4.28** |

**Real, replicated, and about a third of the claim.** Shipped. The lesson is not
that the tuner lies -- it validates on a block it did not tune on, which is why
it caught earlier failures -- but that its own validation still flatters, because
the *choice* of what to validate was made using nearby data. Re-measure a tuned
vector in a separate harness before believing the size.

What it changed, and why it matters:

| weight | was | now |
| --- | --- | --- |
| `canal_double` | 0.0 | **0.5** |
| `commit` | -1 (off) | **1** (manufacturer) |
| `income` | 0.1125 | 0.08438 |

**Both restored terms measured at or below zero on their own** -- `canal_double`
at -3.36, `commit` at ~0. In a vector that now pays for the link icons a level-2
tile switches on, they earn their place. A term can be worthless alone and useful
in company, so a single-term sweep is weak evidence in either direction. That
cuts against how nine of this session's ten weight experiments were run.

The 4p mirror reads 111.19 against 112.29 before, which is the expected shape:
the gain is a relative edge and a mirror cannot see one.

### Why the bot never builds pottery: it cannot afford it

Five agents across three player counts reported that our bots never build a
pottery tile. Measured over 20 games and 80 seats: **0 built, 0 developed, and
all 80 pottery mats finish pristine at [1,1,1,1,1]**. The track is frozen shut,
because L1 has `can_develop = 0` -- you cannot develop past it, only build
through it -- so one build it will not make locks out an industry worth 41 VP in
an agent's game.

**The cause is cash, not valuation.** On a real position (canal round 2, seat
holding GBP19), the best pottery build ranks **50th of 51 candidates**. Decomposing
the 10.67 point gap by zeroing one weight at a time:

| term zeroed | gap closes by |
| --- | --- |
| `liquidity` | **6.15** |
| `mat_potential` | 2.62 |
| `merchant_access` | 2.40 |
| `income` | 1.80 |
| `unflipped` | *widens by 4.6 -- it favours pottery* |

Pottery L1 costs GBP18 plus an iron and the seat holds GBP19, so building empties
the purse, and `liquidity` is an exponential that treats broke as near-fatal. The
coal mine it takes instead costs **net GBP1**. Re-ranking the identical position
with more money settles it: **GBP19 -> rank 50, GBP45 -> rank 10, GBP60 -> rank 9.**

This links a symptom the yardstick has flagged from the beginning. The bot takes
**1.4 Canal-Era loans against an expert 4-6**, so it never rises much above GBP30
early, so the game's best tiles are permanently out of reach.

**Two fixes tried, both failed.** Pricing the tile better -- the `mat_potential`
correction -- measured **-0.79**, because it moves 2.62 of a 10.67 gap. And
crediting an available loan as liquidity, on the argument that GBP0 with a loan in
hand is one action from GBP30, fails in the opposite direction: the bot feels
liquid, **loans less** (13.6 -> 9.5 a game) and still builds no pottery. Even
removing `liquidity` entirely leaves a 4.5 point gap, so no single term is the
blocker.

The open question is therefore not "how should pottery be priced" but "how does
the bot end up with enough cash to build anything expensive" -- and forcing more
Canal-Era loans directly was already tried, and cost 25 VP.

### The one method that has produced gains

Ten changes to the evaluation have been measured this session. Nine were terms
reasoned out from a symptom -- canal double-scoring, a surviving coal mine,
capped merchant access, hand reach, raising `unflipped`, an endgame rival ramp
-- and every one landed at or below zero.

The one that worked came from a different method: **measure what a term is
actually paid, and compare it to what the bot thinks it is worth.** An agent
found link value correlated 0.11 with what links actually scored, because the
estimate counted only neighbours that had already flipped. Fixing the estimator
was worth +11 VP.

Before adding a term, ask whether its estimate can be checked against outcomes.
If it can, check it. If it cannot, the odds here are about one in ten.

### Two rules for anyone measuring here

**A mirror cannot see a symmetric change.** If it helps every seat, the mirror
mean does not move. Measure head to head.

**At 24 games an arm the smallest visible effect is 8.7 VP.** A 3 VP effect needs
about 200. Most changes worth having are invisible at small n.

## Goal

A bot that plays 4-player Brass: Birmingham as strongly as possible.

**The original 200+ VP target is not reachable at 4 players** -- see
`docs/research-landscape.md`. Actions are fixed at 31 per player in a 4p game,
and expert human play converts them at about 5 VP each, giving ~155. Reported 4p
winning scores average 140-150 and top out around 176-185. 200 VP would need
~6.5 VP/action, about 30% better than expert humans. At 2 players (39 actions)
200+ is normal for experienced players, and the engine and harness both support
`--players 2`.

**Measure progress in VP per action**, which is comparable across player counts
and encodes the real constraint:

| target | VP/action (4p) |
| --- | --- |
| current bot | ~2.0 |
| competent club player | ~3.2 |
| **expert human 4p** | **~5.0** |
| best reported 4p game | ~6.0 |

**Caveat that shapes the whole project:** a Brass score is not self-contained.
Breweries flip when *someone else* sells; coal and iron mines flip when
*someone else* consumes. Against passive opponents you burn your own actions
flipping your own tiles and your ceiling drops; against three strong opponents
you contend for the same slots, merchants and cheap coal. So "200+" is only
meaningful against a **named opponent pool**, and the eval harness must report a
score distribution, not a mean. Typical 4p winning scores are ~150–190, so this
target sits near the top of the human range.

## Decisions

| Question | Choice |
| --- | --- |
| Engine language | Python now; port the hot path to Rust/PyO3 once the rules are frozen |
| Scope | Self-play, plus eventually a live advisor (feed it a real game state, get a move) |
| Compute | CPU search first; RTX 4060 laptop (8GB) in reserve for a policy/value net |

Live *automation* of BoardGameArena is off the table — an advisor that takes a
state and returns a move avoids their terms entirely.

## Current state

Rules engine complete and stable: 204 tests pass, and 80 full 4-player games
(40 random, 40 greedy) run to completion with no failures.

- `brassbot/data/brass.json` — generated, canonical component data.
- `tools/extract_gamedata.js` — generates it from `tools/vendor/gameData.js`.
  **Edit the tool, never the JSON**, so provenance survives.
- `brassbot/gamedata.py` — typed loader, market price ladder, income track.
- `tests/test_gamedata.py` — 36 invariants. All passing.
- `docs/rules_reference_eog.txt` — the reference this engine was implemented
  against: complete rules text, though none of the per-tile numbers. **Not
  tracked** — the sheet states it may not be re-posted, so fetch your own copy
  from orderofgamers.com (Brass: Birmingham v1.2) if you need it.
- `brassbot/cards.py` — deck construction; wild cards are outside the deck.
- `brassbot/state.py` — `GameState`, `Player`, `Tile`, setup, cheap `clone()`.
- `brassbot/network.py` — the two connectivity notions and link distance.
- `brassbot/resources.py` — coal/iron/beer sourcing, plan enumeration, consumption.
- `brassbot/actions.py` — the seven action types.
- `brassbot/engine.py` — move generation, application, round/era flow, scoring.
- `brassbot/bots/` — `Bot` interface, the bots, and a spec parser so a bot can be
  named as `heuristic:income=0.3,debt=0.5` and shipped to worker processes as a
  plain string.
  - `random` — uniform over legal actions. The floor.
  - `greedy` — fixed action priorities, no board evaluation.
  - `heuristic` — 1-ply lookahead over a real position evaluation.
- `tools/tune.py` — coordinate descent over the heuristic weights, paired seeds,
  tuned on a seed block kept clear of the reporting seeds.
- `brassbot/evaluate.py` — the evaluation harness.
- `tools/evaluate.py` — matchup CLI.
- `tools/playout.py` — one game with a round-by-round trace, for debugging.

```bash
PYTHONPATH=. .venv/bin/python tools/evaluate.py greedy -o random -n 200 -w 8
PYTHONPATH=. .venv/bin/python tools/evaluate.py greedy --mirror -n 200 -w 8
PYTHONPATH=. .venv/bin/python tools/playout.py greedy -s 3
```

### Baseline numbers

Held-out seeds (0-79), 80 games each, seats rotated, per-format weights applied.

| fmt | pool | mean | SD | P10 | max | VP/action | win% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4p | mirror | 107.7 +- 0.8 | 13.8 | 92 | 164 | **3.47** | 25% |
| 4p | vs greedy | 106.8 +- 1.9 | 17.2 | 82 | 140 | 3.45 | 95% |
| 3p | mirror | 113.5 +- 1.2 | 18.5 | 94 | 153 | 3.24 | 33% |
| 3p | vs greedy | 105.9 +- 2.7 | 24.0 | 72 | 150 | 3.02 | 95% |
| 2p | mirror | **119.4 +- 1.3** | 16.9 | 99 | 158 | 3.06 | 50% |
| 2p | vs greedy | 114.9 +- 1.9 | 17.3 | 91 | 158 | 2.95 | 99% |

Industry commitment is shipped in these numbers (`HeuristicBot.DEFAULTS["commit"]`
= manufacturer). The mirror column barely moves and should not: commitment buys a
*relative* edge, and in a mirror every seat gets it -- the same reason the beer
fix left the mirror at exactly 107.0. It shows up head to head, where it was
measured: vs greedy at 4p goes 101.6 -> 104.6 and 91% -> 99% wins.

### A mirror cannot measure a symmetric change

The beer-preference fix below moved 39 of 40 games and left the 4p mirror mean at
**exactly 107.0**. That is not a null result, it is the wrong instrument: in a
mirror every seat gets the improvement, so an edge that is purely relative
cancels, and the subject's mean cannot move. Measuring it needs an asymmetric
arm -- the preference given to seat 0 only, against a control run that measures
what seat 0 is worth on its own (-0.52 VP, i.e. nothing).

Paired on 300 identical seeds, the fix is worth **+1.23 +- 0.46 VP (2.7 sigma)**.
Unpaired on 200 seeds the same effect read +1.38 +- ~1.2, which would not have
supported any claim. Pair the seeds.

Anything that changes a rule for all players at once needs this treatment.

Re-measured after two engine fixes found by agents playing full games (the
empty-network build exception, and choosing the discard instead of spending
hand[0]). Mirror play gained most -- 4p 98.2 -> 107.0, 3p 100.2 -> 113.3, 2p
104.9 -> 120.1 -- because both fixes help every seat at once. The vs-greedy
column moved far less: greedy was already losing, so a better subject mostly
converts margin it did not need.

Effect of per-format weights (mean, before -> after):

| fmt | mirror | vs greedy |
| --- | --- | --- |
| 2p | 88.8 -> **104.9** | 78.2 -> **105.9** |
| 3p | 102.1 -> 100.2 | 90.3 -> **101.0** |
| 4p | 98.6 -> 98.2 | 99.4 -> 101.3 |

(Measured before the two engine fixes above, and kept at those numbers: this
table records what the weights were worth, not where the bot now stands.)

2p gained most, which is what the tuner predicted (+15.5 on validation) and what
the format called for: **2p wanted `unflipped` cut by half and `sell_ready`
raised by half.** With only one opponent, far less of your coal and beer is
drained on somebody else's turn, so tiles do not flip by themselves -- you have
to go and sell them. That is the interaction effect showing up as a weight.

The 2p bust is also gone: P10 was **0** against greedy, and is now 77.

**4p was rejected by its own validation at +0.0**, and a follow-up investigation
established why. Do not redo this:

- 4p had already been tuned four times; 2p and 3p never had. The 2p/3p gains
  were catching up to where 4p already was, not finding anything new.
- A sensitivity sweep (each weight at x0.5 and x2.0) *appeared* to find six
  improvements, the best worth +6.7. **All of them were noise.** Re-run at 120
  games on the same seeds, every sign flipped: liquidity +6.7 -> -2.2,
  links_held +5.6 -> -4.1, income +4.5 -> -2.6.
- The one genuinely interesting lead -- all four best weights changed *together*,
  which coordinate descent cannot find because it moves one weight at a time --
  ran +7.3 and +5.5 on two blocks and -0.2 and +1.1 on two others. On the
  reporting seeds at 150 games it came out at **exactly -0.0 on both pools**.

So 4p sits on a real optimum, not a plateau the evaluation is blind to:
`unflipped` at half strength costs **-9.0**, so the evaluation is strongly
sensitive to the weight that matters most. It is on a summit, not a flat.

**Method warning.** Seed-block variance at 4p is large enough that a 40-game
comparison manufactures +-7 VP effects out of nothing, and the stderr of the
*baseline mean* is the wrong noise floor for a paired difference. Require >=150
games and agreement across at least two blocks before believing any weight
result.

| fmt | profile |
| --- | --- |
| 2p | `unflipped` 0.375 -> 0.188, `sell_ready` 0.319 -> 0.478 |
| 3p | `unflipped` 0.375 -> 0.281 |
| 4p | defaults (tuning rejected) |

Note the pattern: the fewer the opponents, the less an unflipped tile is worth.

Trajectory of the 4p mirror through this work:

| stage | mean | VP/action |
| --- | --- | --- |
| with the fabricated money-VP rule (not comparable) | 68.6 | 2.21 |
| after correcting scoring | 43.6 | 1.41 |
| + sell-chain terms, re-tune | 93.1 | 3.00 |
| + money horizon, mat potential, era boundary | 98.2 | 3.17 |
| + empty-network build rule, chosen discard | **107.0** | **3.45** |

### Behaviour against expert benchmarks

| metric | before | now | expert 4p |
| --- | --- | --- | --- |
| loans per game | 9.6 | **2.8** | 4-6 canal, 0-3 rail |
| final income | -7.7 | **+13.7** | positive |
| rail links | 5.0 | **8.0** | 7-10 |
| canal links | 3.2 | 4.7 | 2-4 |
| tiles sold | 0.6 | **5.0** | - |
| tiles flipped | 5.4 | **11.6** | 8-12 |
| VP split industry:link | - | **47:53** | 65:35 to 40:60 |
| pottery level reached | 0.1 | 1.1 | - (not re-measured) |
| cash left at game end | ~164 | **16** | 0 (worth nothing) |

Rail links, tiles flipped and the industry:link split are inside expert bands.
Cash left has largely closed -- **16 pounds** at the final whistle against the
~164 we started this work with, though it is still above the expert 0-10.

Loans moved the *wrong* way, and it is worth flagging rather than burying: 4.8 ->
**2.8** a game, against an expert 4-6 in the Canal Era alone. The bot is
borrowing less exactly where the yardstick says it should borrow more, which is
the same Canal-Era under-investment the band table diagnoses. Note that acting on
that finding directly has already been tried once and failed (see below) -- the
diagnosis is sound, the obvious fix is not.

Canal links also still run above the expert 2-4 (the rule of thumb is to build
one only when it scores 6+ VP or is strictly needed).

### Distance to a realistic target

**200+ is not reachable at 4 players** and this is now settled with tournament
data -- see `docs/research-landscape.md`. Fifteen verified tournament games (WBC
2024/2025, Prezcon 2023, WSBG 2022/2025) run **142-184, median 158, none at or
above 200**.

| target | VP/action | where we are |
| --- | --- | --- |
| club average | 3.2 | **we are here (3.45 mirror, 3.28 vs greedy)** |
| strong 4p winner | 4.8-5.2 | +60 VP away |
| tournament ceiling | 5.9 | - |

Best single game so far at 4p: **141** (mirror), **140** (vs greedy); across all
formats **170** (2p mirror) -- inside the range of real tournament winning
scores, but not yet the average.

## Link scoring — settled

End-of-era link scoring counts **flipped tiles only**, plus **2 icons from every
merchant location**. Resolved by reading the printed components, not the rules
text (the icon is a symbol-font glyph that no text extraction preserves). Full
evidence and reasoning in `docs/link-scoring.md`, with the images it cites in
`docs/evidence/`.

Encoded as `LINK_VP_COUNTS_UNFLIPPED_TILES = False` and `MERCHANT_LINK_ICONS`
in `engine.py`, pinned by three tests.

The strategic consequence the bot must exploit: **flipping pays twice** — the
tile's own VP, plus switching on the link icons that every adjacent link counts.
A link touching a merchant is worth a guaranteed 2 VP whatever else happens.

## Evaluation terms, and the pattern behind them

Three of the evaluation's terms exist because the same failure kept recurring:
**Brass pays out at the end of a chain, and a one-step evaluation prices only the
first link of it.** Each fix makes a deferred payoff visible.

| term | the chain it makes visible |
| --- | --- |
| `unflipped` | a built tile pays nothing until it flips |
| `sell_ready`, `merchant_access` | build -> connect to a merchant -> get beer -> sell |
| `mat_potential` | develop -> unlock a higher tile -> build it -> flip it |
| `money_horizon` | cash is only worth what it buys before the game ends |

Expect the next plateau to be the same shape. When the bot looks irrational, ask
which chain it cannot see, rather than which weight is wrong.

## The heuristic bot

Applies each legal action to a clone and scores the resulting position. The
evaluation is built around what actually banks points:

- **Nothing scores until it flips.** Unflipped tiles get partial credit as a
  promise, and that promise must include the tile's *income*, not just its VP.
  Valuing only the VP made every build look like a waste of money and the bot
  simply hoarded — the first version scored 17 against greedy's 61.
- **Income compounds**, so it is weighted by rounds remaining rather than flat.
- **Being broke is not just "less money."** At zero cash almost every action
  disappears from the list; the second failure mode was a bot that refused to
  borrow, ran dry by canal round 3, and passed for the rest of the game. Money
  therefore has a saturating liquidity term, steep near zero and flat once
  solvent.
- **Debt is not symmetric with income.** Unpayable negative income sells your
  tiles at half cost and then costs a VP per pound, so it is charged on top of
  the linear income term.
- **Opponents count.** Draining a rival's mine flips *their* tile and pays
  *them* income, so the value is net of the strongest opponent's position.

Weights live in `HeuristicBot.DEFAULTS` and are tuned by playing, not by
argument — hand-picking them went in circles, with each fix trading one failure
mode for another.

### Known weaknesses

- **1-ply is myopic about loans.** A loan's cost is immediate and certain; its
  benefit only appears once the money is spent. No shallow search sees that.
- **No plan.** It cannot aim at pottery level 5, or hold a merchant for a later
  sale. Every decision is local.
- **It does not model the deck**, its own or anyone's, so it never plays around
  what it is likely to draw.

## Measuring against expert play, not against ourselves

Every other number here is relative to our own bots: the heuristic was tuned
against greedy, search is measured against the heuristic. That ladder answers
"better than our last bot", which is a different question from "good at Brass".

`brassbot/yardstick.py` scores play against a profile of expert *behaviour* drawn
from recorded tournament games, so it references no bot we wrote.

```bash
PYTHONPATH=. .venv/bin/python tools/yardstick.py heuristic -n 40 -w 4 --sources
```

Heuristic bot, 4p mirror -- **4 of 11 bands met**:

Re-measured after the four engine fixes, 200 games:

| dimension | ours | expert | |
| --- | --- | --- | --- |
| VP per action | 3.51 | 4.8-5.2 | LOW |
| **VP entering the Rail Era** | **38.3** | **70-80** | **LOW** |
| **loans in the Canal Era** | **1.4** | **4-6** | **LOW** |
| **tiles developed in the Rail Era** | **2.7** | **0** | **HIGH** |
| tiles developed | 4.6 | 2-4 | HIGH |
| canal links built | 4.7 | 2-4 | HIGH |
| money left at the end | 15.7 | 0-10 | HIGH |
| rail links built | 8.0 | 7-10 | ok |
| tiles flipped | 11.6 | 8-12 | ok |
| loans in the Rail Era | 1.4 | 0-3 | ok |
| share of VP from industry | 0.47 | 0.40-0.65 | ok |

**These four failures are one mistake.** The bot under-invests in the Canal Era:
it takes 1.4 loans where experts take 4-6, so it has too little money, so it
enters the Rail Era on **38.3 VP against an expert 70-80** -- and then spends
scarce Rail Era actions developing (2.7) that should have been done in canal, at
roughly 5 VP of opportunity cost each.

The engine fixes moved every number in the right direction (VP/action 3.07 ->
3.51, VP entering rail 29.5 -> 38.3, tiles flipped 9.8 -> 11.6) without closing a
single band. The diagnosis is unchanged and the gap is structural.

The self-play ladder could never surface this, because every bot we have makes
the same mistake equally. It took an external reference to see it.

### The yardstick diagnoses; do not optimise against it

Acting on the Canal Era finding was tried directly and **it failed usefully.**

The mechanism was real: income is credited a compounding multiplier
(`3 * rounds * income` for a loan's cost) while money was priced flat, so loans
looked bad early and good late -- the inverse of expert play. Adding a
compounding term to money (`money_compounding`) fixes that arithmetic and moves
the bot straight onto the expert loan band:

| `money_compounding` | canal loans | VP entering rail | bands met | mean VP |
| --- | --- | --- | --- | --- |
| 0.0 | 1.44 | 30.8 | 4/11 | **94.6** |
| 0.02 | **4.44** (in band) | 12.7 | **7/11** | **70.0** |
| 0.04 | 4.62 (in band) | 19.2 | 3/11 | 61.1 |

**Matching the expert profile cost 25 VP.** Every loan spends an action. Experts
can afford 4-6 of their 16 canal actions on borrowing because the remaining ones
convert at ~5 VP each; ours convert at ~3, so the same trade is simply bad for
us. Borrowing is a *symptom* of being able to use money well, not a cause of it.

The term is kept but defaults to 0.0, with the reasoning in the code, so it can
be revisited once action productivity rises -- at which point the trade should
flip.

**The lesson is Goodhart's, and it is now load-bearing here.** The yardstick is
the only external reference we have, which makes it tempting as an objective.
It is not one. A missed band is a question about the underlying capability, not
a target to hit. The real finding stands: our actions are worth ~3 VP where an
expert's are worth ~5, and no amount of cash fixes that.

**On the bands.** They come from a handful of recorded tournament games and
written expert guidance, cited per band (`--sources`) and collected in
`docs/research-landscape.md`. They are not a measured distribution -- none exists
publicly for this game. Outside a band is a question to investigate, not a
verdict.

## Price the flow, not the stock

The single most useful rule learned about this evaluation. Every term that priced
a *holding* made the bot hoard the thing and play worse; every term that priced
something *conditional on being spent* helped.

| term | shape | result |
| --- | --- | --- |
| `sell_ready` | conditional on a sale existing | worked |
| `flip_horizon` | decays as the chance to use it expires | worked |
| `money_horizon` | decays to zero at the whistle | worked |
| `mat_potential` | value of the next tile unlocked | worked |
| `money_compounding` | value per pound **held** | **-25 VP** |
| `beer_capacity`, uncapped | value per barrel **held** | **-22 VP** |
| `beer_capacity`, capped at tiles waiting | conditional again | no harm, +25% batching |

The beer pair is the cleanest demonstration: the same term with one `min()` added
is the difference between -22 VP and a small positive. Check the shape of a new
term against this table before spending an afternoon measuring it.

## The sell-batching problem needs search, not a weight

> **SUPERSEDED by measurement.** Batching is barely an opportunity: when a Sell
> is legal, the most tiles flippable in one action is 1.02 in canal and 1.18 in
> rail. There is almost nothing to batch, so this is not where the points are.


A Sell action can flip several tiles at once, but each needs its own beer.
Measured: **1.00 tiles per sell**, 2.5 tiles sellable on a turn, and **73% of
turns leave sellable tiles stranded**. Experts batch 2-3.

The capped `beer_capacity` term lifts batching to 1.15 and is worth +1.1 +-1.2 VP
-- real mechanism, unproven score. This is the first of the chain-pricing fixes
that did *not* produce a clear gain, and the reason looks structural: the payoff
sits five or more plies out (build a brewery, connect, brew, hold sellables, sell
several together). A one-ply evaluation can gesture at that chain but cannot plan
it.

**So this one is a search problem.** Which fits the rest of the picture: search
parameters are at a flat optimum, search budget still pays but is flattening, and
the evaluation has now been pushed to where its remaining errors need depth
rather than better weights.

## Income is not underpriced, and the tune block nearly said it was

Two agents playing full games reported that the strategy guide's "income is not
a goal" is wrong in this engine: a merchant-connected coal mine flips on build,
roughly pays for itself, and jumps income several spaces. That is true of the
*guide*. The question it raised for us was whether our evaluation shares the
guide's mistake and underprices income.

It does not. Swept head-to-head, one variant seat against three baseline seats
(a mirror cannot see a weight that only buys a relative edge):

| income | tune, seeds 10000+ | validation, seeds 20000+ |
| --- | --- | --- |
| 0.0 | +1.6 | -0.0 |
| 0.0563 | **+3.0** | **-1.1** |
| 0.075 | +1.2 | -1.4 |
| 0.09 | +0.5 | - |
| 0.1125 (shipped) | -1.0 control | +0.1 control |
| 0.17 | -4.2 | - |
| 0.225 | -6.4 | - |
| 0.3 | -15.8 | - |
| 0.45 | -42.6 | - |

Raising income is monotonically worse and steeply so. Lowering it looked like a
+3.0 VP win on the tune block and evaporated to -1.1 on held-out seeds -- which
is the whole reason the two blocks exist. Shipped weight stands.

The behaviour numbers say the same thing: the bot ends on **+13.7 income** with
**2.3 coal mines** standing, against the agent's income 16 on 4 mines. It already
plays the coal-for-income line; it was never ignoring it.

Worth noting what the agents were actually right about. Their claim was about the
guide, not about us, and the distinction matters -- "an expert source is wrong"
does not imply "we copied the error".

## Unused merchant locations are still merchant spaces -- settled, and fixed

Two agents independently reported that `warrington` (2p) and `nottingham` (2-3p)
were being dropped as merchant *spaces* rather than merely as merchant *tiles*.
`state.merchants` is filtered by `min_players`, and both `is_connected_to_merchant`
and `link_icons_at` read it, so at low player counts a coal mine in the north-east
could not reach the coal market and `derby-nottingham` scored 0 instead of 2.

Settled against the rulebook, which is explicit on both halves:

- a coal mine sells when **"connected to any Merchant space (even those without
  Merchant tiles)"**, and the coal-purchase icons are printed on "the Warrington,
  Shrewsbury, Nottingham, Gloucester, and Oxford Merchants";
- `docs/link-scoring.md`, settled earlier from photographs of the components,
  already recorded that every merchant location shows 2 link icons permanently,
  per *location* and not per slot, with the pip clusters marking only which slots
  take a tile at which player count.

So the answer was partly already in this repo. `is_connected_to_merchant` now
searches from `data.merchants` (all five locations) and `link_icons_at` keys on
the same. Selling *goods* still requires a real merchant tile and is unchanged.

**Its own docstring had been right all along** and the implementation had been
quietly winning the disagreement. Worth remembering when a comment and the code
it sits on disagree: that is a bug report, not a stale comment.

Effect on our own numbers is small -- 2p mirror 119.6 -> 119.4, 3p 113.7 -> 113.5,
both inside noise -- because the fix is symmetric and our bot rarely plays the
north-east. It matters for anyone who does.

## Choices the engine still makes for you

Four agents playing 2p and 3p converged on the same class of complaint, and it is
worth listing in one place because none of these is a rules *error* -- each is a
legal move the generator never offers, which is how the beer bug and the sell-cap
bug both hid.

| choice | who makes it now | cost seen in play |
| --- | --- | --- |
| which card to discard for Loan / Network / Develop / Sell / Pass | **the player, in `tools/play.py`; still `_expendability` for the bots** | four agents lost the card their plan needed; see below |
| which 3 cards to Scout | 3 sliding windows of 56 possible triples | all three offered options discarded the card the plan needed |
| which industry Gloucester's develop bonus clears | highest-VP next tile (was enum order, i.e. always coal) | removed one of two identical coal L2s, unlocking nothing |
| whether to take merchant beer | always taken when available | rulebook says *may*; sometimes you want your own brewery drained so it flips |
| which second link a double rail reaches | pairs built from lines reachable *before* the action | refused `(burton-stone, stone-uttoxeter)`, legal in the real game because the first link makes the second coal-reachable |

### The discard choice is now offered, and the bot cannot use it

Four agents reported losing the exact card their plan needed, so `legal_actions`
now emits a variant per discardable card for Loan, Network, Develop, Sell and
Pass. `MAX_DISCARD_VARIANTS` controls how many; `tools/play.py` sets it to 3.

**For the bots it is left at 1, because they are blind to it.** The evaluation
ships with `wild_card` and `hand_breadth` at 0, so it never reads the hand: the
two loan variants of a real position both score **8.733942**. Offering the choice
costs 40% of runtime (200 games, 29s -> 41s) and changes not one game -- 110.70
+- 0.53 either way, identical to the decimal.

That identity is also how the first attempt at this measurement was caught. It
set the constant in the parent process, where it never reached the pool workers,
so both arms ran the same configuration -- and the giveaway was the two arms
agreeing to two decimals. Had they differed by noise it would have been reported
as a real null. Vary anything that is not a function argument by building two
trees, not by assigning to a module.

The finding underneath: **a legal choice is worth nothing to a bot whose
evaluation cannot see what it is choosing between.** Hand-aware terms are the
prerequisite, not more branching.

All are documented branching-factor caps rather than oversights, and each costs
search time to lift. But the pattern to remember is that **a behaviour number is
not evidence about the bot until you have checked the bot was offered the
alternative** -- rule 8's "fails" verdict was partly the sell cap, and rule 7's
was entirely the beer ordering.

## The Canal-Era double, and why crediting it at the build does nothing

The largest leak an agent measured: **26 of 39 canal builds (67%) are level 1,
mean level 1.44**, banking 14 VP a game that the era wipe then throws in the box.
A level 2+ tile flipped in the Canal Era survives and scores AGAIN at the Rail
Era's scoring, so those actions spent on level-2 tiles would bank roughly 37.

The doubling was only ever applied to a tile that had *already* flipped, so it
was never a reason to build the level-2 tile. Crediting it at build time moved
the mean canal build level from **1.44 to 1.46** -- nothing.

**Because a Build always places `lowest_level`.** You cannot build a level-2 tile
while a level-1 sits on top of that mat; developing the level-1 away is the only
route to it. So the credit has to go on the *develop*, not the build. Moving it
there moved the build level to **1.85**, which is the mechanism working.

It still does not pay at 4p. Over 200 games an arm:

| format | actions | baseline | with the credit | delta |
| --- | --- | --- | --- | --- |
| 4p | 31 | 110.17 | **106.81** | **-3.36 (2.6 sigma)** |
| 3p | 35 | 115.06 | 115.32 | +0.26 |
| 2p | 39 | 121.11 | 124.09 | +2.98 (1.6 sigma) |

The split follows the action budget exactly: developing costs actions and iron,
2p has 39 actions to spend and 4p has 31. Kept as a weight, `canal_double`, at
0 -- the 2p gain is 1.6 sigma, which is not enough to ship a profile override on,
but it is the most promising per-format lead we have.

**The general lesson is about where a term can act.** Valuing an outcome the bot
has no legal route to reach changes nothing; the credit has to land on the action
that unlocks the route. That is worth checking before pricing anything else the
bot "should" prefer.

## Two more terms that lose, and what they teach

Both suggested to attack real leaks, both measured over 200 games an arm, both
kept as weights at 0 rather than deleted.

| term | idea | 4p mirror |
| --- | --- | --- |
| baseline | - | **110.70 +- 0.53** |
| `rail_bootstrap` | value a surviving level 2+ coal mine as the Canal Era closes | 109.19 (-1.5) |
| `hand_reach` | value network towns your industry cards could build in | 101.72 (-9.0) |
| `merchant_access_cap` | cap merchant access at the tiles actually waiting to sell | **97.53 (-13.2)** |

### And it is not because the other weights were fitted without them

The obvious defence of these terms is that `DEFAULTS` was tuned as a *set*, so
every weight's value compensates for what the others miss -- `merchant_access` is
2.4 partly because nothing else credits connectivity. Add a term that also
credits connectivity and the bot is paid twice, over-invests, and loses. On that
account each term above was tested unfairly: added, with the other twenty held
fixed.

So `hand_reach`, the best-argued of them, was given the fair test. Seeded at 0.3
(coordinate descent scales multiplicatively and cannot move a weight off zero)
and the **whole vector re-tuned around it**, 174 candidates over 26 minutes on
the tuning block, validated on a third block:

| | |
| --- | --- |
| best on tuning seeds | 118.8 |
| validation, starting weights | 108.0 |
| validation, re-tuned weights | 108.9 (+0.8, noise +-2.4) |

**Not an improvement, and the tuner never raised `hand_reach` above the 0.3 it
was seeded with.** Free to re-balance everything around the new term, it found no
configuration that uses it.

The equilibrium defence is therefore wrong, and that is worth knowing: these
terms do not fail because of how they were tested. The evaluation is at a flat
optimum and 174 candidates could not find a way out of it.

`hand_reach` was the most carefully argued of the three and lost monotonically at
every weight. It was the only term in this evaluation ever to read the hand --
`wild_card` and `hand_breadth` both ship at 0, which is why offering a choice of
discard changed not one game in 200. Paying for *reach* turns out to buy links
into towns you might build in, and the actions go on connections that never
convert. Perception was not the missing piece.

**`rail_bootstrap`** attacks a real blindness: every link is removed at the era
boundary, so nothing is connected, so no coal is reachable, and an agent opened
the Rail Era with no legal rail link at all while every Birmingham link went in
three rounds. But it prices a **stock**, and this codebase has now lost points to
that five separate times. The diagnosis stands; pricing a holding is not the fix.

**`merchant_access_cap`** is the more interesting failure. Capping access by what
is waiting to sell looks like exactly the fix that made `beer_capacity` work --
and it costs 13 VP, because the two are not the same shape. **You need the
merchant connection BEFORE the tile that uses it.** Crediting access only once a
tile is waiting inverts the causality and re-opens the trap in
`docs/diagnosis.md`: with no credit for building toward a sale, the bot never
starts the chain, Sell never becomes legal, and money becomes the cheapest VP.
The flatness is deliberate.

The distinction to carry forward: **cap a term when it prices something you
already hold; never when it prices the prerequisite for something you do not.**
`beer_capacity` prices barrels you have. `merchant_access` prices a road to a
sale you have not built yet.

## The pottery gap: measured, explained, and NOT recoverable by valuation

> **RESOLVED.** The cause is `mat_potential`: building pottery L1 is charged for
> the 1 VP filler tile it uncovers, so a 10 VP build prices at 0.25 x 9 = 2.25
> against it. An agent built the fix and measured it over 300 paired games --
> pottery builds rose 0.26 -> 1.05 and the score moved **-0.79 +- 0.65**. The
> mechanism fires and the points are not there. Agents gain from pottery because
> they sequence a sale around it; the bot cannot.


Four independent agents, across all three player counts, reported the same
thing without being asked: **our bots never build pottery.** One won 129-116
against the planner taking **41 of its 129 points from three pottery builds**;
another took 21 VP; a third watched a bot spend Stoke's contested iron/pottery
slot on a 5 VP iron works.

It is not availability, and it is not the commitment filter, which is now off:

| | over 6 games |
| --- | --- |
| decisions | 744 |
| decisions where a pottery build was legal | **317 (43%)** |
| pottery builds actually made | **5** |
| median rank of the best pottery build among all candidates | **#36** |

Pottery is offered constantly and ranked into oblivion. It is the highest VP per
tile in the game -- L1 10, L3 11, L5 20 -- and the only level-1 tile that can be
built in the Rail Era, where no wipe can take it.

**One promising explanation was tested and is wrong.** The two weights that
price a sellable tile are inverted at 4p and only at 4p:

| format | `unflipped` (cannot sell yet) | `sell_ready` (can sell now) |
| --- | --- | --- |
| 2p | 0.1875 | 0.478 |
| 3p | 0.2812 | 0.3187 |
| **4p** | **0.375** | **0.3187** |

The comment says a sellable tile "is worth almost nothing until it can actually
be sold, and nearly its full value once it can", and at 4p it is worth *less*
once it can. Pottery is the tile whose entire value is being sellable, so this
looked like the cause. It is not: sweeping `sell_ready` gives 110.13 at 0.45,
111.39 at 0.6 (+0.69, 0.9 sigma) and 107.99 at 0.8. No effect worth having.

So the gap is real, large, independently observed four times, and **its cause is
still unknown**. That makes it the best-evidenced open question in this document.
Candidates not yet tested: pottery's cost (GBP17 for L1, the most expensive
opening tile), its iron requirement, or that its VP arrives only through a Sell
that the one-ply evaluation cannot see two actions ahead.

## Delta evaluation, and what it actually bought

The evaluation cloned the state and valued all four seats for every candidate
move. Three of those four are opponents, and our own move usually cannot change
what any of them is worth -- so their value is computed once per decision and
carried over whenever the shared state they read is unchanged.

| | before | after |
| --- | --- | --- |
| heuristic, full games | 1.35 games/s | **1.70 games/s** |
| MCTS prior (100 iters) | 8.70 s | **7.53 s** |
| fast path taken | - | **51% of candidates** |

Play is bit-identical over 30 full games, checked against the previous commit
rather than assumed. Three separate changes:

1. **`clone()` stopped seeding a generator it immediately overwrites.**
   `random.Random()` seeds from OS entropy and the next line called `setstate`.
   6.4x faster to construct, and clone is on the hot path. 3% of total runtime.
2. **Merchant reachability is computed once per decision.** It is a search over
   the link graph, only a Network action changes it, and it was being redone for
   every candidate -- in the heuristic's `choose` and again in the MCTS prior,
   where it is paid at every node of the tree.
3. **Opponent values are reused** when `shared_signature` agrees.

### The signature has to name things, not count them

The first version counted flipped tiles, on the reasoning that tiles never
unflip, so an unchanged count means nothing flipped. That is false:
**overbuilding replaces a flipped tile with an unflipped one.** A build that
overbuilt a flipped tile while its coal draw flipped another left the count at 8
on both sides. Every rival holding a link into that town lost icons unseen --
3 VP to one of them -- and one game in thirty played differently.

Counts can cancel; identities cannot. Pinned by
`test_reused_rival_values_equal_a_full_recomputation`, which carries seed 25
because that is the game that caught it.

### It applies to half the candidates, not 83%

An earlier estimate in this project put applicability at 83%. Measured, it is
**51%**, and the first honest implementation only reached 30% -- the signature
included our own tiles, so every Build invalidated it. An opponent reads our
tiles only through `link_icons_at`, which ignores unflipped ones, so our own
unflipped tiles were narrowed out of the signature.

The remaining 49% are candidates that genuinely change what an opponent is
worth: draining a barrel or a coal cube out of their tile, flipping anything,
placing a link, or ending the round.

## Industry commitment: real, but worth 4 VP and not 40

Rule 6 of the expert guide -- "never mix main industries, you end up mid-level in
several and score half" -- is the failure our own numbers describe best: 4.52
industries touched, 4.2 VP per build against an expert 8-10. Before designing a
planning mechanism for it, `brassbot/bots/commit.py` measures whether commitment
by itself scores better at all. It is the crudest possible version: strike every
build of a main industry other than the chosen one off the list of legal moves.

4p, vs three heuristics, held-out seeds 20000+, 300 games each:

| arm | mean | win% | vs control |
| --- | --- | --- | --- |
| no commitment (control) | 106.25 +- 1.08 | 27% | - |
| **manufacturer only** | **109.90 +- 0.97** | **32%** | **+3.65 +- 1.46 (2.5 sigma)** |
| adaptive choice | 107.05 +- 1.00 | 28% | +0.80 +- 1.48 (0.5 sigma) |

At 80 games the other two fixed choices were clearly worse: cotton 103.7, pottery
98.1, against a 107.9 control. The spread between industries is far larger than
the benefit of committing at all.

**Withdrawn.** Re-measured after seventeen engine fixes, 200 games an arm on the
report seeds, commitment is worth nothing at any player count: 2p +0.77 (0.4
sigma), 3p -1.70, 4p -0.03, all for the *uncommitted* arm. It is now off.

Two lessons, and the second is the one that matters.

The engine fixes erased it. A +2.14 +- 0.85 effect measured on one engine did not
survive the engine changing underneath it, which is worth remembering before
shipping anything at 2.5 sigma.

And the measurement asked the wrong question. It tested each industry as a
*commitment*, where pottery loses heavily -- and then shipped a hard filter that
also bans pottery *opportunistically*. Three agents at three player counts
independently found pottery the best VP per action on the board (L1 is 10 VP for
one build, L3 is 11 scored twice, L5 is 20) and each took 21-41 VP from it
uncontested, because no bot of ours will build one. At 2p the filter is perverse:
the deck holds **zero** manufacturer industry cards and two pottery ones, so it
commits to the industry reachable only by location card and bans the one with its
own cards.

"Is X good to commit to" and "is X good to build" are different questions. A
filter answers only the first and enforces it against the second.

### Cotton losing is our bot, not our engine

The guide names cotton as the 2-player industry and in our engine cotton loses at
every count, 2p included. That is the kind of disagreement that has meant a rules
bug three times this month, so it was checked rather than explained away.

**The data is right.** Our mat holds cotton at L1x3, L2x2, L3x3, L4x3, and tile
costs check out against the components (cotton L1 GBP12 / 5 VP / 5 income, L4
GBP18 / 12 VP; pottery L5 GBP24 / 20 VP, rail only).

**The bot cannot climb the track.** A cotton-committed bot at 2p reaches an
average highest level of **2.02** on 2.92 tiles built, never arriving at L3 where
the payoff is: L1 and L2 score 5 VP each, L3 and L4 score 9 and 12.

### Correction: the track is cheap, and an agent climbed it

The paragraph that stood here said cotton's value is "back-loaded behind five
low-value builds", reading the guide's "cotton III needs five tiles cleared" as
five *actions*. **That arithmetic was wrong.** Develop removes **two tiles per
action**, so the L1/L2 row costs two or three actions, not five.

An agent playing 2p seed 502 did it: one L1 build, then both actions of Canal
round 5 on `DEVELOP cotton+cotton` twice, reaching L3 by action 9 of 39. It
finished on **150 VP against the bot's 132**, with cotton producing 74 of them at
**12.3 VP per cotton build** -- against the expert benchmark of 8-10 and our
bot's 4.2.

The decisive detail is one neither the guide nor this document had: **cotton L3
and L4 are canal-era legal**, so an L3 built and flipped in the Canal Era scores
9 twice. Two such tiles were 36 of that 150.

So the failure is not the action budget. It is that a 1-ply evaluator will not
pay a develop action whose return arrives two builds later -- a horizon problem,
not a cost problem. The conclusion that this needs a planner survives; the
reasoning given for it did not.

What actually taxes the cotton line at 2p is beer and merchant access: only two
merchant tiles ever accept cotton at 2p and both can land at one merchant, and
`decks."2".dual_cotton_manufacturer = 0` means there are **no cotton industry
cards at all** -- cotton is gated on nine location cards plus wilds.

### The commitment effect is about +2 VP, not +3.7

The arms were compared on the validation block (20000+), which is also where the
winning arm was chosen -- so the shipping decision was re-run on the report block
(0+), which had decided nothing.

| format | validation (20000+) | report (0+) |
| --- | --- | --- |
| 4p | +3.65 (2.5 sigma) | **+1.53 +- 1.35 (1.1 sigma)** |
| 3p | +4.04 (2.3 sigma) | **+2.71 +- 1.40 (1.9 sigma)** |
| 2p | +1.99 (0.9 sigma) | **+2.17 +- 1.64 (1.3 sigma)** |

The direction replicates in all three formats, but every magnitude shrank and
none is individually significant. Pooled across formats it is **+2.14 +- 0.85**,
about 2.5 sigma. Selecting the arm on one block and reading its size off the same
block overstated it by most of a factor of two -- the second time this session
that the split has caught exactly that.

Treat commitment as worth ~2 VP.

### Choosing the industry adaptively, three ways, all worse than a constant

| chooser | mean | vs control |
| --- | --- | --- |
| anchored on tiles already built | 107.05 +- 1.00 | +0.80 |
| merchant demand and cards, re-decided each turn | 106.22 +- 1.10 | -0.02 |
| merchant demand and cards, **latched at game start** | 108.34 +- 0.98 | +2.10 |
| **constant: always manufacturer** | **109.90 +- 0.97** | **+3.65** |

Two real lessons, in the order they were learned.

**Re-deciding every turn is not commitment, it is mixing with extra steps.** The
market-driven chooser picked manufacturer for 75% of its decisions, which should
have been worth about +2.7 VP, and scored +0.0. Only 14 of 60 games *opened* on
cotton, yet a quarter of all decisions were cotton -- it changed its mind partway
and finished mid-level in two industries, which is exactly the failure rule 6
describes. Latching the choice at the start is worth **+2.1 VP on its own**.

**The market is the wrong signal, even latched.** At 4p the set of merchant tiles
never varies -- two cotton, two manufacturer, one pottery, two wild, two blank --
so only their positions are dealt fresh, and position is not what makes an
industry good. What makes manufacturer the 3-4 player industry is the action
budget: both level-2 manufacturers need no coal, so they cost no link action
first, and the line costs one develop. That is a fixed property of tile costs, so
a per-game read cannot beat a constant, and the chooser's 23% cotton games are
simply losses.

The variability that *is* real is by format, not by deal: the guide names cotton
as the 2-player industry. So the right shape here is a per-format constant, like
the weight profiles -- untested at 2p and 3p.

## Sequencing was tested directly, and the test failed

> **SUPERSEDED.** The conclusion drawn from this and the sections near it -- that
> the evaluation is exhausted and the gap is sequencing -- was over-read. The
> sweeps behind it ran over a weight vector that did not contain the largest term
> in the evaluation, because the link term's coefficient was hardcoded. Weighting
> it was then worth +11 VP. See "Links are valued by what has already flipped".


`brassbot/bots/book.py` forces the expert's Canal Era plan and hands off to the
ordinary bot for the Rail Era, isolating sequencing from everything else.

| seat 0 | mean VP | VP entering rail | flipped in canal | links |
| --- | --- | --- | --- | --- |
| heuristic | 99.1 +- 1.0 | **32.7** | 3.33 | 12.4 |
| book | 93.9 +- 4.0 | **13.9** | 2.03 | 9.7 |
| expert | - | 70-80 | - | ~11 |

It made the diagnosed number worse, not better. The encoding is at fault, not
necessarily the strategy: a priority list fires its develops on the first legal
opportunity, burning two early actions for no VP and no income, and never builds
coal, so it cannot afford the level 2+ tiles the plan is built around. The
expert's own game interleaves -- loan, link, cheap iron for income, develop only
once iron is cheap or flipped.

**So the open question is now whether the strategy is wrong or my reading of it
is.** A hand-written script cannot separate those. The next test is to give
`docs/expert-strategy.md` to an agent and have it play through a text interface,
which checks the interpretation rather than the encoding.

## The hand is now in the model, but priced badly

The evaluation had **no reference to the hand at all** -- so a wild card was
worth zero, and Scout read as three cards gone (0), two wilds gained (0), one
action spent. A pure loss, and the bot scouted 0.20 times a game.

Move generation was also at fault: `legal_scouts` returned a single action that
always discarded the first three distinct cards in hand order, so the bot could
not choose what to give up. It now offers three variants, cheapest-first --
duplicates before singletons, cards for full towns before cards for open ones.
That part is kept.

Pricing the hand is unsolved. Measured:

| wild | breadth | mean VP | scouts/game |
| --- | --- | --- | --- |
| 0.0 | 0.0 | 98.6 +- 1.0 | 0.20 |
| 2.0 | 0.15 | 93.4 +- 1.3 | 3.60 |
| 1.0 | 0.15 | 100.5 +- 1.2 | 3.05 |

At 2.0 it farms wilds -- an action is worth ~3 VP and two wilds paid +4.0, so
Scout looped. Below the cost of an action the pathology stops, but nothing
clears the noise floor. Both weights default to 0.

**Counting cards is the wrong proxy.** What makes a hand good is what it lets you
do, which depends on scarcity.

### Card scarcity was tried, and it needs a different shape

`site_urgency` scored a claimed town by how many copies of its location card
exist. Measured: **99.1 at 0.0, 88.5 at 0.3, 89.5 at 0.8** -- about -10 VP.
Defaulted off.

Two lessons, one mechanical and one conceptual.

**Mechanical:** the first version scored the claim per *tile* rather than per
town, which paid the bot to pile tiles into the same contested town. It built
11.9 tiles instead of 10.8 and lost 11.3 VP. Only the Rail Era allows the
stacking, so the bug lived in exactly half the game. Counting once per town is
verified correct and still loses ~10 VP, so the accounting was not the problem.

**Conceptual, and the useful part:** this encodes *contested = more valuable*.
The real principle is *contested = more urgent*. A one-copy town like Nuneaton is
just as good to own -- you can take it later because nobody can race you there.
Value and urgency are different quantities, and a state evaluation naturally
expresses value.

**Urgency lives on sites you have NOT claimed.** The shape that might work is a
risk term over reachable-but-unbuilt sites: the more copies of a town's card
exist, the more likely a rival takes it before you act, so act there first. That
is a property of the board you do not yet own, which is the opposite side from
where this term sat.

### The original note, kept for the reasoning

Experts count the deck. A location card that appears **once per era** means the
site is uncontested and can wait; one with **three copies** means a rival may
hold one, so move first. Those counts are already in `brassbot/data/brass.json`
and completely unused.

This is also the right answer to "should the bot predict opponents' hands". The
MCTS *sampling* is already correct -- `determinize` redeals from the deck plus
opponents' hands, and public discards are already excluded because they sit in
each player's discard pile. What is missing is not inference, it is using the
known deck distribution to judge how contested a site is.

## Search cannot escape the evaluation, and play-outs do not rescue it

> **Still true about search, but do not read it as "the evaluation is finished".**
> The evaluation had an unweighted term worth +11 VP when fixed, found after this
> was written.


MCTS gains +9 VP over the heuristic while changing its strategy **not at all** --
same 4 of 11 profile bands, same tile levels, same 1.17 tiles per sell. Its prior
and its leaf value are the same function, so it can only ever prefer what the
evaluation already likes.

The obvious fix is an uncorrelated leaf signal: play the game out and use the
real final score. Tested at **equal iterations**, which separates signal quality
from compute:

| rollout | mean VP | win% | brewery lvl | tiles/sell | VP entering rail |
| --- | --- | --- | --- | --- | --- |
| 0.0 | 102.5 +- 4.1 | 50.0% | 1.75 | 1.11 | 35.6 |
| 0.3 | 95.8 +- 3.8 | 12.5% | 2.12 | 1.00 | 26.2 |

**That experiment was confounded and its conclusion has been withdrawn.** A code
review found that `_values` returned *either* an evaluator number (~15-35 on an
arbitrary utility scale) *or* a raw final score (~0-30, and near 0 for a weak
seat), and pushed both into the same accumulator and the same `Bounds`. Each leaf
therefore sampled a Bernoulli mixture of two distributions ~15-19 VP apart, so
two siblings of equal true value could differ by several VP purely from which
drew more play-outs -- and most-visited-child follows that. The result measured a
badly scaled estimator, not the value of an unbiased signal.

The clean A/B has since been run -- `rollout` 0.0 vs 1.0, one consistent
estimator per arm, equal iterations (40), 16 games each:

| rollout | mean VP | win% |
| --- | --- | --- |
| 0.0 | 105.4 +- 4.3 | 43.8% |
| 1.0 | 99.6 +- 4.3 | 25.0% |

Same direction as the confounded run, but **-5.8 against a +-6.1
difference-stderr is ~0.95 sigma -- not established.** There is no evidence
play-outs help; the point estimate is against them; n=16 cannot settle it.

**The cost argument is the one that actually decides it, and it needs no
statistics.** The evaluation arm reaches 115.6 VP at 1500 iterations. Matching
that with play-outs means 1500 x ~75 ms = **112 seconds per move**. A Rust port
typically buys 10-50x, landing at 2-11 s per move -- still unusable. Play-outs
would need ~100x before they are even in the conversation. So they are not a
route to escaping the evaluation's frame at any budget realistically reachable
from here.

That is a narrower claim than the one withdrawn above. It says nothing about
whether the Rust port is worthwhile for other reasons, only that *this* route
does not justify it.

**Do not repeat the mistake in the finding:** if two value sources are mixed at a
node, they must share a scale, or be blended deterministically, or be normalised
before backup. Mixing them per-sample injects variance that looks exactly like a
signal-quality result.

What remains is a **learned value function** trained on self-play outcomes: low
variance, and uncorrelated with hand-crafted blind spots by construction, which
is exactly the combination play-outs could not provide. That is a project of
weeks, not an afternoon, and it should be entered deliberately rather than drifted
into.

## Known simplifications

Deliberate, and each one is somewhere a stronger bot may later want a real choice:

- **Sell beer is resolved greedily** (merchant beer first, then any legal
  brewery) rather than being a searchable choice. Which brewery you drain is
  strategically real — it can hand an opponent income.
- **Shortfall tile sales are cheapest-first.** The rules make this a player
  choice.
- **Move generation is capped** — `MAX_SOURCING_VARIANTS`, `MAX_DOUBLE_RAIL`,
  `MAX_SELL_COMBOS` in `engine.py`. Raising them widens the action space.
- **Link tiles return to their owner** after era scoring. The rules do not say
  explicitly; with 14 per player the cap is near enough to never binding.

## Next up

### We have been comparing our table average against their winners

Reported tournament scores -- 142-184, median 158 -- are **winning** scores. Our
headline mirror number is the mean across **all four seats**, three of which lost.
Comparing them overstates the gap by about 30%.

| | 4p mirror, 200 games |
| --- | --- |
| all seats (the number quoted everywhere) | 110.7 |
| **winning seat only** | **125.2** (median 125, best **157**) |
| human tournament winners | 142-184, median 158 |

**So the gap to a median tournament win is ~33 VP, not ~47**, and our best mirror
game already reaches 157 against a tournament median of 158.

Both numbers are worth keeping and they answer different questions. The all-seats
mean is the right measure for "did this change help", because it is what a mirror
can detect. The winning-seat mean is the right measure for "how far from expert
play", because that is what the human data records. Quoting one against the other
is the mistake.

Caught by an agent auditing the benchmarks, in the last line it produced before
an API error killed it.

### Where the bot stands

> Superseded by the table in "Read this first", which is measured after the link
> fix. These figures predate it: 4p 107.7, 3p 113.5, 2p 119.4.

MCTS reaches ~119 at 4p. Human tournament play runs 142-184, median 158, and the
yardstick's 5.9 VP/action ceiling gives ~183 at 4p -- the two agree, which is the
best evidence we have that 5.9 is real. 200+ is a 2p target (39 actions x 5.9),
not a 4p one.

### Links are valued by what has already flipped, and that was the biggest leak

A link is paid at the END of an era, by which point almost everything standing
has flipped -- **96% of our tiles at rail scoring, 74% at canal**. But
`link_icons_at` counts only tiles flipped *already*, so the number a link is
chosen on barely predicts what it pays: **correlation 0.11 in the Rail Era**,
0.41 in the Canal.

Crediting an unflipped neighbour's `link_vp` at roughly its chance of flipping in
time (`link_flip_canal` 0.7, `link_flip_rail` 0.9) is worth, head to head against
the old evaluation:

| block | delta | win rate |
| --- | --- | --- |
| report 0+ | **+10.38** | 25% -> 50% |
| validation 20000+ | **+11.91** | 25% -> 53% |
| 4p mirror | 110.70 -> **112.29** | - |

Found by an agent, which measured +8.4 / +10.7 / +11.9 across three disjoint
blocks; the numbers above are an independent re-run. The weight curve is smooth
and single-peaked, the two eras contribute additively, and the shape it produces
is the one the expert game has: industry:link moves 47:53 to **39:61** against
the coached game's 43:57, and it reproduces "place coal where your own links
already are" without being told. Runtime cost is zero.

**This corrects the central conclusion recorded above it.** Six weight
experiments and a 174-candidate re-tune found nothing, and that was read as the
evaluation being at a flat optimum with the remaining gap in sequencing. But the
link term had **no weight at all** -- `value += link_icons_at(state, end)`, the
coefficient hardcoded to 1.0 -- so every one of those searches ran over a
21-weight vector that did not contain the largest term in the function. The
optimum was flat in the parameters that existed, not in the evaluation.

Two sequencing claims made here also failed measurement when an agent checked
them. **Sell batching is not an opportunity**: when a Sell is legal the maximum
tiles flippable in one action is 1.02 in canal and 1.18 in rail, so there is
almost nothing to batch. And **pottery is not free VP**: the `mat_potential`
cause was found (building pottery L1 is charged for the 1 VP filler tile it
uncovers) and the fix measured over 300 paired games -- pottery builds 0.26 ->
1.05, score **-0.79 +- 0.65**. The mechanism fires and the points are not there.

### What is settled, and will not be revisited without new evidence

Seven levers have been measured and closed. Each has numbers in this document.

| lever | verdict |
| --- | --- |
| more MCTS iterations | saturates by 300; 5x compute buys nothing |
| deeper search (narrow beam) | depth 10 plays *worse* than depth 4; breadth wins |
| evaluation weights | *see correction*: flat in the weights that existed, but the link term had none, and weighting it was worth +11 |
| industry commitment | real but ~2 VP; manufacturer at every count |
| the guide's industry advice | cotton loses at every count, 2p included |
| learned value function | better offline ranking, ~18 VP worse in play |
| the Rust port's premise | it was justified on compute, and compute is dead |

The through-line: **the search is not the constraint and cannot be made into
one.** More iterations, more depth and a better leaf predictor all fail, because
each one applies a myopic evaluation further away rather than fixing it.

### What actually produced points

Seventeen rules bugs, all found by LLM agents playing full games through
`tools/play.py`, none by self-play. About a third of what agents report does not
survive checking, so verify before fixing. Self-play cannot notice that a legal option
was never offered. Three of our own "the bot fails this expert rule" verdicts
turned out to be the move generator instead.

### The live thread: a planner, not an evaluator

65% of the variance between seats in a 4p mirror is *play*, not the deal.
Identical bots on the identical board finish **28 VP apart** on average. The bot
is not unlucky, it is inconsistent, because every decision is local.

`brassbot/planner.py` is a beam search over whole lines of play rather than
single actions, scoring plans by what they finish on. On 10 seeds at 4p:

| | mean | best game | time |
| --- | --- | --- | --- |
| greedy 1-ply | 115.2 | 127 | - |
| beam width 20 | 134.3 | 152 | 32s |
| **beam width 40** | **143.7** | **166** | 73s |
| beam width 80 | 140.4 | 155 | 150s |

**+28.5 VP over the 1-ply bot at width 40**, where MCTS saturated at 300
iterations and got *worse* when made deeper. It plateaus by width 40 -- width 80
is 140.4, inside noise of 143.7 on ten seeds and twice the cost -- which is the
point to stop paying, not evidence that the approach is finished.

For scale: 143.7 sits inside the human tournament range of 142-184, against a
median of 158. No bot in this project has been near that. The action budget,
mat order, resource availability and link adjacency become constraints on one
optimisation instead of terms in a per-move score.

### The honest version works: 132.2 and a 79% win rate

`brassbot/bots/planner_bot.py` is the real thing -- it samples what it cannot
see, looks a bounded distance ahead rather than to the end of the game, and
re-plans every turn. 4p against three heuristics, report seeds, 24 games:

| bot | mean | win% | time |
| --- | --- | --- | --- |
| heuristic | 107.5 +- 1.5 | 25% | 3s |
| mcts 600 | 117.8 +- 3.0 | 42% | 191s |
| **planner h8 w12** | **132.2 +- 2.4** | **79%** | 286s |
| planner h12 w16 | 130.7 +- 2.6 | 79% | 556s |

**+24.7 over the heuristic and +14.4 over MCTS, at a 79% win rate against a 25%
baseline.** The perfect-information ceiling is 143.7, so roughly 11 VP of that
was clairvoyance and **most of the gain survives honest information** -- which
was the question the whole approach hung on.

That it holds up is partly because we are not blind: the deck composition is
fixed and known per player count, discards are face up, and hand sizes are
public. `determinize` redeals only the genuinely unseen pool, so the uncertainty
is which unseen card sits where, not what exists.

VP per action is now **4.26**, against the expert band of 4.8-5.2 and a club
average of 3.2. The heuristic sits at 3.47.

Horizon 12 with width 16 is no better than horizon 8 with width 12 and costs
twice as much, so the useful settings are small.

### The planner does NOT discover turn-order management

Brass sets next round's order by money spent, least first, so acting last while
spending little buys four actions back to back -- long enough to run build ->
connect -> beer -> sell without an opponent draining the coal or beer partway.
The engine models this correctly and *nothing in any bot uses it*: no reference
to `spent`, `turn_order` or `turn_pos` in the evaluation, and none of the 71
learned features touch it.

A sequence searcher ought to find it unprompted. It does not. 16 seeds, 4p:

| | VP | longest own-action run | four-runs/game | spend acting last vs otherwise |
| --- | --- | --- | --- | --- |
| heuristic | 110.1 | 3.38 | 0.94 | 4.8 vs 5.4 |
| planner | 132.4 | 3.25 | **0.75** | 5.4 vs 5.5 |

It scores 22 VP more while taking *fewer* double turns, and its spending is flat
whether or not it is acting last. Whatever the planner found, this is not it.

**The era boundary is already accounted for, in the evaluation not the search.**
A horizon of 8 own actions reaches the Canal/Rail wipe only from canal round 5,
so during rounds 1-4 -- when the industry line is chosen -- the plan cannot see
it. Doubling the horizon to 16, which reaches the boundary from round 1, changes
**nothing**: 137.7 +-2.4 at 96% wins against 137.7 +-2.3 at 96%, for twice the
runtime. The leaf already encodes the wipe through `scores_twice` (a flipped
level 2+ tile in canal is worth double) and `flip_horizon` (a level-1 tile that
cannot flip in time is worth nothing), so watching the wipe happen adds no
information.

This is the third suspected blind spot this session that turned out to be handled
already -- after market timing, which is visible through money, and the rival
term, which is computed after the candidate action. Check whether the bot is
actually blind before building it eyes.

**The beam collapse was investigated and is benign.** Distinct first actions
alive in a width-12 beam fall 8 -> 5.0 -> 2.7 -> 1.9 by ply four, with 57% of
searches down to one by then -- which is why `horizon=14` plays move-identically
to `horizon=8`. That looked like the search cutting good lines before they pay.
It is not. Giving each candidate first action **its own beam** and comparing
their best lines produces *identical play*: same mean 137.7, same 96% win rate
over 24 games, and 0 of 31 own moves different on each of two full games. The
beam converges early because the first action really is decided by then. Kept on
anyway, since the per-root form runs 21% faster.

**Why the planner does not find turn-order management is still unknown.** The obvious explanation -- that the beam
prunes partial lines with the myopic `position_value` and so cuts tempo plays
before they pay -- was tested and is wrong. Reserving beam slots per distinct
first action, so no candidate is eliminated early, scores **115.4 at a 46% win
rate against 132.2 at 79%**, and reserving two slots each is worse still at
110.5/29%. Spreading a width-12 beam across ~12 first actions leaves every line
one plan deep: a shallower search, not a fairer one. This beam needs depth more
than breadth.

Two chess ideas were then tried against the same target:

| change | result |
| --- | --- |
| root-diverse pruning | **115.4** vs 132.2 control -- badly harmful |
| quiescence (finish a pending sale before scoring) | 133.9 vs 132.8 control -- +1.1, 0.3 sigma, not a gain |
| transposition table | not built; measured **22%** of scored states are repeats |

### Turn-order management is measured, and it is not worth building

An agent played a full 4p game managing turn order deliberately and reported the
numbers. **Do not build this into the bot.**

It achieved four back-to-back actions **three times**, produced ~43 VP across
those twelve actions, and attributed **~0 VP to the actions being adjacent**.
Every combination it needed to protect fitted inside a single two-action turn.
The rule that matters is "two actions per turn", not "four in a row" -- four only
pays for a combo spanning three or more actions, or a slot you must take twice
before anyone reacts, and neither arose in 31 actions.

The two halves of the loop are also wildly asymmetric:

- **"Spend least, go first" is free and reliable** -- three attempts, three
  successes. Loan and Sell both cost nothing, so a cheap round costs no tempo.
- **"Spend most, go last" is not controllable at 4p** -- three successes in nine
  attempts, all early. Out-spending three liquid opponents late means buying
  market coal, which raises the price for your own next purchase. The agent drove
  coal from GBP1 to GBP8 chasing this, finished a rail round **GBP2 short** of a
  double rail that would have flipped a brewery and lifted three of its links,
  and lost by 13.

**Going first is worth buying; going last is not worth paying for.** The agent
finished last, on 94 VP at 3.03 VP/action, below the shipped heuristic's 3.47.

Its useful residue is two things that cost nothing: batch Sell actions into
rounds where you also Loan, and take loans *before* flips (see below).

### Loans before flips: free, unconditional, and nothing does it

"Loans move income by LEVELS, flips move it by SPACES" is worth more than the
footnote it has. Sweeping the whole income track -- 60 spaces x 7 flip sizes,
420 combinations -- **loan-first is never worse, and is better by one income
level in 41% of cases and by two in 11 more**. No bot here orders its actions
this way. Unlike the turn-order loop this is unconditional, so it is the better
target of the two.

### Still to do on it

**It is a ceiling, not a bot yet.** Two things stand between them:

1. **It cheats on hidden information** -- it sees opponents' hands and the deck
   order. Needs determinization, sampling those as MCTS already does.
2. **It is ~25x slower than the heuristic** and re-plans nothing. A real bot
   plans, plays the first action, and re-plans as the board moves.

Both will cost some of the +28.5. The question is how much survives.

### Ordered plan

1. **Determinize the planner and re-measure.** This is the honest number and
   everything else waits on it. If most of the +28.5 survives sampling, build the
   bot around it; if it evaporates, the gain was clairvoyance.
2. **Check whether the planner discovers turn-order management on its own.** The
   engine models "least spent goes first" correctly, and *nothing in the bot uses
   it* -- zero references to `spent` or `turn_order` in the evaluation or in the
   71 learned features. Four back-to-back actions is when a build -> connect ->
   beer -> sell chain completes without an opponent draining it. A sequence
   searcher should find this without being told; if it does, that is strong
   evidence the approach is right.
3. **Re-plan, not plan once.** Plan, take the first action, re-plan. Measure how
   often re-planning changes the line.
4. **Another agent playtest round.** Still the only method that reliably finds
   real defects. Two rounds, eleven bugs.
5. **The three remaining branching caps**, in cost order: Gloucester's develop
   industry, optional merchant beer, double-rail reachability. The discard cap is
   the expensive one and needs measuring before it is lifted.

Parked deliberately: the learned value function (needs MCTS-backed labels and
accumulated data -- a week, for maybe a 30-40% chance), and the Rust port (no
strength case left, though it would still make experiments faster).

## Search

40 games each, 4p, against three heuristic bots (fair share of wins is 25%):

| agent | mean | win% |
| --- | --- | --- |
| heuristic (no search) | 96.6 +- 1.2 | 25% |
| mcts, 100 iterations | 105.6 +- 2.2 | 35% |
| mcts, 300 iterations | 107.9 +- 2.2 | 40% |
| mcts, 600 iterations | **112.5 +- 2.2** | **50%** |
| mcts, 600, after the speedups below | 112.0 +- 2.2 | **57.5%** |

**Search pays at every budget tested and has not plateaued** -- roughly +4 VP per
doubling, still climbing at 600. That settles the concern from the Kingdomino
result (where UCT was 29 points *worse* than the greedy evaluator it wrapped at
short budgets): we are well above that threshold, and the reason is that our
leaves are evaluated by a tuned function rather than rolled out at random.

Costs about 1.1 s/move at 600 iterations, so ~33 s per game for one searching
seat.

**But search alone will not reach expert play.** At ~+4 VP per doubling, closing
the remaining 42 VP to a 155 expert score would need roughly ten more doublings,
and diminishing returns will arrive long before that. Search is a large constant
gain on top of the evaluation, not a substitute for the evaluation being right.

### Making search cheaper

Two rounds, both aimed by profiling rather than intuition -- and the first aimed
at the wrong target.

**Node cost 1.43 -> 0.67 ms.**

- Double-rail probing was **88% of `legal_networks`, ~43% of the whole node**,
  for the rarest action in the game. It cloned and then mutated `links` per
  candidate pair, invalidating the connectivity caches every time. It now pairs
  only lines that already source coal alone -- a second link only ever *adds*
  connections -- and tests against the board as it stands. The approximation can
  only refuse a legal move, never invent one; strength measured 96.6 +-1.1
  against 96.6 +-1.2 before.
- `legal_develops` cloned the entire state to ask what the mat looks like with
  one tile gone. It now removes the tile, looks, and puts it back.

**Search 1.7-2.5x faster** (300 iterations: 653 -> 259 ms/move).

That node work barely helped *search*, so profiling MCTS directly was the next
step: `legal_actions` was only **14%** of it, and the action-ranking prior
**73%**. The prior computed a value for every player and then used one,
discarding three quarters of the work. Behaviour-preserving -- the ordering is
identical and choices still replay from seed.

**The lesson, now three for three.** Every perf hypothesis reasoned from first
principles in this project has been wrong or irrelevant (per-mine distance
caching, twice; then `legal_actions`, which an old third-party profile named and
which had stopped being true after the caching work). Profile the thing you are
actually trying to speed up, immediately before you try.

### Order the sequencing was validated in

Weight tuning at 4p was exhausted *before* search was built, and confirmed as a
real optimum. Search then moved the number by +16. Building it earlier would
have searched harder toward the loan-farming that the money-VP bug rewarded --
which is exactly what the literature predicts, since search faithfully
reproduces a biased evaluation rather than correcting it.

**Sequencing is now evidence-backed, not a hunch.** One-step lookahead is a weak
archetype on this class of game (in Power Grid, OSLA scores *below random*), so
search is worth building eventually. But search does not repair a mis-calibrated
evaluation — on Dominion, five MCTS variants across four parameter settings and
three budgets all converged to the same poor optimum, and the fix was a better
heuristic. Our failure is leaf-evaluation *bias*, not a horizon effect, and the
sell chain sits 40-80 nodes deep. Fix the evaluation first. Details and citations
in `docs/research-landscape.md`.

**Do not simply re-tune.** The tuner drove `debt` from 0.45 to 0.1125 because it
correctly learned that under this evaluation loans win. It is working properly on
a broken objective.

### How to tune without fooling yourself

`tools/tune.py` uses **three disjoint seed blocks**: tune on 10000+, validate on
20000+, report on 0+. It prints the measured noise floor and refuses any step
that does not clear it, then re-measures the final weights on the validation
block and says plainly whether the gain survived.

That machinery exists because it caught two real failures:

- A run reported **114.3** on its tuning seeds and measured **103.6** on
  held-out boards, against 106.7 for the weights it replaced. Coordinate descent
  had chased run-to-run variance for a whole pass.
- On its first outing the new validation flagged a run claiming 118.2 as
  **91.0 vs 101.0 starting** -- "NOT a real improvement."

**Never accept a tuning result on its own seeds.** At 50-60 games per candidate
with SD ~20, the noise floor is about +-2.5, and coordinate descent will happily
walk uphill on noise for a dozen steps.

### What tuning bought, and what it did not

Coordinate descent over 73 candidates (9 min) moved the mean from 47.9 to 86.5
on tuning seeds, holding up at 83.1 on unseen boards -- so the weights
generalised rather than fitting the tuning set.

The bigger win was robustness, which the mean hides: the untuned bot busted to
zero in **9% of games** (SD 30.7, P10 0). The tuned bot has **no busts at all**
(SD 13.6, P10 66). It stopped losing games outright.

Caveat on reading the tuner log: with 40 games per candidate and SD ~30, its
standard error is ~5. The early steps (47.9 -> 82) are far beyond noise; the
last few one-point "improvements" are not, and pass 2 partly undid pass 1 on
`rival` and `links_held`, which is what noise-fitting looks like. Raise
`--games` before trusting small steps.

### Performance

3.5x faster than the first working engine (~80 -> ~280 moves/s single-threaded):

- `link_adjacency` was rebuilt on every call, 11k times per game. Now cached
  against a version counter on `LinkMap`, which bumps itself on mutation so no
  call site has to remember to invalidate.
- `distances_from` is memoised per source set against the same version, and was
  additionally being recomputed *inside* `coal_plans`' recursion even though the
  link graph cannot change mid-plan.
- Double-rail generation cloned the whole state per candidate pair (3,080 clones
  per game). It now reuses one probe clone, and the pair pool is bounded by
  `DOUBLE_RAIL_CANDIDATES`.

Still hot, in order: `all_tiles()` (a linear scan behind every resource query --
an index of mines / iron works / breweries would help), `distances_from`, and
`clone()` copying tiles that were never touched.

MCTS will still want orders of magnitude more, which is what the Rust port is
for.

**Fixed along the way:** `clone()` shared the RNG object with its parent, so a
lookahead that applied an action far enough to reshuffle the deck would have
drawn from the real game's generator and changed what actually happened. Clones
now copy the RNG state instead of the reference.

**The design decision to get right early:** action canonicalisation. A raw Build
is (card x location x tile x coal source x iron source). The caps above are a
blunt first pass; the real fix is collapsing resource sourcing to the genuinely
distinct choices.

## Conventions

- Ids are snake_case everywhere (`stoke_on_trent`, `farm_northern`, `coal_mine`).
- Income *advances* are in track spaces; income *level* is what the space pays.
  Never conflate them — the track is deliberately nonlinear.

## Terms audited against outcomes: what is settled

Four agents instrumented self-play, booked every VP back to the action that
earned it, and regressed outcomes on what each term estimates. Recorded so that
none of this is re-litigated from argument.

**Changed.**

- `loan_bias` **1.5, new.** The evaluation charges a Loan ~4.5 units below its
  preferred move and the realised cost of taking one is **zero** -- a ~3.4 VP
  over-charge, the largest miss in the vector. Mechanism: the income penalty is
  charged `3 x rounds_left x income` while the £30 is priced flat, so the bot
  dislikes loans most in the Canal Era, exactly where forcing one measures best
  (forced canal Loan +1.32 vs control, rail -0.71). The curve peaks sharply:
  2.5 is -0.39 and 4.0 is **-6.30** (the bot loops on loans). Do not raise it.
- `mat_potential` **0.25 -> 0.125.** The next mat tile is built 41.6% of the
  time and banks 1.97 VP against a 5.54 face. See the comment in `heuristic.py`
  for why no better *shape* exists.
- `beer_capacity` **3.0 -> 1.5** plus `beer_rail` **3.0**. Only 28.3% of own
  barrels reach a sale, and a double rail's beer cannot come from a merchant, so
  the sale cap paid nothing for it. Beware the single block: seat-balanced it
  read +0.27 +- 0.96 on report and +2.21 +- 0.65 on validation, pooling to
  **+1.60 +- 0.54**. Win share was 55.0% and 55.6% across the same two blocks --
  at this sample size win share is the steadier statistic of the two.

**Leave alone -- measured, not argued.**

- `blocked` **= 6** is correctly sized (outcomes say -4.32 +- 0.64 VP per
  blocked industry) and nearly inert: cotton is blocked in **800 of 800** seats,
  so 6 of the charge is a constant that cancels in every comparison. Sweeping it
  0 -> 9 moves the score by less than 0.3.
- `links_held` **= 0.3** prices a constraint that never binds: `links_left` is
  14 at the end of all 800 seat-games, because links return at era scoring. The
  term is really a -0.3 toll on every Network action. Correcting it gains
  nothing (0.0 reads -0.80 and -0.18 in 2v2).
- `rival` **= 0.225** should be ~4x higher by outcomes (the best opponent's
  position predicts nearly as strongly as your own), but the whole range
  0.0 -> 1.0 is flat, because **51% of candidate moves cannot change any
  opponent's value by construction**. Same reason the endgame ramp measured
  null.
- `liquidity_scale` **= 8.438** is ~3.5x too short against outcomes and
  stretching it to 30 measured **+2.48 +- 0.59** over 700 held-out games -- but
  that was on a snapshot predating `loan_bias`, and the two are **substitutes,
  not additions**. Seat-balanced in the current tree, 30 scores **-0.82 +- 0.59
  with `loan_bias` present** and **+1.19 +- 0.89 with it removed**. `loan_bias`
  is the better-evidenced half, so it carries the correction. The general
  lesson: `income`, `money`, `money_horizon`, `liquidity`, `liquidity_scale` and
  `loan_bias` are six ways of saying "cash is underpriced" and only one should
  be turned -- every combination the audit tried scored below the best single
  change.
- `income` **= 0.08438** is 2-3x low and linear where outcomes scale as
  `rounds_left^1.34`, but raising it loses monotonically (0.17 -> -4.2,
  0.3 -> -15.8). Wrong against outcomes, not correctable by its own weight: the
  windfall value of free income is not the price at which income should be
  bought with an action and cash. Same for `money`, whose measured value is 6-7x
  its weight and which scores **-21.5** if priced there.
- `debt` **= 0.0633** guards an event costing 23 VP across 320 seat-games, 21 of
  them in a single seat, while firing at 11.4% of decisions and adding 75% on
  top of the income charge. Oversized and wrongly motivated, but `debt=0` is
  only +0.92 +- 0.53. Not worth a change.
- `merchant_access` **= 2.4** is correctly sized, and its connectivity gate is
  load-bearing: removing the gate costs -2.05.
- `flip_horizon` is badly mis-calibrated in the Rail Era and worth **+0.01** to
  fix, because every rail tile shares the same horizon so it cannot re-order
  candidates.
- The `sell_ready`/`unflipped` inversion is **not a bug**: not-ready tiles flip
  97.7% of the time against 94.4% for ready ones.

**Tried and rejected, with numbers.**

- `scout_bias` 1.0 replicated on the tune block (+2.31) *and* validation
  (+3.31), then died on report (**+0.36 +- 0.75**). Both non-report blocks
  flattering at once is exactly what the three-block split exists to catch.
- **Banning Develop in the Rail Era is null** (+0.06 +- 0.55), though a forced
  rail Develop is worth only +0.92 over a Pass. The forced arm measures develops
  the bot did not want; the ones it picks are already worth its alternatives.
- Per-industry realisation rates for `mat_potential`: **-4.27 +- 1.94**.
- Zeroing the cotton and pottery mat terms changes play **bit-for-bit not at
  all**: under `commit` those builds are struck from the move list, so 3.75 of
  the 8.36 mat credit is a dead constant. This is very likely why the earlier
  pottery correction measured -0.79 -- with the industry banned, it had nothing
  to act on.

**Where the score comes from** (200 games, enablement ledger -- each point split
among the actions that were strictly required for it):

| type | VP/game | per action |
| --- | --- | --- |
| Sell | 15.8 | **6.21** |
| Build | 40.7 | 3.63 |
| Network | 26.2 | 2.30 |
| Develop | 2.7 | 1.11 |
| Loan / Scout / Pass | 0 | 0 |

**23.3% of the bot's score is flipped by an opponent's action, not its own.**

---

## 2026-09-04 — LLM opponents, the beer belt, and two stale headline numbers

### LLM agents are now a usable opponent, and the model matters enormously

Ten agent games against the shipped heuristic at 4p, seat 0, one game a seed.
Read them against the **4p mirror mean of 131.3, SD 12.4** -- that is what a
seat in this pool is worth, so it is the only fair yardstick.

| model | brief | seeds | mean | z |
| --- | --- | --- | --- | --- |
| sonnet | mixed, incl. the 13-rule style prompt | 4 | 86.2 | -3.63 |
| fable | engine mechanics only | 3 (9101/03/05) | 109.7 | -1.74 |
| fable | mechanics + human observations as *information* | 3 (9102/04/06) | 116.3 | -1.21 |

Best fable games were **131 twice** -- dead on the bot's own mean, one of them
taking first place at the table. Fable is a real sparring partner; sonnet was
not. Note 9104 (87) is contaminated: the agent chained two `move` calls and
`play.py`'s positional indices shifted under it, so it played a link where it
meant to build a brewery. **`tools/play.py` taking bare indices is a hazard for
any agent driving it** and is the first thing to fix before running more.

**More rules made agents play worse, monotonically** -- see
`docs/playstyle-prompt.md`, which now carries the table. The cause was
extraction, not strategy: descriptive statistics were written as imperatives.
"Humans sell 0-2 times a game" became "sell rarely", and an agent obeying it
skipped the Sell that would have flipped two tiles before the era wipe. Rules 6,
9 and 12 there now carry the caveat that makes them safe to follow.

### What every agent lost to, on every board

All six fable games independently named the same mechanism: **our heuristic
takes the hub links in the first one or two Rail-Era rounds**, and a plan formed
a round earlier has nowhere to land. Five of Birmingham's seven spokes on 9101
and 9102; all four Derby links between two of one agent's own turns on 9103;
nine named links on 9105. One agent diagnosed itself precisely -- *"I spent rail
round 1-2 on Derby builds instead of grabbing links first; that ordering cost
roughly 15-20 link VP."*

That is the bot's strongest weapon and it is **denial, not scoring**. A mirror
match cannot show it, because there everyone does it. This is the class of
finding only an outside opponent produces.

Twice an agent reported the engine refusing a legal-looking sale. Both were
correct behaviour, checked: `MerchantSlot.accepts` handles `"any"` properly, and
the tiles were **pottery L3 and manufacturer L5, which need 2 beer**, planned
against a single merchant barrel. Three of six agents made this same mistake, so
`show` is not surfacing `beer_to_sell` where the *build* decision happens.

### A brewery is the only permanent 2-icon anchor on the board

From `link_vp` in the tile data, and this is the sharpest new fact here:

| industry | link VP by level |
| --- | --- |
| brewery | 2, 2, 2, 2 -- **never drops** |
| coal_mine | 2, 1, 1, 1 (only the L1, which the era wipe removes) |
| cotton_mill | 1, 2, 1, 1 |
| iron_works | 1, 1, 1, 1 |
| manufacturer | 2, 1, **0**, 1, 2, 1, **0**, 1 |
| pottery | 1, 1, 1, 1, 1 |

Two consequences. **Manufacturer L3 and L7 -- the beer-free sellers we
recommend -- are worth zero link VP**, so they are bad neighbours for a link
network and the two pieces of advice pull against each other. And a brewery's
2 icons are the only ones on the board that appear *without the owner spending
an action*: an opponent drinking your beer flips it for you. Every other 2-icon
tile is beer-gated and can strand -- three of six agents stranded one.

Board geography, measured:

- 10 towns can host a brewery (11 slots). **45% of those slots are in the
  Uttoxeter / Stone / Derby / Burton belt, which is 27% of towns.**
- Icon ceiling rises with slot count: 1 slot 2.00, 2 slots 3.79, 3 slots 5.00,
  Birmingham 7.00.
- **Derby is the best town after Birmingham** -- 3 slots, ceiling 5, brewery,
  4 rail links. Stone, Burton and Walsall are the next tier (4 / 4 / brewery).
- Honest caveat: on raw ceiling, brewery towns are *not* better -- 3.70 icons
  and 2.8 rail links against 4.33 and 3.5 for the rest. The argument is about
  **certainty of flipping**, not ceiling.

The bot already favours the belt for breweries: **63% of its breweries land
there against a 45% slot baseline**, while its builds overall are neutral (29%
in the belt, which is 27% of towns).

### Two headline numbers in this document went stale and were re-measured

`mcts.py` was last touched 2026-08-28. `pair_search` landed 09-01 and the
re-tune 09-03. **MCTS shares `player_value` with the heuristic but not its
action selection**, so every gain since August accrued to the heuristic alone
while MCTS stood still. Its docstring still claims "+9 VP over the heuristic",
measured against a bot that no longer exists.

But it is **not** simply the heuristic minus the turn search, and that was the
tempting wrong conclusion. Over 93 decisions:

    MCTS picks what the SHIPPED heuristic picks     63.4%
    MCTS picks what a pair_search=0 heuristic does  69.9%
    the two heuristics agree with each other        73.1%

It leans pre-`pair_search` by only 6.5 points and makes ~30% independent
choices. So it is genuinely searching, and those independent choices are on net
worth about -5 VP. Do not retire it on the copy argument that retired the
commit bot -- that one was byte-identical, this is not. Its own comments already
record that `c`, `widen_k`, `widen_alpha` and `prior_width` all sat inside the
noise floor, so the gap is not in the search settings.

**Measured head to head, 2026-09-04:** `mcts` - `heuristic` = **-4.81 +- 1.66**
over 60 seat-balanced 4p games (-2.9 sigma), taking the top score in 37% where
an even split is 50%. It agrees with the independent 140.0-vs-145.6 estimate.
One block, so treat the size as provisional -- but the SIGN is not in doubt, and
the repo currently ships a search bot that loses to the evaluation it searches
with. That is the state to resolve: either the leaf value and prior stop being
the same function, or `mcts` is retired.

---

## 2026-09-05 — one gain, and four leads closed by measuring them

### The gain: do not BUILD a brewery L1

**+1.86 +- 0.56 at 4p** (three blocks, 540 seat-balanced games, chi2 = 2.51 on
2 df) and **+1.78 +- 0.78 at 3p** (chi2 = 0.32). At 2p it is +2.06 +- 0.89 but
**chi2 = 6.73 fails the heterogeneity check** -- one block came back -1.12
against another at +4.81 -- so treat 2p as unresolved.

Brewery L1 is canal-only: it pays 4 VP and 4 income spaces if it flips, then the
boundary sweeps it. A brewery only flips when somebody DRINKS it, and the bot
builds its breweries at canal round 4.9 on average -- late enough that they
often die unflipped. So the build buys nearly nothing.

**The mechanism is action reallocation, not strategy.** Measured on paired
seeds, banning the build changes:

| | normal | banned | change |
| --- | --- | --- | --- |
| breweries built | 2.76 | 2.57 | **-0.19** |
| of them L1 | 0.38 | 0.00 | -0.38 |
| of them L3 | 0.65 | 0.78 | +0.13 |
| **double rails** | **3.01** | **2.97** | **-0.04** |
| links laid | 11.79 | 11.94 | +0.15 |

0.38 builds freed, about half rebuilt higher on the ladder and half spent
elsewhere. 0.38 actions at 4.59 VP each predicts **+1.74**; measured **+1.86**.
The numbers only line up that well if the L1 was returning close to nothing.

**It is NOT about beer or double rails** -- doubles moved -0.04. An earlier
reading in this document that connected breweries to the double-rail count was
wrong and is withdrawn.

**A round-aware version is worse, not better.** Allowing the L1 build through
canal round K, 180 games a cell:

| K | | delta |
| --- | --- | --- |
| 0 | never build it | **+2.41** |
| 1 | round 1 only | +2.41 |
| 2 | rounds 1-2 | +2.20 |
| 3 | rounds 1-3 | +1.99 |
| 4 | rounds 1-4 | +0.31 |

K=0 and K=1 are identical because the bot never builds a brewery L1 in round 1
anyway (its earliest brewery is round 3). Every further round of permission
costs. **The blunt rule is the right one.**

**SHIPPED as `doomed_build`, and the weight beats the ban.** A penalty in
`_bias` on building any canal-only tile, 1.0 at 4p, pinned to 0 at 2p and 3p.

**+2.51 +- 0.68 at 4p** (3.7 sigma) on two fresh blocks after the value was
chosen on a third; +2.85 +- 0.55 over all 540 games, chi2 1.09/2. Quote the
fresh figure -- the swept block is selection-biased.

The value curve at 4p, 180 games a cell: 0.125 +1.30, 0.25 +1.96, 0.5 +2.56,
0.75 +2.79, **1.0 +3.49**, 2.5 +2.16, 5 +1.73, 10 **-1.32**, 25 **-1.44**.
Large values are actively harmful: `_bias` is summed across both halves of a
turn in the pair search, so an overwhelming penalty poisons every pair holding a
doomed build and suppresses the good ones too.

**Why the penalty beats the ban (+1.86), measured:** at 1.0 doomed brewery
builds fall 0.38 -> 0.03 a game while doomed iron works barely move, 0.17 ->
0.15. An iron works L1 into a short market flips instantly and is often
cash-positive, so it still clears the bar; a brewery nobody will drink does not.
A hard filter cannot make that distinction.

3p is null -- 0.5 +1.12, 1.0 +0.05, 2.5 +0.37, none above 1 sigma -- which also
casts doubt on the ban's marginal +1.78 there. 2p failed heterogeneity. Both
pinned to 0, and verified: 2p and 3p games are bit-identical to the pre-change
bot, 4p games differ.

### Closed: the double-rail "gap" is not a gap

Human logs take 5.00 double rails a game, the bot 2.96, and this document has
treated that as the largest behavioural difference available. It is not a
difference in decision quality.

    rail-era decisions            16.00 a game
    a double rail was LEGAL at     4.85   (30% of decisions)
    the bot TOOK it                2.96   (61% of offers)
    declined for a Build           1.56   (32% of offers)

The chances exist -- 4.85 offered against the humans' 5.00 taken -- so the bot
is not starved of them. But **forcing every legal double rail measures -0.21 +-
0.89**: flat. The Builds it prefers are worth as much as the doubles it skips,
which makes sense, since a mine or works into a short market flips instantly and
is often cash-positive. Do not chase this.

### Closed: turn order is worth about one action, and not worth a term

Turn order is by money spent, so going last in round N and first in round N+1
gives four consecutive actions -- twice the window `pair_search` exploits. The
37 weights include nothing that reads `spent`.

    the bot already gets 1.12 double turns a game; 72% of seats get one
    correlation with final score: r = +0.106

    forced FIRST every round   134.7
    forced LAST  every round   129.8
    value of turn position     +4.81 +- 1.86 VP (2.6 sigma), wins 64% of pairings

**+4.81 is an upper bound** -- it hands first position over free, where a real
bot must pay actions and money for it. Against `pair_search`'s +7.6 for a window
half the size, the headroom is smaller and much harder to capture.

### Closed: forcing a Canal-Era brewery develop

This document records "+7.7 VP" for that. Re-measured seat-balanced in the
current tree: **+1.15 +- 0.98, 1.2 sigma.** Like the planner's +14.78 -> +3.09,
the original was measured on the 1v3 harness before `pair_search`. The gain is
in not wasting the build, not in developing more.

### Archetype commitment, at n=120 instead of n=2

Banned-industry bots, 120 seat-balanced games a cell, null control +0.11 +- 1.04:

| banned from building | delta | se | sigma |
| --- | --- | --- | --- |
| BRIC (no cotton/manu/pottery) | -11.30 | 1.22 | -9.3 |
| BRIC + pottery | -7.74 | 1.12 | -6.9 |
| BRIC + cotton | -5.84 | 1.28 | -4.6 |
| BRIC + manufactured | -4.18 | 1.20 | -3.5 |
| no coal | -9.80 | 1.32 | -7.4 |
| **no brewery** | **-16.28** | 1.10 | **-14.7** |

**Banning breweries costs more than banning all three selling industries
combined.** Coal is second. See `docs/strategy-archetypes.md` for the full
26-game agent study behind these, and for the corrections it needed once the
n=120 numbers arrived.

### The best remaining lead: the move generator decides things the player should

Three agents independently hit places where `legal_actions` makes a SCORING
choice on the player's behalf, so the bot has never seen the alternative:

1. **Merchant assignment on multi-tile sells.** A 4-tile sale was offered
   "all-Oxford only"; the Nottingham variant (+3 VP each instead of +2 income)
   was never enumerated.
2. **Beer source on a double rail.** The engine picks own breweries on link
   towns, alphabetically -- and that choice decides WHICH of your breweries
   flips, which is 4-10 VP.
3. **The merchant develop bonus** is auto-resolved toward whichever removal
   uncovers the highest-VP tile. Three separate agents lost a tile they had
   planned around.

This repo has found 17 rules bugs, **none from self-play**, and
`docs/architecture.md` says why: a bot only ever plays what it is offered. These
are the same class and none has been costed.

Also unclaimed: `MAX_DISCARD_VARIANTS` is 1 for the bot because the evaluation
ships `wild_card` and `hand_breadth` at 0 and cannot tell the variants apart.
The engine comment names the fix itself -- "raising it for the bot only pays
once the evaluation values cards, which is the actual missing piece."

### Human logs, now nine seats

| | mean | values |
| --- | --- | --- |
| sells | 0.56 | 0,0,0,0,0,1,1,1,2 |
| double rails | 5.00 | 4,4,5,5,5,5,5,6,6 |
| score | 127.7 | 101,110,116,119,129,137,138,144,155 |

Wins 6 of 9. Builds across all nine seats: coal 26, brewery 22, iron 14,
pottery 6, manufacturer 2, **cotton 0**. Brewery tiles developed away 2.56 a
seat and **brewery L1 built ZERO times in nine games** -- which is the
observation the gain above came from.
