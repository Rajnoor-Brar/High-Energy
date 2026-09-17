"""One error type for everything the user can get wrong.

`HepError` carries where the problem is (a config key, a file, a point name) and, when there is one,
a hint that says what to do. `hekit.cli` catches it, prints `render()` and exits 2; nothing else in the
package prints error text.
"""

from __future__ import annotations


class HepError(Exception):
    """A user-facing error: a message, optionally where it came from and what to do about it."""

    exit_code = 2

    def __init__(self, message: str, *, where: str = "", hint: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.where = where
        self.hint = hint

    def render(self) -> str:
        head = f"{self.where}: {self.message}" if self.where else self.message
        return f"{head}\n  hint: {self.hint}" if self.hint else head

    def __str__(self) -> str:
        return self.render()


class NotImplementedYet(HepError):
    """A command that the roadmap has not reached yet."""

    exit_code = 3

    def __init__(self, command: str, step: str) -> None:
        super().__init__(f"`hep {command}` is not implemented yet",
                         hint=f"it arrives in step {step}; see docs/rework/steps/README.md")
        self.command = command
        self.step = step


def did_you_mean(name: str, candidates: object) -> str:
    """"did you mean X?" for a misspelled key or name; empty when nothing is close."""
    import difflib

    close = difflib.get_close_matches(name, [str(item) for item in candidates], n=3, cutoff=0.6)
    return "did you mean " + " or ".join(f"'{item}'" for item in close) + "?" if close else ""
