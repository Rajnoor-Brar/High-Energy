"""`hep proc`: fits and derived histograms over results that already exist (08 §2, 12 §2).

It never generates anything. The inputs are the `analysis.yoda` files `hep run` has already written,
and the outputs go into the study directory beside the plots — so the order is always
`hep run` → `hep proc` → `hep plot`, and a fit is a thing you can redo without regenerating events.

`--only` picks one fit by name, `--backend` overrides every fit's choice, and selectors work exactly
as they do for `hep plot`, because "the points I mean" should not be a different idea in two commands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from ..config import load_config
from ..errors import HepError
from ..plan.cli import selectors
from ..results import layout as layout_module
from ..sweep import select as select_points


@click.command("proc")
@click.argument("config_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@selectors
@click.option("--only", metavar="NAME", help="run just this one [[proc.fit]] or [[proc.hist]] entry")
@click.option("--backend", type=click.Choice(["auto", "minuit2", "roofit", "scipy"]),
              help="override the backend of every fit")
@click.option("--engine", type=click.Choice(["auto", "rdf", "uproot"]),
              help="override the engine of every derived histogram")
@click.option("--out", type=click.Path(file_okay=False, path_type=Path),
              help="write into this directory instead of the study's proc/")
@click.option("--keep-root", is_flag=True, help="also write proc.root for inspection")
@click.option("--export-root", is_flag=True,
              help="write each point's analysis.root, as [proc.export] would")
@click.pass_context
def proc(context: click.Context, config_file: Path, study, pins, across, style, overlay, sets,
         only, backend, engine, out, keep_root, export_root) -> None:
    """Fits and derived histograms (ROOT processing)."""
    from ..plan import build as builder
    from . import backends as backends_module
    from . import fit as fit_module
    from . import outputs as outputs_module

    config = load_config(config_file, sets=tuple(sets))
    entries = _fits_of(config)
    histograms = [dict(item) for item in (getattr(config, "proc_hists", None) or [])]
    exporting = export_root or bool(getattr(getattr(config, "proc_export", None), "enabled", False))
    if only:
        every = [str(item.get("name")) for item in entries + histograms]
        entries = [entry for entry in entries if str(entry.get("name")) == only]
        histograms = [item for item in histograms if str(item.get("name")) == only]
        if not entries and not histograms:
            raise HepError(f"no [[proc.fit]] or [[proc.hist]] called {only!r}",
                           hint="names in this config: " + (", ".join(every) or "none"))
    if not entries and not histograms and not exporting:
        raise HepError("this config declares no [[proc.fit]], [[proc.hist]] or [proc.export]",
                       hint="12 §2 has the blocks; `hep config reference proc.fit` prints the keys")

    selection = select_points(config, study=study, pins=tuple(pins), across=across, style=style,
                              overlay=overlay)
    plan = builder.build(config, selection, check_analyses=False)
    layout = layout_module.Layout.of(config)

    points = _points_of(plan, layout)
    if not points:
        raise HepError("no results to fit",
                       hint="`hep run` first; `hep plan` shows what this config expands to")

    destination = Path(out) if out else _proc_dir(layout, plan)
    chosen = backend or "auto"
    fitted: list[Any] = []
    models: dict[str, Any] = {}
    inputs: dict[str, str] = {}

    for entry in entries:
        wanted = _points_for(entry, points)
        for name, path in wanted:
            objects = _read(path)
            target = _target_of(objects, str(entry.get("target") or ""), name)
            one = fit_module.run_one(target, entry,
                                     backend=backend or str(entry.get("backend") or "auto"))
            one.point = name if len(wanted) > 1 else ""
            fitted.append(one)
            models[one.name] = fit_module.model_for(entry)
            inputs.setdefault(name, outputs_module.sha256_of(path))
            click.echo("hep proc: " + outputs_module.summary_line(one))

    used = sorted({one.result.backend for one in fitted})
    if chosen == "auto" and used and "minuit2" not in used and "roofit" not in used:
        # Said out loud, not inferred from the JSON later: `auto` quietly using a different fitter
        # than the reader assumes is exactly how two runs come to disagree for no visible reason.
        click.echo("hep proc: PyROOT is not available, so the scipy backend was used", err=True)

    if not fitted and not entries:
        written = None
    else:
        written = outputs_module.write_json(
            fitted, destination, inputs=inputs,
            config_hash=str(getattr(plan, "hash", "") or ""),
            pyroot=backends_module.available("minuit2"),
            backend=", ".join(used), merge=bool(only))
        click.echo(f"hep proc: {len(fitted)} fits → {written}")

    # ── derived histograms (12 §2.2) ─────────────────────────────────────────
    filled: list[Any] = []
    for entry in histograms:
        for name, path in _points_for(entry, points):
            source = _source_of(entry, path)
            from . import hist as hist_module

            one = hist_module.fill(entry, source, engine=engine or str(entry.get("engine") or "auto"))
            one.name = f"{one.name}/{name}" if len(points) > 1 else one.name
            filled.append(one)
            inputs.setdefault(str(source), outputs_module.sha256_of(source))
            click.echo(f"hep proc: {one.name}: {entry.get('expression')} on {source.name} "
                       f"({one.engine}, {one.entries} entries, {one.total:.0f} in range)")

    curves = outputs_module.write_yoda(fitted, destination, histograms=filled, merge=bool(only))
    if curves:
        click.echo(f"hep proc: curves → {curves}")
    if keep_root or any(bool(entry.get("keep_root")) for entry in entries):
        root_file = outputs_module.write_root(fitted, destination, models)
        click.echo(f"hep proc: {root_file}" if root_file
                   else "hep proc: no PyROOT, so proc.root was not written")

    # ── the ROOT view (12 §2.3) ──────────────────────────────────────────────
    # Per point, beside its own `analysis.yoda`, because it is one-to-one with it. The YODA file
    # stays the record; this is a derived view and `hep clean` may remove it.
    if exporting:
        from . import export as export_module

        settings = getattr(config, "proc_export", None)
        filename = str(getattr(settings, "file", "") or "analysis.root")
        select = [str(pattern) for pattern in (getattr(settings, "select", None) or [])]
        for name, path in points:
            target = (Path(out) / f"{name}.root") if out else (path.parent / filename)
            written_root = export_module.export(path, target, select=select, title=name)
            for obj_path, reason in written_root.skipped.items():
                click.echo(f"hep proc: {obj_path or '(nothing)'} not exported: {reason}", err=True)
            if written_root.ok:
                click.echo(f"hep proc: {len(written_root.objects)} histograms → {target}")
            else:
                raise HepError(f"nothing in {path.name} could be exported to ROOT",
                               hint="[proc.export].select decides what is taken; [] means all")

    if any(not one.result.valid for one in fitted):
        bad = ", ".join(one.name for one in fitted if not one.result.valid)
        raise HepError(f"these fits did not converge: {bad}",
                       hint="fits.json has the status; try `range`, `init` or `limits`")


# ── helpers ──────────────────────────────────────────────────────────────────

def _fits_of(config: Any) -> list[dict]:
    """The `[[proc.fit]]` entries. An array section reaches the model as a list of dicts."""
    return [dict(entry) for entry in (getattr(config, "proc_fits", None) or [])]


def _points_of(plan: Any, layout: Any) -> list[tuple[str, Path]]:
    """`(point name, analysis.yoda)` for every point of the plan that has a result."""
    from ..plot import page as page_module

    found: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for page in getattr(plan, "pages", []) or []:
        for point in page_module.points_of(plan, layout, page):
            if point.name in seen or not point.yoda.is_file():
                continue
            seen.add(point.name)
            found.append((point.name, point.yoda))
    if found:
        return found

    # No pages. A config whose only analyzer is a C++ module declares no Rivet analysis, so the planner
    # builds no page — but it still produces one `analysis.yoda` per point, and `hep proc` works on
    # points, not on pages. Falling back to the plan's own points is what makes a module-only
    # config processable at all.
    for point in getattr(plan, "points", []) or []:
        directory = layout.point(plan.group_of(point.name).name)
        for candidate in ("analysis.yoda", "analysis.yoda.gz", "analysis.partial.yoda"):
            path = directory / candidate
            if path.is_file() and point.name not in seen:
                seen.add(point.name)
                found.append((point.name, path))
                break
    return found


def _points_for(entry: dict, points: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    """Which points this fit applies to: `all`, or a comma-separated list of names."""
    wanted = str(entry.get("points") or "all").strip()
    if wanted in ("", "all", "*"):
        return points
    names = {part.strip() for part in wanted.split(",") if part.strip()}
    chosen = [item for item in points if item[0] in names]
    if not chosen:
        raise HepError(f"fit {entry.get('name')!r} names points that have no results: {wanted}",
                       hint="points here: " + ", ".join(name for name, _ in points))
    return chosen


def _read(path: Path) -> dict:
    import yoda

    return yoda.read(str(path))


def _target_of(objects: dict, target: str, point: str) -> Any:
    """The histogram a fit names, with the near misses listed when it is not there."""
    if not target:
        raise HepError("a [[proc.fit]] needs a `target` YODA path")
    if target in objects:
        return objects[target]
    # A variant writes `/photo_eic:R=0.4/d01-...`; a target given without options should still find
    # it when there is exactly one match, because writing the options out is the unusual case.
    matches = [path for path in objects
               if path.split(":", 1)[0] == target.split(":", 1)[0]
               and path.rsplit("/", 1)[-1] == target.rsplit("/", 1)[-1]]
    if len(matches) == 1:
        return objects[matches[0]]
    if len(matches) > 1:
        raise HepError(f"{target!r} matches {len(matches)} objects in {point}",
                       hint="name the variant too, for example "
                            f"{matches[0]!r}")
    near = [path for path in sorted(objects) if not path.startswith(("/RAW/", "/REF/"))][:8]
    raise HepError(f"{point} has no object at {target!r}",
                   hint="it has: " + ", ".join(near) + (" …" if len(objects) > 8 else ""))


def _proc_dir(layout: Any, plan: Any) -> Path:
    """`studies/<latest run of this study>/proc/`, beside the plots (12 §3)."""
    from . import outputs as outputs_module

    study = getattr(plan, "study", "") or "adhoc"
    latest = layout.latest_study(study)
    if latest is None:
        latest = layout.new_study(study, serial=bool(getattr(plan.config.run, "serial", True)))
    return latest / outputs_module.PROC_DIR


def _source_of(entry: dict, point_yoda: Path) -> Path:
    """The file a `[[proc.hist]]` reads.

    `source = "delphes"` means the group's own `delphes.root`, which sits beside its
    `analysis.yoda` (07 §1) — the point of naming it that way is that a study of twenty points does
    not repeat the path twenty times. Anything else is taken as a path.
    """
    wanted = str(entry.get("source") or "delphes").strip()
    if wanted in ("delphes", "delphes.root"):
        return Path(point_yoda).parent / "delphes.root"
    path = Path(wanted)
    return path if path.is_absolute() else Path(point_yoda).parent / path
