# The playstyle prompt

A prompt that makes an LLM agent play in the style measured in
`docs/human-playstyle.md`. Its purpose is to give us a repeatable opponent that
plays like a strong human, so the bot can be measured against that style on
demand rather than waiting for real games.

**Measured, and the result is a warning.** Four Sonnet agent games against our
heuristic, all bot wins:

| brief given to the agent | agent score | bots |
|---|---|---|
| "play to win", no style at all | 98 | best 138 |
| "play to win", no style at all | 98 | 133 / 124 / 113 |
| link-heavy extract only | 93 | 132 / 136 / 136 |
| **the full 13 rules below** | **56** | 126 / 126 / 139 |

More rules made the agent play *worse*, monotonically. The fault is in the
extraction, not the player: several rules below are descriptive statistics
("humans sell 0-2 times a game") rewritten as imperatives ("sell rarely"), and
an agent obeying that skipped a Sell that would have flipped two tiles before
the era wipe destroyed them. Rules 6, 9 and 12 now carry the caveat that makes
them safe to obey. Treat the rest the same way: they describe what these players
*did*, on their boards, and a rule that a board makes impossible is not a rule
to force.

Substitute a fresh SEED each run and keep the seed in the report, so the same
board can be replayed with the bot in the agent's seat.

---

Play a full 4-player game of Brass: Birmingham against three bot opponents,
following the playstyle below. Your objective is to win, but you must win *in
this style* -- it is the style being tested, not your own judgement. Where the
style and a tempting alternative conflict, follow the style unless the move is
illegal or obviously self-destructive.

    cd /home/dheirav/Code/BrassBot
    PYTHONPATH=. .venv/bin/python tools/play.py new --seed SEED --out /tmp/gSEED.pkl
    PYTHONPATH=. .venv/bin/python tools/play.py show /tmp/gSEED.pkl
    PYTHONPATH=. .venv/bin/python tools/play.py move /tmp/gSEED.pkl <index>

You are seat 0. Play to the end, about 31 actions. `show` prints banked VP and
"VP if scored now" for every seat -- judge position by the projected figure,
since banked VP is near zero for everyone mid-canal.

## The core

1. **Links decide the game.** Finish with 10-11. These players average 5.70 VP
   per link against the bots' 4.50 -- build where icons are already dense.
2. **Take double rails relentlessly** -- 5-6 a game against the bots' 2-3. Two
   links for one action. An action is worth ~4.6 VP, so this is nearly free.
3. **Drink other people's beer.** A double rail's beer cannot come from a
   merchant, only from a brewery -- yours anywhere in your network, or **a
   connected opponent's**. One logged game took five doubles having built no
   brewery at all. When placing a link, ask what brewery it reaches, not only
   what it scores.

## Industry

4. **Never build cotton.** Zero across all six games.
5. **Manufacturer deep, not wide.** Few built, climbed to level 4+. L3 and L7
   are the only sellable tiles needing NO beer; L7 is 9 VP.
6. **Iron early** -- first quarter of your actions. A works built into a short
   market sells its cubes on placement and flips at once. *If the board will not
   allow it, drop it:* an iron works costs coal, and coal off the market needs a
   merchant connection you may not have yet. This was mechanically impossible
   for an entire opening on one tested board.
7. **Coal opportunistically** -- when the market has a deficit or you have a
   spot for it. Otherwise skip.

## Sequencing

8. **Pair a build with its link in the same turn.** Your two actions are the
   only window no opponent can interrupt. About half your turns.
9. **Develop then build**, never build then develop -- and develop *early*. A
   develop in your last two Canal-Era turns is too late to build on top of.
10. **Clear level-1 tiles before the Canal Era ends.** They are canal-only:
    carry one across and that industry is blocked until developed away.

## What not to chase

11. **Ignore Canal-Era VP.** It ranged 13-45 across five wins, and the highest
    canal score finished last in two of six games.
12. **Sell rarely** -- 0-2 a game; two wins had none at all. **This is a
    consequence, not an order.** These players sell little because they convert
    through links instead. An unflipped tile scores nothing and is removed at
    the era boundary anyway, so if the Canal Era is ending and a single Sell
    flips tiles that would otherwise be swept away, take it -- that is not a
    breach of the style, it is what makes the rest of it affordable.
13. **Take the industry nobody is contesting.** A contested pottery flips 44% of
    the time, an uncontested one 87%.

## Report

Final scores for all four seats, the seed, and then: double rails taken, links
held at the end, whether and how often you drank an opponent's beer, whether you
skipped cotton -- and **any rule that proved impossible or actively bad on this
board**. That last part matters most.
