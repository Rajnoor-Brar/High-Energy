"""The one error type (rank 0).

Every refusal the runner makes is a `HepError`: a message, *where* it applies (a config key, a file,
a point), and a *hint* saying what to do. `cli` catches it, prints `render()`, and exits 2 before
anything ran (or 1 once points have run). Nothing else prints error text.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable


class HepError(Exception):
    def __init__(self, message: str, *, where: str | None = None, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.where = where
        self.hint = hint

    def render(self) -> str:
        lines = [f"hep: {self.message}"]
        if self.where:
            lines.append(f"  where: {self.where}")
        if self.hint:
            lines.append(f"  hint:  {self.hint}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.render()


def did_you_mean(word: str, choices: Iterable[str]) -> str | None:
    """A hint for a misspelt key or name, or None when nothing is close."""
    close = difflib.get_close_matches(word, list(choices), n=3, cutoff=0.6)
    if not close:
        return None
    return "did you mean " + " or ".join(f"'{c}'" for c in close) + "?"
