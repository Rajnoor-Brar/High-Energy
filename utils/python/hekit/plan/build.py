"""Building a plan: points → generations → seeds → cards → stage chains (02 §3, 03 §5, §7).

Nothing here touches `results/`: the rendered cards and specs live in the plan objects, and
`hep plan --write` (or `hep run`, P3-S05) decides where they land.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..adapters import adapter_for
from ..adapters import base as adapter_base
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


def module_search_paths(config: Any) -> tuple[Path, ...]:
    """Where a user C++ module's shared library could be (05 §5).

    The build tree first, because that is what `hep build --modules` produces and what a module is
    actually loaded from; the source directory after it, for a library built by hand beside its `.cc`.
    """
    found: list[Path] = []
    if config.project:
        found.append(paths.build_root() / "modules" / config.project)
        found.append(paths.repo_root() / "modules" / config.project)
    return tuple(found)


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


def stage_chain(config: Any, group: Any) -> list[Stage]:
    """The processes one generation needs.

    Pythia and a store replay run inside `hep-run`, so the chain has one stage. An external generator
    adds up to two more — a cached `prepare` and a `generate` that writes the FIFO `hep-run` reads
    (04 §1, §8) — and an external Delphes tee adds one in P7-S08. The chain stays a closed list,
    never a general dependency graph (02 §3).

    The order is always prepare → generate → hep-run, and `hep-run` is always last: it is the one
    that decides whether the run succeeded, because it is the one counting events.
    """
    tool = config.generator.tool
    name = group if isinstance(group, str) else group.name
    run_stage = Stage(name="hep-run", role="generate+analyse",
                      command=["hep-run", str(naming.point_dir(config, name) / "run.toml")],
                      note="in-process source and sinks")
    detector = detector_stages(config, group)
    for stage in detector:
        # *After* the run, not beside it: `DelphesHepMC3` sizes its input and skips anything of
        # length zero, so it cannot read a pipe (P7-S08). The tee writes a file instead.
        stage.phase = run_stage.phase + 1
    if tool in {"pythia", "store"}:
        return [run_stage, *detector]

    adapter = adapter_for(tool)             # raises, naming the step, for one not written yet
    external = external_stages(config, group, adapter)
    if native_rivet(config, adapter):
        # The generator runs Rivet itself and writes the YODA, so there is nothing for `hep-run` to
        # read. Faster for a Rivet-only run, and it gives up every other sink (04 §4).
        return external
    run_stage.role = "analyse"
    if getattr(adapter, "STREAMS", True):
        # It shares the generator's phase: a FIFO's two ends must be open at once or they deadlock.
        run_stage.phase = max((stage.phase for stage in external), default=1)
        run_stage.note = "reads the FIFO the generator writes (Source::Stream)"
    else:
        # The generator wrote a file, so it has to be finished before this reads it (MadGraph's LHE).
        run_stage.phase = max((stage.phase for stage in external), default=0) + 1
        run_stage.note = "showers the events the generator wrote"
    for stage in detector:
        stage.phase = run_stage.phase + 1      # it reads the file this run wrote
    return [*external, run_stage, *detector]


def detector_stages(config: Any, group: Any) -> list[Stage]:
    """The external Delphes stage, when `[delphes].card` asks for one (05 §5, P7-S08)."""
    from ..adapters import delphes as delphes_adapter

    if not delphes_adapter.enabled(config):
        return []
    name = group if isinstance(group, str) else group.name
    return [delphes_adapter.stage(config, group,
                                  naming.point_dir(config, name)).to_plan_stage()]


def native_rivet(config: Any, adapter: Any) -> bool:
    """Is this run letting the generator do the analysing?"""
    return (getattr(config.rivet, "mode", "inprocess") == "native"
            and bool(getattr(adapter, "RUNS_RIVET", False)))


def external_stages(config: Any, group: Any, adapter: Any) -> list[Stage]:
    """The adapter's own stages, as the planner shows them (04 §1).

    A `prepare` stage is only in the chain when the cache has not already got it: that is the whole
    point of the cache, and it has to be visible in `hep plan` or a seed study would look as though
    it integrates ten times.
    """

    from ..adapters import cache as cache_module

    directory = naming.point_dir(config, group.name)
    stages: list[Stage] = []

    entry = cache_module.for_group(config, group)
    prepare = adapter.prepare(config, group, entry.directory) if entry is not None else []
    if prepare and not entry.ready:
        stages += [stage.to_plan_stage() for stage in prepare]

    # `stages()` for a tool that needs more than one step to produce its events — MadGraph launches
    # and then unpacks — and `generate()` for the usual single one.
    fifo = adapter_base.fifo_path(directory)
    produced = (adapter.stages(config, group, fifo) if hasattr(adapter, "stages")
                else [adapter.generate(config, group, fifo)])
    stages += [stage.to_plan_stage() for stage in produced]
    return stages


def build(config: Any, selection: Any, *, index: int | None = None, tool_version: str = "",
          check_analyses: bool = True) -> Plan:
    """Expand, identify, seed and render — everything `hep plan` shows."""
    points = expand(config, selection, index)
    warnings = list(config.warnings)
    tool = config.generator.tool
    adapter = adapter_for(tool) if tool != "store" else None

    # A replay's events already exist, so a sweep that would change them is refused here rather than
    # silently ignored (11 §5). Resolving the store also turns a name or a hash into a directory.
    store_directory = None
    if tool == "store":
        from ..adapters import store as store_adapter

        store_adapter.check_quantities(config, selection)
        store_directory = store_adapter.resolve(config.generator.input, project=config.project)

    card = card_file(config)
    card_bytes = hashing.read_card(card) if card is not None else None
    card_text = card_bytes.decode("utf-8", errors="replace") if card_bytes else ""
    if adapter is not None and card_text:
        adapter.check_card(card_text, str(card))

    if check_analyses:
        entries = group_analyses(points)
        warnings += rivet_adapter.check_analyses(entries, analysis_search_paths(config), str(config.path))

    # A replay is identified by the store it replays plus its analysis configuration (11 §4), and
    # the store's *own* hash is what identifies it — not the reference the user happened to type.
    store_hash = ""
    if store_directory is not None:
        from ..store import index as index_module

        store_hash = index_module.read(store_directory).hash or str(store_directory)

    identified = hashing.group_by_identity(
        points, tool=tool, card_bytes=card_bytes, card_text=card_text, tool_version=tool_version,
        store_hash=store_hash)

    blocks = seeding.assign([(identity.names[0], identity.hash) for identity, _ in identified],
                            run_seed=config.run.seed, threads=config.run.threads)

    groups: list[Group] = []
    plan_store = store_directory
    for identity, members in identified:
        # the directory is named after the events, not after the first analysis variant (07 §1)
        name = members[0].generation_name or identity.names[0]
        block = blocks[identity.hash]
        if config.run.seed_policy == "legacy":
            block = seeding.legacy_block(config.run.seed, members[0].number,
                                         config.run.legacy_seed_step, config.run.threads)
        group = Group(name=name, identity=identity, points=members, seeds=block,
                      analyses=group_analyses(members), stages=[],
                      directory=naming.point_dir(config, name))
        if adapter is not None:
            for point in members:
                adapter.check_overrides(point, str(config.path))
                warning = adapter.frame_warning(point)
                if warning and warning not in warnings:
                    warnings.append(warning)
            group.base_card = card_text
            group.card = adapter.render_card(
                members[0], seeds=block, threads=config.run.threads,
                card_path=str(card), card_sha=identity.inputs["card"],
                identity_hash=identity.hash, origin=describe_origin(config, selection, members[0]),
                # An external adapter renders the whole card rather than appending to a base, and
                # needs to know where its events go; Pythia ignores these.
                base_text=card_text, events=members[0].events,
                fifo=str(adapter_base.fifo_path(naming.point_dir(config, name))),
                mode=getattr(config.rivet, "mode", "inprocess"),
                analyses=group_analyses(members),
                lhe=str(adapter.lhe_path(config, group)) if hasattr(adapter, "lhe_path") else "")
            if hasattr(adapter, "launch_script"):
                # MadGraph's launch carries the seed, the event count and the beams, so it is
                # rendered with the point like the card is (04 §7).
                from ..adapters import cache as cache_module

                entry = cache_module.for_group(config, group)
                group.launch = adapter.launch_script(
                    members[0], seeds=block, events=members[0].events,
                    process_dir=adapter.process_dir(entry.directory))
            if hasattr(adapter, "merging_warning"):
                notice = adapter.merging_warning(card_text)
                if notice and notice not in warnings:
                    warnings.append(notice)
        # After the card: an external generator's prepare stage is keyed on the rendered card, so
        # the chain cannot be built before there is one (04 §1).
        group.stages = stage_chain(config, group)
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
