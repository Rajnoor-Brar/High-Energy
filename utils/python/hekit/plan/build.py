"""Building a plan: points → generations → seeds → cards → stage chains (02 §3, 03 §5, §7).

Nothing here touches `results/`: the rendered cards and specs live in the plan objects, and
`hep plan --write` (or `hep run`, P3-S05) decides where they land.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters import adapter_for
from ..adapters import rivet as rivet_adapter
from ..env import paths
from ..errors import HepError
from ..sweep import curve_legend, expand, group_pages, page_name, page_suffix
from . import hashing, naming, seeds as seeding
from .model import Group, Page, Plan, Stage


def card_file(config: Any) -> Path | None:
    """The base card named by `[generator].card`, resolved next to the config file."""
    if not config.generator.card:
        return None
    candidate = Path(config.generator.card)
    if candidate.is_absolute():
        return candidate
    return (config.path.parent / candidate).resolve()


def analysis_search_paths(config: Any) -> tuple[Path, ...]:
    """Where to look for analysis plugins and their `.info` files."""
    found: list[Path] = []
    for entry in config.rivet.paths:
        candidate = Path(entry)
        found.append(candidate if candidate.is_absolute() else (config.path.parent / candidate).resolve())
    if config.project:
        # The compiled plugin is what Rivet actually loads, and `rivet-build` writes it into the build
        # tree next to the copied .info/.plot files — so that comes first. The source directory stays
        # in the list because a hand-built .so often sits there.
        found.append(paths.build_root() / "analyses" / config.project)
        found.append(paths.analyses_root() / config.project)
        found.append(paths.output_root() / config.project)
    return tuple(found)


def group_analyses(points: list[Any]) -> list[str]:
    """Every analysis variant of a generation, in one Rivet handler (03 §4)."""
    seen: list[str] = []
    for point in points:
        for entry in point.analyses:
            if entry not in seen:
                seen.append(entry)
    return seen


def stage_chain(config: Any, group_name: str) -> list[Stage]:
    """The processes one generation needs.

    Pythia and a store replay run inside `hep-run`, so the chain has one stage. External generators add
    a prepare and a generate stage in P7, and an external Delphes tee adds a stage in P7-S08; the chain
    stays a closed list, never a general dependency graph (02 §3).
    """
    tool = config.generator.tool
    if tool in {"pythia", "store"}:
        return [Stage(name="hep-run", role="generate+analyse",
                      command=["hep-run", str(naming.point_dir(config, group_name) / "run.toml")],
                      note="in-process source and sinks")]
    raise HepError(f"stage chains for '{tool}' arrive with its adapter",
                   hint="P7 adds Sherpa, Whizard, MadGraph and Herwig")


def build(config: Any, selection: Any, *, index: int | None = None, tool_version: str = "",
          check_analyses: bool = True) -> Plan:
    """Expand, identify, seed and render — everything `hep plan` shows."""
    points = expand(config, selection, index)
    warnings = list(config.warnings)
    tool = config.generator.tool
    adapter = adapter_for(tool) if tool != "store" else None

    card = card_file(config)
    card_bytes = hashing.read_card(card) if card is not None else None
    card_text = card_bytes.decode("utf-8", errors="replace") if card_bytes else ""
    if adapter is not None and card_text:
        adapter.check_card(card_text, str(card))

    if check_analyses:
        entries = group_analyses(points)
        warnings += rivet_adapter.check_analyses(entries, analysis_search_paths(config), str(config.path))

    identified = hashing.group_by_identity(
        points, tool=tool, card_bytes=card_bytes, card_text=card_text, tool_version=tool_version,
        store_hash=config.generator.input if tool == "store" else "")

    blocks = seeding.assign([(identity.names[0], identity.hash) for identity, _ in identified],
                            run_seed=config.run.seed, threads=config.run.threads)

    groups: list[Group] = []
    for identity, members in identified:
        # the directory is named after the events, not after the first analysis variant (07 §1)
        name = members[0].generation_name or identity.names[0]
        block = blocks[identity.hash]
        if config.run.seed_policy == "legacy":
            block = seeding.legacy_block(config.run.seed, members[0].number,
                                         config.run.legacy_seed_step, config.run.threads)
        group = Group(name=name, identity=identity, points=members, seeds=block,
                      analyses=group_analyses(members), stages=stage_chain(config, name),
                      directory=naming.point_dir(config, name))
        if adapter is not None:
            for point in members:
                adapter.check_overrides(point, str(config.path))
                warning = adapter.frame_warning(point)
                if warning and warning not in warnings:
                    warnings.append(warning)
            group.card = adapter.render_card(
                members[0], seeds=block, threads=config.run.threads,
                card_path=str(card), card_sha=identity.inputs["card"],
                identity_hash=identity.hash, origin=describe_origin(config, selection, members[0]))
        groups.append(group)

    pages = [Page(name=page_name(config, selection, key), suffix=page_suffix(config, selection, key),
                  members=members,
                  legends=[curve_legend(config, selection, point) for point in members])
             for key, members in group_pages(points).items()] if selection.groups else []

    plan = Plan(config=config, selection=selection, points=points, groups=groups, pages=pages,
                warnings=warnings)
    from .spec import attach_specs

    attach_specs(plan)
    return plan


def describe_origin(config: Any, selection: Any, point: Any) -> str:
    """The human-readable provenance line of a point: config, study, position."""
    parts = [str(config.path)]
    if selection.study:
        parts.append(f"--study {selection.study}")
    return " ".join(parts) + f" [{point.number}]"
