# Where to spend effort next — SWOT for each option

Written 2026-08-29, after the planner reached 133 VP at an 83% win rate.

## The numbers every option is judged against

| | 4p mean | win% |
| --- | --- | --- |
| heuristic (1-ply) | 107.5 | 25% |
| MCTS 600 | 117.8 | 42% |
| **planner (beam, re-planning)** | **133** | **83%** |
| human tournament median | 158 | - |
| human tournament ceiling | 184 | - |

Remaining gap to a median tournament win: **~25 VP**.

Two facts constrain everything below.

**We cannot measure small changes.** Per-game SD is ~15, and at 24 games per arm
the smallest detectable effect is **8.7 VP**. A genuine 3 VP improvement needs
200 games an arm; 2 VP needs 450. Most real improvements are invisible to us.

**The planner converts compute into VP, and nothing else did.** MCTS saturated at
300 iterations and got *worse* when made deeper. The beam improved from 115 to
143 as width went 8 -> 40. This is the first algorithm here with a real appetite
for hardware.

---

## Option 1 — Rust port of the engine and planner

**Strengths.** 30-50x is realistic for this workload; it is almost all tile and
card structs, cloning, and tight loops. Profiling says the cost is `clone` and
`apply_action`, which is exactly what a systems language makes cheap. Ownership
rules make the beam's heavy state-copying hard to get subtly wrong -- and a
silent aliasing bug in a cloner would corrupt every measurement without failing a
test. Cargo needs no build engineering.

**Weaknesses.** Two to four weeks. The rules engine is 199 tests' worth of
subtle, hard-won behaviour -- eleven bugs were found by agents *playing*, not by
tests, so a port can reintroduce exactly the class of bug the tests do not catch.
Python stays as the harness, so there are two codebases and an FFI seam.

**Opportunities.** Raises the measurement ceiling: 30x turns "can detect 8.7 VP"
into "can detect ~2 VP", which is the band most real improvements live in. Makes
beam width 40+ and multi-world determinization affordable. A clean engine is also
the natural artifact to open-source.

**Threats.** Porting a moving target -- the engine has changed materially in the
last day. Effort spent on speed is effort not spent on strength, and the gap to
158 is a *play* problem, not a throughput one. Risk of a subtly divergent port
that scores differently and is never noticed, which cross-checking against the
Python engine on identical seeds must prevent.

## Option 2 — C++ port

**Strengths.** Same 30-50x. Mature parallelism (OpenMP, TBB) if the search is
ever parallelised within a game. If you are already fluent, faster to write.

**Weaknesses.** Nothing protects you from the aliasing and lifetime mistakes that
a state-cloning search invites. Build tooling is work Cargo does for free.

**Opportunities / Threats.** As Rust. **The language choice is worth far less
than porting the right algorithm** -- both hit the same ceiling, so pick on
fluency, not on theory.

## Option 3 — Hybrid: native core, Python harness

Port only `state`, `engine` and the beam inner loop as an extension; keep bots,
evaluation, measurement and analysis in Python.

**Strengths.** Most of the speed for a fraction of the work -- the profile is
concentrated in exactly these modules. Keeps the whole measurement apparatus,
which is the part of this project that has repeatedly saved us. Incremental: it
can be abandoned halfway with the Python still working.

**Weaknesses.** FFI crossings per node can eat the gain if the boundary is drawn
badly; the boundary must be "run the whole search natively", not "call apply from
Python". Two languages in one hot path is harder to profile.

**Opportunities.** The engine is the stable, well-tested part and the natural
thing to freeze in a faster language. Evaluation and bot logic -- the parts still
changing weekly -- stay malleable.

**Threats.** Half-measures that deliver 3x instead of 30x and cost a week.

## Option 4 — Stay in Python and optimise

Transposition table (**22% of scored states are repeats**, measured), fewer
clones, cheaper `legal_actions`.

**Strengths.** Days, not weeks. No new language. The transposition table is the
right design regardless, and carries into any port.

**Weaknesses.** Optimism about ceilings has been wrong here twice today: the
"cheap opponent" idea saved 10% and cost 3.3 VP, and delta evaluation bought 26%
and zero strength. Realistically 1.5-2.5x total -- which does **not** move the
8.7 VP detection floor meaningfully.

**Opportunities.** Cheap, and it de-risks a port by settling the algorithm first.

**Threats.** Spending a week to arrive back at "we need the port".

## Option 5 — More agent playtests

**Strengths.** **The single highest-yield activity in this project: eleven real
rules bugs across two rounds, none of which self-play could find.** Agents score
150-177 where our bots score 107-133, so they also generate strategy we do not
have. Cheap, parallel, needs no new infrastructure.

**Weaknesses.** Finds *correctness*, not strength -- most fixes were symmetric
and moved the mirror by nothing. Yield should fall as the obvious bugs go.
Reports need verification: one agent's "eras are a round short" was wrong, and
acting on it would have broken a correct engine.

**Opportunities.** Three are running now, including the first ever against the
planner. An agent that beats it tells us where it plays badly -- which is
diagnosis, and diagnosis is what produced the planner in the first place.

**Threats.** Diminishing returns; comfort in an activity that reliably produces
*findings* rather than VP.

## Option 6 — Learned value function, take two

MCTS-backed labels instead of heuristic outcomes; accumulate data across rounds
rather than replacing it.

**Strengths.** The only remaining idea with a large upside. Both failure causes
are understood and both fixes are standard.

**Weaknesses.** Attempt one lost by 18 VP. A better offline predictor played
*worse*, so the metric we would tune against is not trustworthy. A week.

**Opportunities.** A strong evaluation would lift the planner too -- it prunes
with the evaluation, so the two compound.

**Threats.** ~30-40% odds by my estimate, after six consecutive closed levers.

## Option 7 — Consolidate and stop

**Strengths.** The engine is correct at 2/3/4p, deterministic, 199 tests, eleven
bugs fixed. The bot beats everything we have built. That is a real artifact.

**Weaknesses.** 25 VP short of a median tournament player.

**Threats.** Stopping just as the first genuinely scaling approach appeared.

---

## Recommendation

**Do 5 and 3, in that order, and skip 1/2 as first moves.**

1. **Agent playtests now** (running). Highest measured yield, and the
   planner-facing one is diagnosis, which is what has actually worked here.
2. **Hybrid native core** rather than a full port. The profile is concentrated in
   `state.clone` and `engine.apply_action`; port those and the beam loop, keep
   the measurement apparatus that has caught every mistake in this project.
   Build the transposition table first -- it is a design change, and design
   changes belong in the language you can still iterate in.
3. **Then reconsider the full port** with a settled algorithm and a known target.

The reason not to start with a full port: **the gap to 158 is a play problem, not
a throughput one**, and every large gain here has come from measurement or from
agents playing, never from making the existing thing faster. Speed buys better
*experiments*, which is real and is why the port belongs on the list -- but it
buys no VP by itself.

If you would rather have one number than a plan: the planner at width 40 with
multi-world determinization is the most likely single source of the next 10 VP,
and it is unaffordable in Python today. That is the strongest argument for
porting, and it is an argument for porting *the planner*, not the whole project.
