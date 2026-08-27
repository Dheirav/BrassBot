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

Rules engine complete and stable: 63 tests pass, and 80 full 4-player games
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
| 4p | mirror | 98.2 +- 0.9 | 15.6 | 79 | 146 | **3.17** | 25% |
| 4p | vs greedy | 101.3 +- 2.1 | 18.7 | 78 | 144 | 3.27 | 94% |
| 3p | mirror | 100.2 +- 1.1 | 16.9 | 81 | 145 | 2.86 | 33% |
| 3p | vs greedy | 101.0 +- 2.2 | 19.7 | 78 | 136 | 2.88 | 96% |
| 2p | mirror | **104.9 +- 1.8** | 23.0 | 82 | 148 | 2.69 | 50% |
| 2p | vs greedy | 105.9 +- 2.3 | 21.0 | 77 | 144 | 2.72 | 98% |

Effect of per-format weights (mean, before -> after):

| fmt | mirror | vs greedy |
| --- | --- | --- |
| 2p | 88.8 -> **104.9** | 78.2 -> **105.9** |
| 3p | 102.1 -> 100.2 | 90.3 -> **101.0** |
| 4p | 98.6 -> 98.2 | 99.4 -> 101.3 |

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
| + money horizon, mat potential, era boundary | **98.2** | **3.17** |

### Behaviour against expert benchmarks

| metric | before | now | expert 4p |
| --- | --- | --- | --- |
| loans per game | 9.6 | **4.8** | 4-6 canal, 0-3 rail |
| final income | -7.7 | **+8.0** | positive |
| rail links | 5.0 | **7.0** | 7-10 |
| canal links | 3.2 | 4.5 | 2-4 |
| tiles sold | 0.6 | **2.8** | - |
| tiles flipped | 5.4 | **9.5** | 8-12 |
| VP split industry:link | - | **46:47** | 65:35 to 40:60 |
| pottery level reached | 0.1 | 1.1 | - |
| cash left at game end | ~164 | **52** | 0 (worth nothing) |

Rail links, tiles flipped, loan count and the industry:link split are all now
inside expert bands. The remaining leaks are visible: **52 pounds unspent at the
final whistle** is roughly ten actions of unused buying power scoring nothing,
and canal links run slightly above the expert 2-4 (the rule of thumb is to build
one only when it scores 6+ VP or is strictly needed).

### Distance to a realistic target

**200+ is not reachable at 4 players** and this is now settled with tournament
data -- see `docs/research-landscape.md`. Fifteen verified tournament games (WBC
2024/2025, Prezcon 2023, WSBG 2022/2025) run **142-184, median 158, none at or
above 200**.

| target | VP/action | where we are |
| --- | --- | --- |
| club average | 3.2 | **we are here (3.00 mirror, 3.32 vs greedy)** |
| strong 4p winner | 4.8-5.2 | +60 VP away |
| tournament ceiling | 5.9 | - |

Best single game so far: **150** (vs greedy), **139** (mirror) -- inside the
range of real tournament winning scores, but not yet the average.

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

| dimension | ours | expert | |
| --- | --- | --- | --- |
| VP per action | 3.07 | 4.8-5.2 | LOW |
| **VP entering the Rail Era** | **29.5** | **70-80** | **LOW** |
| **loans in the Canal Era** | **1.5** | **4-6** | **LOW** |
| **tiles developed in the Rail Era** | **2.8** | **0** | **HIGH** |
| tiles developed | 5.8 | 2-4 | HIGH |
| canal links built | 4.9 | 2-4 | HIGH |
| money left at the end | 18.9 | 0-10 | HIGH |
| rail links built | 8.5 | 7-10 | ok |
| tiles flipped | 9.8 | 8-12 | ok |
| loans in the Rail Era | 1.8 | 0-3 | ok |
| share of VP from industry | 0.47 | 0.40-0.65 | ok |

**These four failures are one mistake.** The bot under-invests in the Canal Era:
it takes 1.5 loans where experts take 4-6, so it has too little money, so it
enters the Rail Era on **29.5 VP against an expert 70-80** -- and then spends
scarce Rail Era actions developing (2.8) that should have been done in canal, at
roughly 5 VP of opportunity cost each.

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

1. ~~Eval harness~~ — done. Rotates seats, reports a distribution and the
   `>=200` hit rate, splits drawn wins, and flags turn-order bias.
2. ~~A real heuristic bot~~ — done, and tuned. Beats `greedy` 75.5% at +29 mean.
3. ~~Diagnose where the points are missing~~ — done, and it changed the plan.
   Full write-up in `docs/diagnosis.md`. The short version: the bot never builds
   or sells cotton, manufacturers or potteries (highest level built: 0.3, 0.5,
   0.1), sells 0.6 tiles a game, and spends **47-66% of its Rail Era actions
   taking loans**. A quarter of its score is leftover cash.

   It is stuck in a self-fulfilling trap: a 1-ply evaluation credits an
   unflipped sellable tile at 0.25, so building one looks like a loss, so it
   never builds one, so Sell is never legal, so money becomes the cheapest VP,
   so it loans. It is being rationally pessimistic about its own inability to
   execute the build-connect-sell chain.

4. **Fix the evaluation before adding search** (next):
   - credit an unflipped sellable tile near full value when a sale is *available
     now* -- connected accepting merchant plus reachable beer -- and low when it
     is not; add terms for merchant connectivity and beer access so building
     *toward* a sale registers as progress
   - set `money` to its true terminal value of 0.10 (it is 0.225) and let the
     liquidity term carry "can I still act"; re-tune `debt` afterwards, since its
     current value was fitted to a world where loans were good
   - re-run the diagnostic; if sales rise and loans fall, re-tune
5. **Memoise `legal_networks`** — a prerequisite for search either way.
   Profiling puts `legal_actions` at 4.52 ms against 0.08 ms for clone+apply,
   85% of it in `legal_networks` via ~112 `coal_plans` and ~282 `distances_from`
   calls per invocation. That caps node expansion at ~200/s; published MCTS on
   comparable games needed thousands of iterations per move.
6. ~~Search bot~~ — built (`brassbot/bots/mcts.py`) and it is the largest single
   gain in the project. See below.
7. ~~Make nodes cheaper~~ — done, twice over. Node cost 1.43 -> 0.67 ms and
   search 1.7-2.5x faster; details below. Strength is unchanged where it should
   be and the win rate rose from 50% to 57.5% at the same 600 iterations.
8. ~~Measure at 1500+ iterations~~ and ~~tune the search parameters~~ — both done.

### Search budget, measured

40 games each (24 at 1500), 4p, against three heuristic bots:

| agent | mean | win% | VP/action |
| --- | --- | --- | --- |
| heuristic | 96.3 +- 1.1 | 25.0% | 3.11 |
| mcts 300 | 107.9 +- 2.2 | 40.0% | 3.48 |
| mcts 600 | 112.8 +- 2.2 | 57.5% | 3.64 |
| **mcts 1500** | **115.6 +- 3.2** | **66.7%** | **3.73** |

Still improving, but **flattening**: roughly +5 for the first doubling, +3 for a
2.5x increase after it. Compute is still a lever and the Rust port would still
pay, but it is no longer the cheap one -- reaching an expert 155 this way would
need far more doublings than the curve will support.

### Search parameters are already near a flat optimum

A full tuning run (17 candidates, 57 min, `-b mcts`) changed exactly one
parameter, `c` from 1.0 to 0.5, and reported +3.0 VP on its validation block
against a +-2.2 noise floor. Measured on the reporting seeds, **paired against
c=1.0 on identical games, it came out 2.8 VP worse.** Two blocks favoured 0.5,
one favoured 1.0; pooled it is a wash. Not adopted.

`widen_k`, `widen_alpha` and `prior_width` were all left untouched -- nothing beat
the noise floor. That is the useful result: the settings taken from published
multiplayer work were already good, and **the remaining gap is in the evaluation,
not the search configuration.** Do not re-run this expecting a win.

The cited hope was that MCTS parameters could be worth a 32x compute advantage.
Here they were worth nothing measurable, most likely because they were never
badly chosen.
8. **Policy/value net** — only if search plateaus. It has not.

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
