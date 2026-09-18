"""Stamping a result so it still identifies itself after it leaves its directory (07 §2).

A YODA file gets copied into a talk, mailed to a collaborator, dropped into a directory of other
people's curves. Once that happens the `provenance.json` next to it is gone, and the file has to say
for itself which point it is and what produced it. So three annotations go onto `/_EVTCOUNT`, which
every Rivet run writes:

| Annotation | Value |
|---|---|
| `HekitPoint` | the point name |
| `HekitHash` | `sha256:…`, the identity of the inputs (03 §5) |
| `HekitGit` | the repository state, `0a10209` or `0a10209-dirty` |

They are added **after** the run, by reading and rewriting the file with the Python `yoda` module,
because Rivet owns the file while it is running. Reading and rewriting a YODA loses nothing — but it
does reset the locale (00/B29), which is why that is saved and restored here.

Stamping never fails a run: if `yoda` is missing or the file cannot be rewritten, the result stays
exactly as it was and the caller is told.
"""

from __future__ import annotations

import contextlib
import locale
from pathlib import Path
from typing import Any

from ..results.layout import marked
from .git import git_state

COUNTER = "/_EVTCOUNT"
RAW_COUNTER = "/RAW/_EVTCOUNT"
POINT = "HekitPoint"
HASH = "HekitHash"
GIT = "HekitGit"


def git_label(state: dict[str, Any] | None = None) -> str:
    """`0a10209`, `0a10209-dirty`, or "unknown" outside a repository."""
    state = state if state is not None else git_state()
    sha = state.get("sha")
    if not sha:
        return "unknown"
    return f"{sha}-dirty" if state.get("dirty") else str(sha)


@contextlib.contextmanager
def _locale_kept():
    """YODA's reader sets LC_ALL to "C" and does not put it back (00/B29), which breaks the next
    non-ASCII write in the same process."""
    saved = locale.setlocale(locale.LC_ALL)
    try:
        yield
    finally:
        with contextlib.suppress(locale.Error):
            locale.setlocale(locale.LC_ALL, saved)


def annotations(point: str, point_hash: str, *, git: str | None = None) -> dict[str, str]:
    return {POINT: point, HASH: point_hash, GIT: git if git is not None else git_label()}


def stamp(path: Path, point: str, point_hash: str, *, git: str | None = None) -> bool:
    """Add the annotations to a YODA file in place. Returns False when it could not be done."""
    path = Path(path)
    if not path.is_file():
        return False
    try:
        import yoda
    except ImportError:                                  # pragma: no cover - yoda is always present here
        return False

    marks = annotations(point, point_hash, git=git)
    try:
        with _locale_kept():
            objects = yoda.read(str(path))
            targets = [objects[name] for name in (COUNTER, RAW_COUNTER) if name in objects]
            if not targets:
                return False
            for target in targets:
                for key, value in marks.items():
                    target.setAnnotation(key, value)
            # tmp + rename, like every other write (D22): a stamp must not be able to truncate a result.
            temporary = path.with_name(marked(path.name, "tmp"))
            yoda.write(list(objects.values()), str(temporary))
            temporary.replace(path)
    except Exception:
        with contextlib.suppress(OSError):
            path.with_name(marked(path.name, "tmp")).unlink(missing_ok=True)
        return False
    return True


def read_stamp(path: Path) -> dict[str, str]:
    """The annotations on a stamped file, `{}` when there are none."""
    try:
        import yoda
    except ImportError:                                  # pragma: no cover
        return {}
    try:
        with _locale_kept():
            objects = yoda.read(str(path))
    except Exception:
        return {}
    for name in (COUNTER, RAW_COUNTER):
        target = objects.get(name)
        if target is None:
            continue
        found = {key: target.annotation(key) for key in (POINT, HASH, GIT)
                 if target.hasAnnotation(key)}
        if found:
            return found
    return {}
