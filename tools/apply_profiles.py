"""Write tuned per-format weights into HeuristicBot.PROFILES.

Only applies a format whose tuning run actually held up on the validation seed
block. A run that gained on its own seeds and not on unseen ones is noise, and
adopting it makes the bot quietly worse -- which has already happened once here.

    PYTHONPATH=. .venv/bin/python tools/apply_profiles.py            # dry run
    PYTHONPATH=. .venv/bin/python tools/apply_profiles.py --write
"""
import argparse
import json
import pathlib
import re
import sys

from brassbot.bots.heuristic import HeuristicBot

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "brassbot/bots/heuristic.py"


def load(players: int):
    path = pathlib.Path(f"tuned_weights_{players}p.json")
    if not path.exists():
        return None, f"no {path}"
    data = json.loads(path.read_text())
    if not data.get("held_up"):
        start = data.get("validation_start", 0.0)
        tuned = data.get("validation_tuned", 0.0)
        noise = data.get("validation_noise", 0.0)
        return None, (f"rejected: validation {tuned:.1f} vs {start:.1f} starting "
                      f"(+{tuned - start:.1f}, noise +-{noise:.1f})")
    # Store only what actually differs from the defaults, so the profile reads
    # as "what this format wants changed" rather than a wall of repeated numbers.
    diff = {k: v for k, v in data["weights"].items()
            if abs(v - HeuristicBot.DEFAULTS[k]) > 1e-9}
    return diff, f"accepted: validation +{data['validation_tuned'] - data['validation_start']:.1f}"


def render(profiles: dict[int, dict]) -> str:
    if not profiles:
        return "    PROFILES: dict[int, dict] = {}\n"
    lines = ["    PROFILES: dict[int, dict] = {"]
    for players in sorted(profiles):
        body = ", ".join(f'"{k}": {v:.4g}' for k, v in sorted(profiles[players].items()))
        lines.append(f"        {players}: {{{body}}},")
    lines.append("    }")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="edit the source file")
    args = ap.parse_args(argv)

    profiles = {}
    for players in (2, 3, 4):
        diff, why = load(players)
        print(f"{players}p: {why}")
        if diff:
            print(f"     {diff}")
            profiles[players] = diff

    block = render(profiles)
    print("\nwould write:\n" + block)
    if not args.write:
        print("(dry run -- pass --write to apply)")
        return 0

    text = SOURCE.read_text()
    pattern = re.compile(r"    PROFILES: dict\[int, dict\] = \{.*?\n(?:    \}\n)?",
                         re.DOTALL)
    match = pattern.search(text)
    if not match:
        print("could not find the PROFILES block", file=sys.stderr)
        return 1
    SOURCE.write_text(text[:match.start()] + block + text[match.end():])
    print(f"wrote {len(profiles)} profile(s) into {SOURCE.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
