"""The bot must play a seed identically in every process.

Move generation iterates sets of town ids and of Industry members. Python
randomises string hashing per process, so before those orders were sorted the
same seed produced a different game in a different process: over 12 games the
mirror mean came out 104.71, 105.35 and 104.75 under three hash seeds. That
breaks the project's determinism requirement outright, and it also silently
widened every measurement ever taken.

PYTHONHASHSEED can only be set before the interpreter starts, so this has to
spawn subprocesses -- an in-process test cannot see the bug at all.
"""
import os
import subprocess
import sys

SCRIPT = """
from brassbot.bots import make
from brassbot.engine import apply_action, legal_actions
from brassbot.state import new_game

picks = []
# Full games, not openings: with an empty network the build options come from
# an ordered dict, so the first several moves stay stable even when the bug is
# present -- the divergence needs a player who already owns something. And it
# is seed-dependent, so this sweeps several. On the unsorted engine seed 0 came
# out [119, 107, 126, 107] under one hash seed and [95, 127, 117, 93] under
# another; seed 77, the obvious first choice, never diverged at all.
for seed in (0, 1, 2):
    state = new_game(4, seed=seed)
    bot = make("heuristic")
    while not state.finished:
        actions = legal_actions(state)
        action = bot.choose(state, actions)
        picks.append(f"{seed} {len(actions)} {action!r}")
        apply_action(state, action)
    picks.append(f"final {seed} {[p.vp for p in state.players]}")
print("\\n".join(picks))
"""


def _run(hashseed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=hashseed, PYTHONPATH=".")
    out = subprocess.run([sys.executable, "-c", SCRIPT], env=env,
                         capture_output=True, text=True, timeout=600)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_the_same_seed_plays_identically_under_different_hash_seeds():
    baseline = _run("0")
    assert baseline.count("\n") > 150, "the probe did not play full games"
    for hashseed in ("1", "12345"):
        assert _run(hashseed) == baseline, (
            f"move generation differs under PYTHONHASHSEED={hashseed}; "
            "an unsorted set is leaking process-dependent order into play"
        )
