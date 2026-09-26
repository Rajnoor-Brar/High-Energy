"""`provenance.json`: everything needed to explain, trust and rebuild one result (07 §2).

The field list is adapted from `legacy/utils/Record/Meta.hh`, which had the right instinct — record the
host, the git state, the tool versions and a hash of every input — and the wrong scope, since it lived
inside the C++ writer and therefore knew nothing about the configuration that produced the run.

The split here is the one the architecture already makes: `hep-run` writes `run.summary.json` with what
only it knows (counts, the seeds its instances really used, σ with its error, warnings), and this
module folds that into the rest — the configuration, the git state, the resources, the outputs and
their hashes. So provenance is assembled by the side that knows about configuration, and a run never
fails because provenance could not be gathered:

**every field degrades to "unknown" rather than raising.** A missing git, an unreadable plugin, a
deleted card — each costs one field and nothing else.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..results.layout import write_json
from . import versions
from .git import git_state

NAME = "provenance.json"
SCHEMA = 2


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z") or ""


def sha256(path: Path | str) -> str:
    """The digest of a file, or "" when it cannot be read."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def file_record(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {"path": str(path), "sha256": sha256(path), "bytes": size}


def who() -> str:
    for source in (lambda: os.environ.get("USER", ""), getpass.getuser):
        try:
            found = source()
        except Exception:                        # pragma: no cover - no passwd entry
            found = ""
        if found:
            return found
    return "unknown"


@dataclass
class Provenance:
    """One point's provenance, assembled piece by piece and written once."""

    point: str = ""
    point_hash: str = ""
    origin: dict[str, Any] = field(default_factory=dict)
    cards: list[dict[str, Any]] = field(default_factory=list)
    resources: dict[str, Any] = field(default_factory=dict)
    run: dict[str, Any] = field(default_factory=dict)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    exit_code: int = 0
    created: str = field(default_factory=now)

    def document(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "point": self.point,
            "hash": self.point_hash,
            "origin": self.origin,
            "created": self.created,
            "host": platform.node() or "unknown",
            "user": who(),
            "platform": f"{platform.system()} {platform.release()}",
            "git": git_state(),
            "tools": tools(),
            "cards": self.cards,
            "resources": self.resources,
            "run": self.run,
            "outputs": self.outputs,
            "exit": self.exit_code,
        }

    def write(self, directory: Path) -> Path:
        return write_json(Path(directory) / NAME, self.document())


def tools() -> dict[str, str]:
    """Versions of everything a result depends on, `hekit` included."""
    found: dict[str, str] = {}
    try:
        from .. import __version__ as hekit_version
    except Exception:                            # pragma: no cover - during early bootstrapping
        hekit_version = "0.1.0"
    found["hekit"] = hekit_version
    try:
        for name, tool in versions.toolchain().items():
            if getattr(tool, "version", ""):
                found[name.lower().replace(" ", "_")] = tool.version
    except Exception:                            # pragma: no cover - a broken environment
        pass
    return found


def resources_of(spec: dict[str, Any], *, pdf_sets: list[str] | None = None,
                 analysis_paths: list[Path] | None = None) -> dict[str, Any]:
    """PDF sets, analysis plugins and module libraries, with a hash of every `.so` we can find.

    The hash is what makes "the same analysis" checkable: a plugin rebuilt with different cuts has the
    same name and a different digest, and that is the difference between two results that look
    comparable and two that are.
    """
    found: dict[str, Any] = {"pdf_sets": sorted(set(pdf_sets or []))}
    analyses: dict[str, Any] = {}
    for analyzer in spec.get("analyzer", []) or []:
        if analyzer.get("kind") != "rivet":
            continue
        search = [Path(entry) for entry in analyzer.get("paths", [])] + list(analysis_paths or [])
        for entry in analyzer.get("analyses", []) or []:
            base = entry.split(":", 1)[0]
            analyses.setdefault(base, {"so_sha256": "", "path": ""})
            for directory in search:
                candidate = Path(directory) / f"Rivet_{base}.so"
                if candidate.is_file():
                    analyses[base] = {"so_sha256": sha256(candidate), "path": str(candidate)}
                    break
    if analyses:
        found["analyses"] = analyses
    return found


def assemble(*, spec: dict[str, Any], summary: dict[str, Any] | None, origin: dict[str, Any],
             outputs: list[Path] | None = None, exit_code: int = 0,
             pdf_sets: list[str] | None = None,
             analysis_paths: list[Path] | None = None) -> Provenance:
    """Build a `Provenance` from a resolved spec and whatever `hep-run` reported.

    `summary` is the parsed `run.summary.json`; None when the run never got far enough to write one,
    in which case the run section says so rather than inventing numbers.
    """
    meta = spec.get("meta", {})
    found = Provenance(point=meta.get("point", ""), point_hash=meta.get("hash", ""),
                       origin=origin, exit_code=exit_code)
    found.cards = [file_record(card) for card in spec.get("source", {}).get("cards", [])]
    found.resources = resources_of(spec, pdf_sets=pdf_sets, analysis_paths=analysis_paths)
    found.run = dict((summary or {}).get("run", {}))
    if summary is None:
        found.run = {"events": 0, "stopped": True, "note": "the run wrote no summary"}
    found.outputs = [file_record(path) for path in (outputs or []) if Path(path).is_file()]
    return found


def read(directory: Path) -> dict[str, Any] | None:
    path = Path(directory) / NAME if Path(directory).is_dir() else Path(directory)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
