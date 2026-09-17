"""The loaded configuration: section objects, the quantity catalogue, studies, origins.

`load_config()` is the only entry point the rest of the toolkit uses. What it returns is fully
resolved and checked, but not yet *expanded*: selecting a study, applying pins and turning the sweep
into points is P1-S03.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

from ..errors import HepError, did_you_mean
from . import load as ld
from . import schema as sch
from . import validate as vl
from .fields import check

#: Paths whose value is a list of tables rather than a leaf value.
ARRAY_SECTIONS = {("sinks", "module"): sch.MODULE_SINK, ("proc", "fit"): sch.PROC_FIT,
                  ("proc", "hist"): sch.PROC_HIST}


@dataclass
class Study:
    """One `[study.<name>]`: its own scan plus any section overrides it carries."""

    name: str
    description: str = ""
    across: list[Any] = dataclass_field(default_factory=list)
    overlay: str = ""
    style: str = ""
    pin: dict[str, Any] = dataclass_field(default_factory=dict)
    #: ("run", "events") → value, applied on top of the file when the study is selected
    overrides: dict[tuple[str, ...], Any] = dataclass_field(default_factory=dict)


@dataclass
class Config:
    """A validated run configuration."""

    path: Path
    project: str
    schema: int
    run: Any
    generator: Any
    beams: Any
    rivet: Any
    store: Any
    delphes: Any
    output: Any
    plot: Any
    terminal: Any
    sweep: Any
    settle: Any
    module_sinks: list[dict[str, Any]] = dataclass_field(default_factory=list)
    proc_fits: list[dict[str, Any]] = dataclass_field(default_factory=list)
    proc_hists: list[dict[str, Any]] = dataclass_field(default_factory=list)
    quantities: dict[str, Any] = dataclass_field(default_factory=dict)
    studies: dict[str, Study] = dataclass_field(default_factory=dict)
    warnings: list[str] = dataclass_field(default_factory=list)
    resolved: ld.Resolved = dataclass_field(default_factory=ld.Resolved)

    # convenience --------------------------------------------------------
    def origin(self, dotted: str) -> str:
        """Where the winning value of a key came from (`file:line`, `cli`, `default`)."""
        path = ld._split_key(dotted)
        if path not in self.resolved.origins:
            raise HepError(f"no value for '{dotted}'",
                           hint=did_you_mean(dotted, [".".join(p) for p in self.resolved.origins]))
        return self.resolved.origins[path]

    def explain(self, dotted: str) -> list[tuple[str, str, Any]]:
        """The layer chain for a key, oldest first."""
        return self.resolved.explain(dotted)

    def quantity(self, name: str) -> Any:
        try:
            return self.quantities[name]
        except KeyError:
            raise HepError(f"undeclared quantity '{name}'", where=str(self.path),
                           hint=did_you_mean(name, self.quantities) or
                                f"declared: {', '.join(sorted(self.quantities)) or 'none'}") from None


def _free_table(resolved: ld.Resolved, path: tuple[str, ...]) -> dict[str, Any]:
    depth = len(path)
    return {key[-1]: value for key, value in resolved.values.items()
            if len(key) == depth + 1 and key[:depth] == path}


def _build_section(section: sch.Section, prefix: tuple[str, ...], resolved: ld.Resolved) -> Any:
    values: dict[str, Any] = {}
    for key, spec in section.fields.items():
        path = prefix + (key,)
        if spec.free:
            values[key] = _free_table(resolved, path)
        elif path in resolved.values:
            values[key] = resolved.values[path]
        else:
            values[key] = spec.default_value()
    built = sch.CLASSES[section.name](**values)
    for name, subsection in section.subsections.items():
        setattr(built, name, _build_section(subsection, prefix + (name,), resolved))
    return built


def _named_sections(resolved: ld.Resolved, family: str) -> dict[str, tuple[str, ...]]:
    """`quantity` → {"pdf": ("quantity", "pdf"), …} for every named table that has keys."""
    found: dict[str, tuple[str, ...]] = {}
    for path in resolved.values:
        if len(path) >= 3 and path[0] == family:
            found[path[1]] = (family, path[1])
    return found


def _validate_leaves(resolved: ld.Resolved) -> None:
    """Check every leaf against its field; unknown keys and bad values fail here."""
    for path, value in list(resolved.values.items()):
        if path in ARRAY_SECTIONS:
            resolved.values[path] = ld.check_array_section(
                ARRAY_SECTIONS[path], value, resolved.origins.get(path, "?"))
            continue
        where = resolved.origins.get(path, "default")
        spec, label = ld.resolve_field(path, where)
        resolved.values[path] = check(spec, value, f"{where} {label}".strip())


def load_config(path: str | Path, *, sets: tuple[str, ...] = (), machine_file: Path | None = ld.MACHINE_FILE,
                project: str | None = None) -> Config:
    """Read, layer and validate a run TOML (03 §1–2, §6).

    Precedence, lowest to highest: built-in defaults, the machine file (allow-listed keys), the
    `extends` chain left to right, this file, `--set`.
    """
    path = Path(path)
    resolved = ld.Resolved()
    resolved.apply(ld.defaults_layer())
    machine = ld.machine_layer(machine_file)
    if machine is not None:
        resolved.apply(machine)
    for layer in ld.extends_layers(path):
        resolved.apply(layer)
    if sets:
        resolved.apply(ld.set_layer(tuple(sets)))

    vl.require_schema(resolved, path)
    _validate_leaves(resolved)

    quantities: dict[str, Any] = {}
    for name, prefix in _named_sections(resolved, "quantity").items():
        vl.check_name(name, "quantity", resolved.origins.get(prefix, str(path)))
        quantity = _build_section(sch.QUANTITY, prefix, resolved)
        setattr(quantity, "name", name)
        vl.check_quantity(quantity, resolved.origins.get(prefix + ("values",), str(path)))
        quantities[name] = quantity

    studies: dict[str, Study] = {}
    for name, prefix in _named_sections(resolved, "study").items():
        vl.check_name(name, "study", resolved.origins.get(prefix, str(path)))
        fields = _build_section(sch.STUDY, prefix, resolved)
        overrides = {key[2:]: value for key, value in resolved.values.items()
                     if key[:2] == prefix and len(key) > 2 and key[2] in sch.SECTIONS}
        studies[name] = Study(name=name, description=fields.description, across=list(fields.across),
                              overlay=fields.overlay, style=fields.style, pin=dict(fields.pin),
                              overrides=overrides)

    config = Config(
        path=path,
        project=project or resolved.values.get(("project",)) or _project_from_path(path),
        schema=resolved.values[("schema",)],
        run=_build_section(sch.RUN, ("run",), resolved),
        generator=_build_section(sch.GENERATOR, ("generator",), resolved),
        beams=_build_section(sch.BEAMS, ("beams",), resolved),
        rivet=_build_section(sch.RIVET, ("rivet",), resolved),
        store=_build_section(sch.STORE, ("store",), resolved),
        delphes=_build_section(sch.DELPHES, ("delphes",), resolved),
        output=_build_section(sch.OUTPUT, ("output",), resolved),
        plot=_build_section(sch.PLOT, ("plot",), resolved),
        terminal=_build_section(sch.TERMINAL, ("terminal",), resolved),
        sweep=_build_section(sch.SWEEP, ("sweep",), resolved),
        settle=_build_section(sch.SETTLE, ("settle",), resolved),
        module_sinks=resolved.values.get(("sinks", "module"), []),
        proc_fits=resolved.values.get(("proc", "fit"), []),
        proc_hists=resolved.values.get(("proc", "hist"), []),
        quantities=quantities,
        studies=studies,
        resolved=resolved,
    )
    vl.cross_check(config)
    return config


def _project_from_path(path: Path) -> str:
    """`configs/PhotoProduction/eic.toml` → `PhotoProduction`."""
    parent = path.resolve().parent
    return parent.name if parent.name not in {"configs", ""} else ""
