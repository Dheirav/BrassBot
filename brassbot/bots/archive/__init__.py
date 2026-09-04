"""Bots that no longer ship, kept runnable rather than deleted.

Nothing here is in `REGISTRY`, so the harness will not select it and no
measurement can quietly include it. It stays importable and under test so it
does not rot into something that cannot be revived, and so the reasoning that
retired it can still be re-run rather than merely believed.

Retiring something is a claim, and a claim needs a number. Each module's
docstring carries the measurement that retired it.
"""
