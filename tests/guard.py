"""The test-safety guard itself: snapshot the protected trees and report what changed (00/B18).

Used by tests/conftest.py (as an autouse fixture over every test directory) and tested directly on a
fake tree in tests/python/test_skeleton.py - planting a write in the real configs/ is what it forbids.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
#: Trees that tests must leave untouched.
PROTECTED = ("results", "configs")


def snapshot(roots: tuple[Path, ...]) -> dict[str, tuple[int, int]]:
    """path -> (mtime_ns, size) for every file **and directory** under `roots`.

    Directories are included so that a write which cleans up after itself is still caught: creating and
    removing a file leaves the file set unchanged but bumps the parent directory's mtime.
    """
    state: dict[str, tuple[int, int]] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in (root, *root.rglob("*")):
            try:
                info = path.stat()
            except OSError:          # vanished while walking: recorded as a change below
                state[str(path)] = (-1, -1)
                continue
            if path.is_dir():
                state[str(path) + "/"] = (info.st_mtime_ns, -1)
            elif path.is_file():
                state[str(path)] = (info.st_mtime_ns, info.st_size)
    return state


def changes(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]]) -> list[str]:
    """Human-readable list of additions, removals and modifications."""
    found = [f"added {path}" for path in sorted(set(after) - set(before))]
    found += [f"removed {path}" for path in sorted(set(before) - set(after))]
    found += [f"modified {path}" for path in sorted(set(before) & set(after)) if before[path] != after[path]]
    return found


