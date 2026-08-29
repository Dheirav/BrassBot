# NEXT — BrassBot

Live handover document. Current state, then what to pick up.

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

Rules engine complete and stable: 175 tests pass, and 80 full 4-player games
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

| format | mirror | vs greedy | best single game |
| --- | --- | --- | --- |
| 4p | 107.7 +- 0.8 | 106.8 | 164 |
| 3p | 113.5 +- 1.2 | 105.9 | 153 |
| 2p | 119.4 +- 1.3 | 114.9 | 158 |

MCTS reaches ~119 at 4p. Human tournament play runs 142-184, median 158, and the
yardstick's 5.9 VP/action ceiling gives ~183 at 4p -- the two agree, which is the
best evidence we have that 5.9 is real. 200+ is a 2p target (39 actions x 5.9),
not a 4p one.

### What is settled, and will not be revisited without new evidence

Seven levers have been measured and closed. Each has numbers in this document.

| lever | verdict |
| --- | --- |
| more MCTS iterations | saturates by 300; 5x compute buys nothing |
| deeper search (narrow beam) | depth 10 plays *worse* than depth 4; breadth wins |
| evaluation weights | flat optimum everywhere tried, income included |
| industry commitment | real but ~2 VP; manufacturer at every count |
| the guide's industry advice | cotton loses at every count, 2p included |
| learned value function | better offline ranking, ~18 VP worse in play |
| the Rust port's premise | it was justified on compute, and compute is dead |

The through-line: **the search is not the constraint and cannot be made into
one.** More iterations, more depth and a better leaf predictor all fail, because
each one applies a myopic evaluation further away rather than fixing it.

### What actually produced points

Eleven rules bugs, all found by LLM agents playing full games through
`tools/play.py`, none by self-play. Self-play cannot notice that a legal option
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

**Why it happens is still unknown.** The obvious explanation -- that the beam
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
- Not a git repo yet.
