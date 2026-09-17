"""The resolved spec: the one contract between `hep` and `hep-run` (03 §7).

Everything is explicit — absolute paths, resolved seeds, no `use` indices, no sweeps, no studies — so
that `hep-run` needs to know nothing about configuration. The structure is also described by
`spec_v2.json`, which the Python and the C++ tests share.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tomli_w

from ..errors import HepError
from . import naming

SPEC_VERSION = 2
SPEC_SCHEMA = Path(__file__).with_name("spec_v2.json")


def sink_documents(config: Any, group: Any) -> list[dict[str, Any]]:
    """One entry per sink, in the order `hep-run` should attach them (05 §5)."""
    sinks: list[dict[str, Any]] = []
    if group.analyses:
        sinks.append({
            "kind": "rivet",
            "analyses": list(group.analyses),
            "paths": [str(path) for path in _search_paths(config)],
            "xsec": config.rivet.xsec,
            "weights": config.rivet.weights,
            "dump_every": config.rivet.dump_every,
            "check_beams": config.rivet.check_beams,
        })
    for module in config.module_sinks:
        sinks.append({"kind": "module", "name": module["name"], "options": module.get("options", {})})
    if config.store.enabled:
        sinks.append({"kind": "store", "dir": str(group.directory / "events"),
                      "compression": config.store.compression})
    return sinks


def _search_paths(config: Any) -> tuple[Path, ...]:
    from .build import analysis_search_paths

    return analysis_search_paths(config)


def source_document(config: Any, group: Any) -> dict[str, Any]:
    """Where the events come from (03 §7)."""
    tool = config.generator.tool
    if tool == "store":
        return {"kind": "store", "input": config.generator.input}
    cards = []
    from .build import card_file

    base = card_file(config)
    if base is not None:
        cards.append(str(base))
    cards.append(str(naming.card_path(config, group.name, tool)))
    for extra in group.points[0].cards:
        cards.append(str((config.path.parent / extra).resolve()))
    return {"kind": tool, "cards": cards}


def document(config: Any, group: Any, *, origin: str = "") -> dict[str, Any]:
    """The resolved spec of one generation."""
    directory = group.directory or naming.point_dir(config, group.name)
    return {
        "meta": {
            "schema": SPEC_VERSION,
            "point": group.name,
            "aliases": [name for name in group.aliases if name != group.name],
            "hash": f"sha256:{group.identity.hash}",
            "origin": origin,
        },
        "run": {
            "events": group.points[0].events or 0,
            "seed": group.seeds.point,
            "threads": config.run.threads,
            "seeds": {"point": group.seeds.point, "instances": list(group.seeds.instances)},
        },
        "source": source_document(config, group),
        "output": {
            "dir": str(directory),
            "yoda": "analysis.yoda",
            "summary": "run.summary.json",
        },
        "sink": sink_documents(config, group),
        "status": {"fd": 3, "heartbeat_ms": 500},
    }


def attach_specs(plan: Any) -> None:
    """Fill in every group's resolved spec."""
    from .build import describe_origin

    for group in plan.groups:
        group.spec = document(plan.config, group,
                              origin=describe_origin(plan.config, plan.selection, group.points[0]))


def dumps(spec: dict[str, Any]) -> str:
    """The spec as TOML, with the sinks as an array of tables."""
    return tomli_w.dumps(spec)


def write(plan: Any, directory: Path) -> list[Path]:
    """Write every group's `run.toml` and native card into `directory/<group>/` (never into results/).

    `hep plan` uses a temporary directory; `hep run` (P3-S05) writes into the point directory itself.
    """
    written: list[Path] = []
    for group in plan.groups:
        target = directory / group.name
        target.mkdir(parents=True, exist_ok=True)
        spec_path = target / "run.toml"
        spec_path.write_text(dumps(group.spec), encoding="utf-8")
        written.append(spec_path)
        if group.card:
            card = target / naming.card_path(plan.config, group.name, plan.config.generator.tool).name
            card.write_text(group.card, encoding="utf-8")
            written.append(card)
    return written


def check(spec: dict[str, Any]) -> None:
    """Validate a spec against `spec_v2.json` when jsonschema is available, else structurally."""
    try:
        import jsonschema
    except ImportError:                     # pragma: no cover - jsonschema is a dev dependency
        _check_structure(spec)
        return
    try:
        jsonschema.validate(spec, json.loads(SPEC_SCHEMA.read_text(encoding="utf-8")))
    except jsonschema.ValidationError as error:
        raise HepError(f"resolved spec is invalid: {error.message}",
                       where="/".join(str(part) for part in error.absolute_path) or "spec") from None


def _check_structure(spec: dict[str, Any]) -> None:
    for section in ("meta", "run", "source", "output", "status"):
        if section not in spec:
            raise HepError(f"resolved spec has no [{section}]")
    if spec["meta"].get("schema") != SPEC_VERSION:
        raise HepError(f"resolved spec is not version {SPEC_VERSION}")
