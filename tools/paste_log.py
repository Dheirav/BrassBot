"""Paste a Boomforge game log straight in, and have it saved and read back.

    PYTHONPATH=. .venv/bin/python tools/paste_log.py

Paste the log panel, then press Ctrl-D on a blank line. The log is saved under
logs/ with a timestamp and immediately parsed, so you find out whether it read
cleanly while the game is still in front of you.

Piping works too, which is handy for a file you already have:

    PYTHONPATH=. .venv/bin/python tools/paste_log.py < game.txt
    pbpaste | PYTHONPATH=. .venv/bin/python tools/paste_log.py --name vs-bots

Why keep them: every strong-play reference this project has is a quote from a
guide or an agent's write-up, and two of those turned out to be
strategy-conditional claims applied as universal law. A real log is evidence
about what was actually played -- and any complete game, however it was played,
also checks that our engine accepts every move a human legally made.
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tools.import_log import parse, summarise  # noqa: E402

LOGS = pathlib.Path(__file__).resolve().parent.parent / "logs"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--name", help="label for the file, e.g. 'vs-bots-4p'")
    ap.add_argument("--no-save", action="store_true", help="parse without keeping it")
    args = ap.parse_args(argv)

    if sys.stdin.isatty():
        print("Paste the game log, then Ctrl-D on a blank line.\n"
              "(The whole log panel, oldest or newest first -- either is fine.)\n",
              file=sys.stderr)
    text = sys.stdin.read()
    if not text.strip():
        print("Nothing pasted.", file=sys.stderr)
        return 1

    if not args.no_save:
        LOGS.mkdir(exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        label = f"-{args.name}" if args.name else ""
        path = LOGS / f"{stamp}{label}.log"
        path.write_text(text, encoding="utf-8")
        print(f"\nsaved to {path.relative_to(LOGS.parent)}\n")

    moves, players, scores = parse(text)
    if not moves:
        print("Parsed no moves. The format may have changed -- the lines above\n"
              "beginning [unparsed] show what it could not read.", file=sys.stderr)
        return 1
    summarise(moves, players, scores)
    return 0


if __name__ == "__main__":
    sys.exit(main())
