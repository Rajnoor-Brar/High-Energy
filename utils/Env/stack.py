#!/usr/bin/env python3
"""utils/Env/stack.py — utils/Env/stack.toml read (audit 1 B7, V78).

    stack.py --bash      the probes for utils/Env/flags.sh: TOOLS=(…), STACK=<sha>, probe/dir_lib lines
    stack.py --versions  each entry's version, as `hep status --stack` prints it

Importable too (the runner's `[identity] version = "stack:<name>"`): `entries()`, `version(name)`.
Standard library only.
"""

from __future__ import annotations

import hashlib
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

FILE = Path(__file__).with_name("stack.toml")


def entries() -> dict[str, dict]:
    return tomllib.loads(FILE.read_text(encoding="utf-8"))


def expand(text: str) -> str:
    """Shell text (`${A:-${B-}/x}`) as bash expands it."""
    done = subprocess.run(["bash", "-c", f'printf %s "{text}"'], capture_output=True, text=True)
    return done.stdout


def version_command(name: str) -> list[str]:
    """Its version command; for a { file = … } version, a command that prints that file's line."""
    entry = entries().get(name)
    if entry is None:
        raise KeyError(f"stack.toml has no [{name}]")
    spec = entry.get("version", [])
    if isinstance(spec, dict):
        return ["grep", "-m1", "-i", "version", expand(spec["file"])]
    return list(spec)


def version(name: str) -> str:
    """The first line its version command prints, "" without one, "?" when it cannot be run."""
    command = version_command(name)
    if not command:
        return ""
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return "?"
    text = (done.stdout or done.stderr).strip()
    return text.splitlines()[0] if text else ""


def bash() -> str:
    """flags.sh's probes, in the file's order."""
    stack = entries()
    tools = list(dict.fromkeys(e["flags"][0] for e in stack.values() if e.get("flags")))
    lines = [f"TOOLS=({' '.join(shlex.quote(t) for t in tools)})",
             f"STACK={hashlib.sha256(FILE.read_bytes()).hexdigest()[:16]}",
             f"NAMES=({' '.join(n for n, e in stack.items() if e.get('flags') or e.get('dir'))})",
             "probes() {"]
    for name, entry in stack.items():
        if entry.get("flags"):
            lines.append(f"    probe {name} {' '.join(shlex.quote(a) for a in entry['flags'])}")
        elif entry.get("dir"):
            lines.append(f'    dir_lib {name} "{entry["dir"]}" {shlex.quote(entry["lib"])}')
    lines.append("}")
    return "\n".join(lines) + "\n"


def versions() -> list[str]:
    out = []
    for name, entry in entries().items():
        if entry.get("dir"):                          # a library with no *-config: is it there?
            where = expand(entry["dir"])
            found = Path(where, "include").is_dir() and Path(where, "lib").is_dir()
            shown, where = ("found" if found else "not found"), where
        elif isinstance(entry.get("version"), dict):
            where = expand(entry["version"]["file"])
            shown = version(name) if Path(where).is_file() else "not found"
        else:
            command = entry.get("version") or entry.get("flags")
            where = shutil.which(command[0]) if command else None
            shown = version(name) if entry.get("version") and where else ("not found" if command else "")
        out.append(f"{name:10s} {shown or '-':40s} {where or ''}")
    return out


if __name__ == "__main__":
    if sys.argv[1:] == ["--bash"]:
        sys.stdout.write(bash())
    elif sys.argv[1:] == ["--versions"]:
        print("\n".join(versions()))
    else:
        sys.exit("usage: stack.py --bash | --versions")
