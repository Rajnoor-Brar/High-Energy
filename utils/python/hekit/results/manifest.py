"""The study manifest: what one run of a study asked for and what it produced (07 §1).

A point directory explains itself (`provenance.json`); a study directory explains the *selection* — the
points it covers, the pages it drew, the command that started it, and the free-text label the user
gave it. That separation is what lets two studies share a generation: the manifest points at points,
it does not own them.

`hep plot`, `hep compare` and `hep runs` all read this file, so it is the one place where a study's
membership is written down.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .layout import serial_of, study_of, write_json

NAME = "manifest.json"
SCHEMA = 2


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Manifest:
    """One run of one study."""

    study: str
    directory: Path
    project: str = ""
    label: str = ""
    serial: int | None = None
    cli: str = ""
    config: str = ""
    started: str = field(default_factory=now)
    finished: str = ""
    points: list[dict[str, Any]] = field(default_factory=list)
    pages: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    exit_code: int = 0

    @classmethod
    def for_run(cls, directory: Path, study: str, **rest) -> "Manifest":
        return cls(study=study or study_of(directory.name), directory=directory,
                   serial=serial_of(directory.name), **rest)

    def add_point(self, name: str, *, point_hash: str, directory: Path, state: str = "",
                  aliases: list[str] | None = None) -> None:
        """Record a point by **reference**: the path and the hash, never a copy of its outputs."""
        self.points.append({"name": name, "hash": point_hash,
                            "path": relative(directory, self.directory),
                            "state": state, "aliases": aliases or []})

    def add_page(self, name: str, *, members: list[str], path: Path | None = None) -> None:
        self.pages.append({"name": name, "members": members,
                           "path": relative(path, self.directory) if path else ""})

    def document(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "study": self.study,
            "project": self.project,
            "serial": self.serial,
            "label": self.label,
            "started": self.started,
            "finished": self.finished or now(),
            "cli": self.cli,
            "config": self.config,
            "exit": self.exit_code,
            "points": self.points,
            "pages": self.pages,
            "warnings": self.warnings,
        }

    def write(self) -> Path:
        self.finished = self.finished or now()
        return write_json(self.directory / NAME, self.document())


def relative(path: Path | None, base: Path) -> str:
    """A path relative to the study directory when it can be, absolute when it cannot.

    Results move — to another machine, into a tarball — and a manifest full of absolute paths from
    somebody else's home directory is the usual reason a study cannot be replotted elsewhere.
    """
    if path is None:
        return ""
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve()))
    except ValueError:
        pass
    try:                                        # one level up covers points/ next to studies/
        return str(Path(path).resolve().relative_to(Path(base).resolve().parent.parent))
    except ValueError:
        return str(Path(path).resolve())


def read(directory: Path) -> dict[str, Any] | None:
    """The manifest of a study directory, or None when there is none to read."""
    path = directory / NAME if directory.is_dir() else directory
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
