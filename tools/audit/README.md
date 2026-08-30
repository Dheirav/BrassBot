# Measurement instruments

These are the tools that produced every evaluation win the bot has. They exist
because the alternative — inventing a weight term to patch an observed symptom —
has been tried eleven times and measured at or below zero every time. Everything
that worked came from measuring what a term is actually **paid** and comparing
it against what the bot believes it is worth.

They were written by audit agents in a scratch directory that gets cleaned up.
Kept here because rebuilding them costs about 12,000 games.

Run them with the repo on the path:

    PYTHONPATH=. OMP_NUM_THREADS=1 .venv/bin/python tools/audit/duel.py 240 0 <base> <variant>

`OMP_NUM_THREADS=1` matters: without it numpy oversubscribes and eight workers
on eight cores drive the load average past 30.

## duel.py — seat-balanced 2v2

**Use this before believing any magnitude.** The usual 1-variant-vs-3-baselines
harness flatters the odd seat by about +0.5 VP for *any* perturbation: three
deliberately near-neutral placebos measured +0.74, +0.39 and +0.47. The odd seat
gains simply by not contending for the same slots as three copies of itself.

This runs the six balanced seat pairings so every seat is the variant in exactly
half of them, which cancels the bias. It has cut 1v3 results by 2-3x repeatedly.
Report both the VP delta and the win share — at 240 games the win share is the
steadier of the two.

## inject.py — exogenous grants

Hands one seat £X, or +N income levels, or +N VP at a chosen round, and pairs
against a control on identical seeds. This is what a resource is actually paid in
final VP, independent of whether the bot knows how to use it.

Its calibration control is what makes the rest trustworthy: granting +10 VP
returns +9.53 +- 0.66 final VP, so the outcome scale really is VP and any term
can be quoted against it.

Two standing cautions. The windfall value of a resource is **not** the weight it
should carry — the weight sets terms of trade, and an evaluator that loves cash
refuses to spend it (`money` priced at its measured value scores -21.5). And
these corrections do not stack: four knobs that all mean "cash is underpriced"
should not all be turned.

## forced.py / attrib.py — what an action is worth

`forced.py` overrides a single decision (with a Pass, with the best action of a
given type, with the Nth-ranked candidate) and plays the rest normally on the
same seed. Because the engine is deterministic, the score difference is caused
by the override. Pin `ProbeBot.ranked()` against `HeuristicBot.choose` before
trusting a run — it should reproduce a plain game exactly.

This gives the exchange rate everything else should be priced in: **one action is
worth 4.59 +- 0.67 VP**, and one evaluation unit is worth **0.76 VP**.

`attrib.py` books every point back to the action that earned it, by patching
`score_era`, `_merchant_bonus`, `_apply_build` and `flip_tile` in the measuring
process only. It reconciles to the exact final score. Note the enablement ledger
splits each point among the actions that were strictly required for it, which is
a modelling choice, not a measurement.

## trace.py — decision traces

Records cash, legal-action counts, and a counterfactual re-generation of
`legal_actions` with extra money, to find what money actually gates. This is how
we learned that option-gating stops dead at £20 while the outcome value of a
pound runs to £97 — the two halves of the story disagreeing is what located the
`liquidity_scale` error.

## mat_probe.py — instrumented self-play

Per-seat round-boundary snapshots: the mat's next tile per industry, every build
tagged with the VP it actually banks at era scoring, `links_left`, the blocked
set, and `player_value` for every seat. Use it to ask whether an estimator has
any *shape* worth keeping: within (industry, era, round), correlate the estimate
against what actually gets banked. `mat_potential` scores +0.014 there, which is
why only its level was changed and not its form.

## Three failure modes these have caught

- **A result that replicates on two blocks and dies on the third.** `scout_bias`
  was +2.31 on tune and +3.31 on validation, then +0.36 on report. Keep the three
  seed blocks disjoint and always hold one out.
- **Two arms that secretly share a configuration.** Always run a null arm — the
  defaults respelled, or a bias of 1e-12 routed through the new code path. It
  must return 0.00 +- 0.00.
- **The repo moving underneath a long run.** An engine fix landing mid-audit
  shifted a control mean by 0.15 VP on identical seeds. For anything that runs
  for hours, `git archive HEAD` into scratch and measure against the snapshot.
