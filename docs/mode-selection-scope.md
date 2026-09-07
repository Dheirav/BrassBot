# Mode selection — scope

## Where this came from

The Boomforge author described their bot: a hand-built engine that scores every
legal move in estimated VP, considers future VP, searches the rest of its own
two-action turn, is tuned by seeded self-play and mirrored head-to-head tests —
and **chooses between three loose strategies based on the board, merchants,
cards and existing commitments**.

Every line of that describes our bot too, except the last. `pair_search` is the
two-action search. Three disjoint seed blocks with a heterogeneity check is the
mirrored tuning. What we do not have is strategy selection: our bot is one
weight vector applied to every position, conditioned on player count and nothing
else.

## The hypothesis, stated so it can fail

> Some of our weights have an optimum that depends on the board, and a single
> vector is averaging over regimes rather than being right in either.

If true, a weight that measures **null on average** should measure
**positive in one regime and negative in the other**. That is a stronger and
cheaper prediction than "modes will make the bot better", and it can be tested
without building any mode machinery at all.

## Why there is prior reason to believe it

Every conditioning axis we have ever looked at turned out to matter:

| weight | 4p | 3p | 2p |
|---|---|---|---|
| `unflipped` | +2.86 | **-2.90** | -1.76 |
| `doomed_build` | 1.0 | pinned 0.0 | 1.0 |
| `canal_double` | 1.25 | 0.75 (+1.21, 1.8σ) | 0.75 (+0.57, 0.6σ) |

We keep discovering the right number is conditional, and player count is the
only axis we can express it on. `PROFILES` is already a mode selector — it is
just keyed on the one feature we happened to implement.

And we have candidate mixtures sitting in the discard pile. `sell_ready` was
dropped at **-0.13 +- 0.58**: a clean null. A weight worth +2 when a merchant
pays well for your goods and -2 when it does not would measure exactly that.

## The board feature

Nine merchant tiles are shuffled across five locations at setup:

    tiles      blank, blank, any, cotton_mill, manufacturer,
               pottery, manufacturer, any, cotton_mill        (4p)
    locations  shrewsbury vp4 (1)   gloucester develop1 (2)   oxford income2 (2)
               warrington money5 (2)   nottingham vp3 (2)

Beer count is fixed by player count (7 non-blank tiles at 4p) so it is not a
regime. What varies is **which industry sells into which bonus**. Candidate
feature, cheap and static at setup:

```python
def sell_regime(state) -> str:
    """Whether the board pays well for selling. VP merchants are shrewsbury (4)
    and nottingham (3); 'any' slots accept every sellable industry."""
    rich = 0
    for mid in ("shrewsbury", "nottingham"):
        for slot in state.merchants.get(mid, ()):
            if slot.kind != "blank":
                rich += 1
    return "sell_rich" if rich >= 2 else "sell_poor"
```

Exact thresholds are for Stage 0 to settle; the point is that it is a pure
function of the setup, identical for every seat, and known before move one.

## Staging

### Stage 0 — falsify it before building anything  (compute only, no code ships)

Take a weight that measured **null overall** — `sell_ready` is the best
candidate, `merchant_access` the second — and re-run the existing paired duel,
but partition the seeds by `sell_regime` and pool each partition separately.

Reuse the heterogeneity machinery already in `tools/verify-weight.py`: it
computes a chi-square across seed blocks to ask "do these blocks disagree?".
Here the same test asks "do these *regimes* disagree?".

- **Structure exists** if the two partitions differ at chi2 > 3.84 (1 df) with
  each partition's own blocks internally agreeing.
- **Kill** if the partitions agree. Then the averaging story is wrong for this
  feature, and either try one more feature or stop. Cost so far: compute only.

Sizing: a 4p arm of 540 games takes ~28 min measured. Partitioning halves the
games per cell, so ~1100 games an arm for equal power, ~60 min per arm, and two
arms per weight. **~2 h per weight tested.**

### Stage 1 — plumbing, behaviour unchanged  (~half a day)

Add a `MODES` layer resolved once at game start and merged over
`DEFAULTS + PROFILES[n]`, exactly as `PROFILES` is merged today. Ship it with a
single mode whose overrides are empty.

Guards that matter:

- **Resolve the mode once, at game start, and cache it on the bot.** It must not
  be recomputed inside `pair_search` probe states — a mode that changes
  mid-search makes the two halves of a pair incomparable, and probes are copies
  whose contents differ from the real board.
- **Keep it a pure function of public setup state.** Determinism is why a
  180-game block is comparable across weeks and why 4.0σ means anything. Ties
  are broken by generation order here deliberately; do not import Boomforge's
  tie-break randomness with it.
- Verification: mirror the new build against the previous one. Must measure
  0.00 within noise. Anything else means the merge order is wrong.

### Stage 2 — one weight, one split  (~6 h compute)

Split **only the weight Stage 0 identified**. Sweep each side on the tune blocks
(10000+), verify on the validate blocks (20000+), report on the report blocks
(0+) — the existing three-block discipline, unchanged.

Ship only at the standing bar: **>=3σ pooled with blocks agreeing.**

### Stage 3 — extend, only if Stage 2 clears

Add further weights one at a time, each earning its own split. Do not re-tune
the whole vector across modes.

## The real risk, and the guard

Splitting k weights across m modes multiplies the search space by m^k, and this
project's entire discipline exists because a large search space finds gains that
are noise. One weight was shipped today at 4.0σ; four leads were closed because
they could not clear the bar. A mode layer makes it much easier to manufacture
apparent wins.

The guards are non-negotiable and already exist: choose the split on the tune
blocks, confirm on **fresh** blocks the split was not chosen on, require the
per-regime blocks to agree internally, and ship at 3σ. Stage 0 exists precisely
so the machinery is never built unless the conditional structure is measured
first.

## Cost

| stage | compute | code | kill criterion |
|---|---|---|---|
| 0 falsify | ~2 h per weight | none | partitions agree |
| 1 plumbing | ~20 min | ~half a day | mirror vs old != 0 |
| 2 one split | ~6 h | small | < 3σ or blocks disagree |
| 3 extend | ~6 h per weight | small | same |

Stages 0 and 1 are independent and can run in parallel: Stage 0 is compute with
no code change, Stage 1 is code that changes no behaviour.

## What this is not

Not a search deepening. The planner (+14.78 -> +3.09) and MCTS (-4.81, archived)
both tried to buy strength with lookahead and failed. This is the same
evaluation at the same depth, selected differently — the cheapest architectural
change on the table, and the only one the Boomforge description suggests we are
actually missing.
