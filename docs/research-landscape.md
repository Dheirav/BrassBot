# What exists, and what a realistic target is

Research completed 2026-08-27. Sources are self-reported player data and code
repositories; treat the score figures as community-reported, not measured under
controlled conditions.

## 1. The 200 VP target is not reachable in 4 players

This is the finding that matters most, and it contradicts the project's stated
goal.

Brass gives each player a fixed number of actions: 2 per round, over 10/9/8
rounds per era at 2/3/4 players, across two eras, minus one for the single-action
first round. So:

| players | actions per player | expert VP at ~5/action |
| --- | --- | --- |
| 2 | 39 | ~195 |
| 3 | 35 | ~175 |
| **4** | **31** | **~155** |

That "VP ≈ actions × 5" rule comes from a player with 100+ plays, and it lines up
with the independent self-reported score data:

- [BGG thread 2698436](https://boardgamegeek.com/thread/2698436), post 38159016 —
  27 plays, 10 players, mostly experienced 3-4p: **top 185, average winning 158,
  average score 141**, lowest winning 134.
- [BGG thread 2756965](https://boardgamegeek.com/thread/2756965) — **4p winner
  average 140-150**; one 10-game 4p sample averaged 124 with a high of 176. In
  *3 players*, which scores higher, **200+ happens about 1 game in 20**.

So in a 4-player game, 200 VP needs about **6.5 VP per action against the ~5 that
strong human play achieves** — roughly 30% better than expert humans, in the
player count that scores lowest. The reported 4p maximum anywhere in this data is
176-185.

**Recalibrated targets, in increasing order of ambition:**

| target | VP/action | meaning |
| --- | --- | --- |
| 100 | 3.2 | competent club player |
| 155 | 5.0 | **expert human 4p play** |
| 165 | 5.3 | wins a table of experts |
| 185 | 6.0 | best 4p result in the sampled data |
| 200 | 6.5 | beyond any reported 4p game |

**VP per action is the better progress metric** than raw score, because it is
comparable across player counts and directly encodes the constraint that actions
are the scarce resource.

Where we are now: **63 VP in a 4p mirror over 31 actions = ~2.0 VP/action**, or
about 40% of expert efficiency.

If 200+ specifically is the goal, it is reachable at **2 players** — experienced
2p winners are reported at 180-210, with one 208 in a 35-game sample. The engine
already supports 2p and the harness takes `--players 2`.

## 2. Nobody has built a strong Brass bot

- **No academic literature exists.** arXiv returns nothing across four query
  forms; Semantic Scholar returns only false positives. The
  [TAG / Tabletop Games Framework](https://github.com/GAIGResearch/TabletopGames)
  — the main academic framework for modern board game AI, ~40 games including
  Terraforming Mars and Puerto Rico — does not include Brass.
- Of ~46 GitHub repositories, **two publish any measured scores**, both weak:
  - [Quasrain-Coder/BrassBirmingham](https://github.com/Quasrain-Coder/BrassBirmingham)
    — LLM agents, 2p self-play: **average 1.4 VP, median 23, 40% of games
    negative**, and 70%+ of actions were Pass in later variants.
  - [KDC-Solo/brass-birmingham](https://github.com/KDC-Solo/brass-birmingham) —
    a fan Automa scoring 105-200 by difficulty; passive/random play 0-63.
- The most complete RL setup,
  [VyqreL/brass-birmingham-rl-model](https://github.com/VyqreL/brass-birmingham-rl-model)
  (Gymnasium, action masking, MaskablePPO), has **one commit and no results,
  models, or logs**. The one real MCTS implementation
  ([robert-ptr/Brass_MCTS](https://github.com/robert-ptr/Brass_MCTS)) runs 10
  iterations.

**No published score distribution for random / greedy / heuristic / MCTS Brass
play exists anywhere.** Our harness already produces exactly that, so those
numbers would be the first of their kind.

## 3. Independent corroboration of our diagnosis

The LLM-agent project's action mix reports **Sell at 1.1% of all actions**. Ours
is ~1.9% (0.6 sales over ~31 actions). Two implementations, entirely different
agent architectures, both fail to execute the sell chain.

That is good evidence the trap identified in `docs/diagnosis.md` is a property of
the *game* — the build → connect → beer → sell chain is genuinely hard to reach
by local reasoning — rather than a quirk of our evaluation function. It also
suggests fixing it is where the differentiated value is.

For scale: their 2p LLM agents average 1.4 VP. Our heuristic bot averages 63 in
4p. Low bar, but our bot is plausibly already the strongest Brass agent with
published numbers.

## 4. Brass is not on Board Game Arena

Verified 2026-08-27: Brass game pages return HTTP 500 and the full BGA game list
contains no Brass entry. Roxley's official BGA version has been in private alpha
since mid-2025, and the Steam adaptation was delisted in May 2024.

Consequences:

- **No replay corpus exists.** Validating the engine against thousands of real
  games, or mining human play for heuristics, is off the table.
- **The "live advisor" goal needs rethinking.** There is no online platform to
  advise against. The remaining forms are advising a physical game or a Tabletop
  Simulator session, via manual state entry.

## 5. What the algorithm literature says (and it cuts both ways)

There is no Brass literature, so this comes from the closest published work —
mainly the TAG / Tabletop Games Framework, which implements Power Grid,
Terraforming Mars, Puerto Rico and Dominion.

### One-step lookahead is weak on this class of game

Our bot is a one-step-lookahead (OSLA) agent. That is a *bad* archetype here.

**Power Grid** ([Hornish & Alhassan 2026](http://tabletopgames.ai/assets/pdf/IEEEPowerGrid.pdf)),
1000 self-play episodes per player count:

| players | MCTS | OSLA | random |
| --- | --- | --- | --- |
| 3 | 82.3% | 0.7% | 17.0% |
| 4 | **70.5%** | **0.5%** | 14.4% |
| 6 | 54.4% | 0.4% | 11.3% |

OSLA does worse than random. The authors: Power Grid "rewards longer-horizon
planning, and optimizing only for immediate gains often leads to poor long-term
outcomes." *Caveat: their OSLA used a default reward, not the good leader-based
heuristic their MCTS used, so part of that gap is heuristic quality.*

**Terraforming Mars**
([Gaina, Goodman & Perez-Liebana, AIIDE 2021](https://cdn.aaai.org/ojs/18902/18902-52-22668-1-2-20211004.pdf))
is the clean comparison — MCTS and OSLA share *the same* heuristic. Mean final
score over 100 mirrored runs:

| players | MCTS | OSLA | random |
| --- | --- | --- | --- |
| 2 | 115 | 114 | 93 |
| 4 | **84** | **78** | 62 |

MCTS wins at every count and the margin widens with more players.

That paper also documents an OSLA pathology structurally identical to our
loan-farming: OSLA over-prefers raising Temperature because it "immediately
earn[s] a point, and [is] cheap enough to repeatedly appear in the list of legal
actions."

### But search does not rescue a mis-calibrated evaluation

This is the better-evidenced half, and it decides our ordering.

[MultiTree MCTS, CoG 2022](https://ieee-cog.org/2022/assets/papers/paper_91.pdf)
on **Dominion** — our situation almost exactly. Game score there is "deceptive,"
rewarding short-term points over long-term structure, and *five MCTS variants ×
four parameter settings × three time budgets all found the same poor optimum*:

> "can mean they find a relatively poor optimum and can be beaten by a human
> player, or by MCTS with a game-specific heuristic function that takes these
> factors into account."

What fixed it was a better heuristic, not more search. In
[Skill Depth, CoG 2024](https://tabletopgames.ai/assets/pdf/Goodman2024SkillAnalysis.pdf)
the same lesson appears as a 32x compute advantage failing to compensate for a
bad policy — "a 32ms budget can easily defeat a Classic 1024ms agent."

**Why this applies to us specifically:** our error is *leaf-evaluation bias*, not
a horizon effect. Search fixes horizon errors, where the leaf value is correct
but beyond current depth. For search to discover that starting the sell chain is
good, it would have to expand a complete build → connect → beer → sell, roughly
10-20 of our own plies, i.e. 40-80 nodes deep through opponent turns. Nothing
affordable reaches that, and every shallower node is scored by the same biased
function.

### Under-budgeted search is worse than no search

[Kingdomino, CIG 2018](https://arxiv.org/pdf/1807.04458) — average victory margin
against three greedy opponents; the greedy mirror baseline is -9.0:

| time/ply | 0.1s | 1.0s | 2.0s | 8.0s |
| --- | --- | --- | --- | --- |
| UCT over greedy | **-38.3** | -12.0 | -1.5 | +4.0 |
| flat Monte Carlo | -15.8 | -0.6 | **+4.3** | +9.7 |

UCT wrapped around a greedy evaluator was 29 points *worse* than the evaluator
alone at 0.1s/ply, and needed ~2s/ply to break even. Flat Monte Carlo beat UCT at
every budget.

### If and when we do build search

- **Progressive widening is the load-bearing component in multiplayer.**
  [Baier & Kaisers, CoG 2020](https://ieee-cog.org/2020/papers/paper_193.pdf),
  3-6 players at 250ms/move: vanilla MCTS 46.0% vs minimax baselines, **with PW
  71.9%**, with PW + opponent-move abstraction 79.6%. Plain MCTS *loses* to
  minimax in multiplayer at short budgets.
- **Evaluate leaves with the heuristic; do not roll out to game end.** TAG found
  full rollouts give "weaker and sparser reward signals and lower overall playing
  strength" on long games. Their Power Grid MCTS stores full states and evaluates
  on expansion, with no random rollouts at all.
- **Search buys less as player count rises.** Skill Depth: "In all cases,
  2-player games show a higher ST than 3-player versions of the same game (and
  this reduces further for 4-Players)."
- **Factored/combinatorial action handling** fits our sourcing problem:
  Power Grid used a Conditional Action Tree with a legality mask;
  [naive sampling](https://arxiv.org/abs/1710.04805) treats a combinatorial
  action as separable per dimension and "outperforms the other sampling
  strategies" as branching grows — a natural fit for coal source x iron source
  given a fixed card+location+tile.

### Engine performance is a prerequisite

Independent profiling of our engine: `legal_actions` costs **4.52 ms** at a
mid-game state against **0.08 ms** for clone+apply — 85% of it inside
`legal_networks`, from un-memoised repeated `coal_plans` (~112 calls) and
`distances_from` (~282 calls) per invocation. That caps node expansion at
~200/second.

Kingdomino's UCT needed thousands of iterations per move to beat greedy. So
memoising the network and sourcing computations is a prerequisite for search
being *testable at all*, independent of whether we build it.


## Sources kept out of the repository

Three things this work depended on are deliberately untracked, for licensing
rather than size reasons:

- `tools/vendor/gameData.js` — third-party component transcription with no
  published licence. `tools/extract_gamedata.js` prints the fetch command when it
  is missing. The generated `brassbot/data/brass.json` **is** tracked: component
  costs and VP values are facts about the game, not authored expression.
- `docs/rules_reference_eog.txt` — extracted text of the Esoteric Order of Gamers
  rules summary (orderofgamers.com, Brass: Birmingham v1.2), which states it may
  not be re-posted or repurposed.
- `docs/evidence/*.png` — crops of Roxley's board and player-mat artwork used to
  settle the link-scoring question. `docs/link-scoring.md` states every finding
  in full without them.

## 6. A learned value function: the cheap probe says no obvious headroom

Before building a training pipeline, the question worth answering is whether a
learned function can predict outcomes better than the hand-crafted one **on the
job the evaluation actually does**.

`brassbot/features.py` extracts 45 features per (state, seat), deliberately the
same quantities the evaluation already uses, so a learned function competes on
identical information. Self-play positions were labelled with the seat's final
score, split by game, and a linear model fitted on the training games.

| predictor | across all stages | within game stage |
| --- | --- | --- |
| hand-crafted evaluation | 0.279 | **0.605** |
| linear model, same features | 0.700 | **0.595** |

*(Spearman against final VP, held-out games.)*

**The first column is a trap and the second is the real answer.** Predicting final
VP across all stages is easy -- a Rail Era position already has most of its score
banked -- and the linear model's dominant weight was `era_is_rail` at -47.6, i.e.
it was mostly learning what turn it was. Our evaluation never does that: it ranks
sibling positions inside a single decision, where the stage is identical for every
candidate. Measured on that task, the hand-tuned weights **match a fitted linear
model and slightly beat it**.

So there is no easy win here. What this does *not* rule out:

- **Nonlinearity.** Only a linear fit was tried. A network could find structure a
  weighted sum cannot.
- **Richer features.** These 45 are deliberately the evaluation's own quantities.
  Board topology, per-tile detail, and opponent structure are all absent.
- **Better training data.** Labels come from heuristic self-play, so the target is
  "what the heuristic achieves from here", which caps what can be learned. The
  AlphaZero loop exists to escape exactly that, by regenerating data with the
  improved player.

**Whoever picks this up should re-run the probe with a nonlinear model and richer
features first.** It costs an hour and tells you whether the weeks are worth
spending. Reporting the all-stages number instead of the within-stage one would
have justified the whole project on an artifact.
