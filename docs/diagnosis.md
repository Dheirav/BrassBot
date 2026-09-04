# Why the heuristic bot scores 63, not 200

> **Superseded, 2026-09-04.** This is the record of a measurement taken on
> 2026-08-27, when the bot's 4p mirror mean was 61.4. It now scores **131.3**
> (SD 12.4), so every absolute figure below is historical. The *shares* it
> reports are what remain useful, and the leftover-cash finding drove real
> changes. Current standings live in `NEXT.md`.

Measured 2026-08-27 with `tools/diagnose.py heuristic -n 80 -w 8` — the tuned
heuristic bot in a mirror match, 80 games, seat 0.

## Where its points come from

Mean 61.4 VP.

| Source | VP | share |
| --- | --- | --- |
| money (£10 = 1 VP) | 16.4 | **26.8%** |
| link, Rail Era | 15.3 | 24.9% |
| industry, Rail Era | 13.4 | 21.9% |
| link, Canal Era | 9.6 | 15.7% |
| industry, Canal Era | 5.9 | 9.7% |
| merchant bonuses | 0.7 | 1.1% |

A quarter of the score is **leftover cash** — roughly £164 unspent per game.

For contrast, a 200-point game is mostly flipped industry: something like 100 VP
of tiles, 55 of links, a handful of money. Ours is upside down.

## What it does

| | per game |
| --- | --- |
| tiles built | 8.4 |
| tiles **sold** | **0.6** |
| tiles developed | 4.6 |
| links (canal / rail) | 3.2 / 5.0 |
| final income | **−7.7** |

Highest tile level ever built, averaged over games:

| industry | level |
| --- | --- |
| coal mine | 2.4 |
| iron works | 2.0 |
| brewery | 1.9 |
| manufacturer | **0.5** |
| cotton mill | **0.3** |
| pottery | **0.1** |

**It does not play half the game.** Cotton mills, manufacturers and potteries —
the entire sellable, high-VP side of the board — are essentially never built.
Pottery, which tops out at 20 VP for a single tile, appears in about one game in
ten. It sells 0.6 tiles per game.

## The action mix, and the smoking gun

| action | per game | |
| --- | --- | --- |
| **Loan** | **9.6** | the most-used action in the game |
| Build | 8.4 | |
| Network | 7.2 | |
| Develop | 3.2 | |
| Scout | 1.4 | |
| Pass | 0.7 | |
| Sell | 0.6 | |

Broken down by phase, loans as a share of all actions taken:

| phase | loan share | builds |
| --- | --- | --- |
| canal r1–r2 | 0% | 66 |
| canal r3–r8 | 6–34% | 217 |
| **rail r2–r5** | **47–66%** | 62 |
| rail r6–r8 | 32–39% | 37 |

In the middle of the Rail Era — the half of the game holding every expensive
tile — **two of every three actions is a loan**. Builds collapse from 51 in a
single canal round to 15–20 per rail round.

This is not an endgame cash grab. It is a mid-game collapse.

## Root cause: a self-fulfilling trap

The chain that produces real points in Brass is long: build a cotton mill, build
a link to a merchant that accepts cotton, secure beer, *then* sell. Only the
last step pays anything. Every step before it is pure cost.

A 1-ply evaluation sees each step in isolation, so:

1. A sellable tile is credited at `unflipped = 0.25` of its value, because the
   bot has no way to know a sale is coming.
2. So building one looks like a net loss, and it doesn't.
3. With no sellable tiles, Sell is almost never legal — 0.6 per game.
4. With no sales, the only VP left is resource tiles that auto-flip into the
   market, plus links.
5. Money becomes the cheapest remaining VP, and Loan is the cheapest way to get
   money. So it loans.

The bot is being *rationally pessimistic about itself*: it declines to build
sellables because it correctly predicts it will never sell them. Step 2 and
step 3 hold each other in place.

Worked example, Rail Era round 5 (`rounds_left = 3`) under the tuned weights:

* **Loan** → +£30 × 0.225 = **+6.75**, minus 3 income levels × 3 rounds ×
  (0.225 + 0.1125) = −3.04. Net **+3.7**.
* **Build a cotton mill II** (£14 + coal) → −3.15 for the money, plus
  0.25 × (5 VP + income promise) ≈ +1.9. Net **−1.5**.

Loaning wins, every turn, and it is the evaluation that says so.

## Two things the tuner got wrong, and why

Tuning drove `debt` from 0.45 down to 0.1125 — it *learned* that ignoring debt
wins, because under this evaluation loans are reliably positive. And `money` sits
at 0.225, more than double the 0.10 that a pound is actually worth at scoring.
Anything above 0.10 is a bet that the cash gets spent productively; the bot
leaves £164 on the table, so that bet is simply false.

This is proxy-optimisation: the weights were tuned against score, and score
rewarded the degenerate line because the evaluation could not see the good one.
More tuning will not fix it — the tuner is working correctly on a broken
objective.

## What to do, in order

1. **Make selling visible to the evaluation.** Credit an unflipped sellable tile
   near its full value when a sale is *actually available now* (connected
   merchant that accepts it, plus reachable beer), and low when it is not. Add
   terms for merchant connectivity and beer access so building *toward* a sale
   registers as progress. This attacks the trap at step 1–2, where it is cheapest
   to break.
2. **Set `money` to its true terminal value (0.10)** and let the liquidity term
   carry "can I still act". Re-tune `debt` afterwards — its current value was
   fitted to a world where loans were good.
3. **Re-run this diagnostic.** If sales and pottery/cotton levels rise and loans
   fall, the trap is broken and it is worth tuning again.
4. **Only then consider search.** If the bot still cannot execute the sell chain
   with the evaluation fixed, the problem really is planning depth, and PIMC or
   ISMCTS is the answer. Right now search would spend its budget exploring a
   position the evaluation misjudges.

## Reproducing

```bash
PYTHONPATH=. .venv/bin/python tools/diagnose.py heuristic -n 80 -w 8
PYTHONPATH=. .venv/bin/python tools/diagnose.py heuristic -o greedy -n 80 -w 8
```
