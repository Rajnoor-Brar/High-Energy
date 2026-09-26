"""Reading `events.index.json` (11 §2).

The index is written last and atomically, so its presence is the signal that a store is finished: a
directory of shards without one is an unfinished store, not a short one. Everything that consumes a
store — `hep store info`, `hep store verify`, and the replay source of P5-S02 — starts here rather
than by scanning the shards, because the shards cannot say how many events they *should* hold.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import HepError

NAME = "events.index.json"
VERSION = 1
SCHEMA = Path(__file__).resolve().parent / "index_v1.json"


def schema_path() -> Path:
    return SCHEMA


@dataclass
class Shard:
    file: str
    events: int = 0
    bytes: int = 0
    sha256: str = ""
    worker: int = 0

    @classmethod
    def of(cls, payload: dict[str, Any]) -> "Shard":
        return cls(file=payload.get("file", ""), events=int(payload.get("events", 0) or 0),
                   bytes=int(payload.get("bytes", 0) or 0), sha256=payload.get("sha256", ""),
                   worker=int(payload.get("worker", 0) or 0))


@dataclass
class Index:
    """One store's index, as data."""

    directory: Path
    version: int = VERSION
    format: str = "hepmc3-ascii"
    compression: str = "zst"
    point: str = ""
    hash: str = ""
    provenance: str = "../provenance.json"
    tool: str = ""
    tool_version: str = ""
    beam_ids: list[int] = field(default_factory=list)
    beam_energies: list[float] = field(default_factory=list)
    threads: int = 0
    seeds: list[int] = field(default_factory=list)
    weights: list[str] = field(default_factory=list)
    xsec_pb: float = 0.0
    xsec_err_pb: float = 0.0
    events: int = 0
    stopped: bool = False
    shards: list[Shard] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def shard_events(self) -> int:
        return sum(shard.events for shard in self.shards)

    @property
    def consistent(self) -> bool:
        return self.shard_events == self.events

    @property
    def bytes(self) -> int:
        return sum(shard.bytes for shard in self.shards)

    def shard_paths(self) -> list[Path]:
        return [self.directory / shard.file for shard in self.shards]

    def describe(self) -> str:
        state = "partial" if self.stopped else "complete"
        return (f"{self.point or self.directory.name}: {self.events} events in "
                f"{len(self.shards)} {self.compression} shards ({state})")


def read(directory: Path | str) -> Index:
    """The index of a store directory (or the path to the index itself)."""
    path = Path(directory)
    if path.is_dir():
        path = path / NAME
    if not path.is_file():
        raise HepError(f"no {NAME} in {Path(directory)}",
                       hint="a store without an index is unfinished; `hep store verify` says what "
                            "is there")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HepError(f"cannot read {path}: {error}") from None

    if payload.get("version") != VERSION:
        raise HepError(f"{path} is index version {payload.get('version')!r}, this hekit reads "
                       f"{VERSION}", hint="the store was written by a different version of hep-run")

    beams = payload.get("beams", {}) or {}
    generator = payload.get("generator", {}) or {}
    return Index(
        directory=path.parent,
        version=payload["version"],
        format=payload.get("format", "hepmc3-ascii"),
        compression=payload.get("compression", "none"),
        point=payload.get("point", ""),
        hash=payload.get("hash", ""),
        provenance=payload.get("provenance", ""),
        tool=generator.get("tool", ""),
        tool_version=generator.get("version", ""),
        beam_ids=[int(entry) for entry in beams.get("ids", []) or []],
        beam_energies=[float(entry) for entry in beams.get("energies", []) or []],
        threads=int(payload.get("threads", 0) or 0),
        seeds=[int(entry) for entry in payload.get("seeds", []) or []],
        weights=list(payload.get("weights", []) or []),
        xsec_pb=float(payload.get("xsec_pb", 0.0) or 0.0),
        xsec_err_pb=float(payload.get("xsec_err_pb", 0.0) or 0.0),
        events=int(payload.get("events", 0) or 0),
        stopped=bool(payload.get("stopped", False)),
        shards=[Shard.of(entry) for entry in payload.get("shards", []) or []],
        raw=payload,
    )


def validate(payload: dict[str, Any] | Path | str) -> None:
    """Check an index against the committed JSON Schema, when jsonschema is available."""
    if isinstance(payload, (str, Path)):
        path = Path(payload)
        if path.is_dir():
            path = path / NAME
        payload = json.loads(path.read_text(encoding="utf-8"))
    try:
        import jsonschema
    except ImportError:                          # pragma: no cover - a dev dependency
        _structural(payload)
        return
    try:
        jsonschema.validate(payload, json.loads(SCHEMA.read_text(encoding="utf-8")))
    except jsonschema.ValidationError as error:
        raise HepError(f"the store index is invalid: {error.message}",
                       where="/".join(str(part) for part in error.absolute_path) or NAME) from None


def _structural(payload: dict[str, Any]) -> None:
    for key in ("version", "format", "compression", "events", "shards"):
        if key not in payload:
            raise HepError(f"the store index has no '{key}'")


def find_stores(root: Path) -> list[Path]:
    """Every store directory under a results tree, by its index."""
    if not Path(root).is_dir():
        return []
    return sorted(path.parent for path in Path(root).rglob(NAME))
