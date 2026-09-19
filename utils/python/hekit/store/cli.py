"""`hep store ls | info | verify` (08 §2, 11 §2).

Three questions a store has to answer without a replay: what stores are there, what is in this one,
and is it still intact. All three read the index; only `verify` touches the shards.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from ..errors import HepError
from . import index as index_module
from .verify import verify as verify_store


@click.group("store")
def store() -> None:
    """HepMC3 event stores: ls, info, verify."""


def _console(plain: bool = False):
    from rich.console import Console

    from ..term import theme

    theme.autodetect()
    return Console(no_color=plain, highlight=not plain)


def _roots(project: str = "") -> list[Path]:
    from ..env import paths

    root = paths.results_root()
    if not root.is_dir():
        return []
    return [root / project] if project else [entry for entry in sorted(root.iterdir())
                                             if entry.is_dir()]


@store.command("ls")
@click.argument("project", required=False, default="")
@click.option("--json", "as_json", is_flag=True, help="machine-readable output")
@click.pass_context
def list_stores(context: click.Context, project: str, as_json: bool) -> None:
    """List the event stores under the results tree."""
    from ..term import theme

    found = []
    for root in _roots(project):
        for directory in index_module.find_stores(root):
            try:
                index = index_module.read(directory)
            except HepError:
                continue
            found.append({"path": str(directory), "point": index.point, "events": index.events,
                          "shards": len(index.shards), "compression": index.compression,
                          "bytes": index.bytes, "stopped": index.stopped})

    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    console = _console((context.obj or {}).get("plain", False))
    if not found:
        from ..env import paths

        console.print(f"[dim]no event stores under {paths.results_root()}[/dim]")
        return

    from rich.table import Table

    table = Table(box=None, pad_edge=False)
    for name in ("point", "events", "shards", "codec", "size", "state"):
        table.add_column(name)
    for row in found:
        table.add_row(row["point"] or Path(row["path"]).parent.name, theme.count(row["events"]),
                      str(row["shards"]), row["compression"],
                      f"{row['bytes'] / 1e9:.2f} GB" if row["bytes"] > 1e9
                      else f"{row['bytes'] / 1e6:.1f} MB",
                      "[yellow]partial[/]" if row["stopped"] else "complete")
    console.print(table)


@store.command("info")
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="print the index itself")
@click.pass_context
def info(context: click.Context, target: Path, as_json: bool) -> None:
    """Everything the index of one store records."""
    index = index_module.read(target)
    if as_json:
        click.echo(json.dumps(index.raw, indent=2))
        return

    from rich.table import Table

    from ..term import theme

    console = _console((context.obj or {}).get("plain", False))
    console.print(f"[bold]{index.point or index.directory.name}[/bold]  [dim]{index.directory}[/dim]")
    if index.hash:
        console.print(f"[dim]{index.hash}[/dim]")

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column()

    def row(label: str, value) -> None:
        if value not in ("", None, []):
            table.add_row(label, str(value))

    row("events", theme.count(index.events) + (" (partial)" if index.stopped else ""))
    row("shards", f"{len(index.shards)}  ({index.compression}, "
                  f"{index.bytes / 1e6:.1f} MB, {index.bytes / max(index.events, 1):.0f} B/event)")
    row("format", index.format)
    row("generator", f"{index.tool} {index.tool_version}".strip())
    row("beams", f"{index.beam_ids}  {index.beam_energies} GeV" if index.beam_ids else "")
    row("threads", index.threads)
    row("seeds", index.seeds)
    row("weights", ", ".join(index.weights))
    row("sigma", theme.sigma(index.xsec_pb, index.xsec_err_pb) if index.xsec_pb else "")
    row("provenance", index.provenance)
    console.print(table)

    shards = Table(box=None, pad_edge=False, title="shards", title_justify="left")
    for name in ("worker", "file", "events", "size", "sha256"):
        shards.add_column(name)
    for shard in index.shards:
        shards.add_row(str(shard.worker), shard.file, theme.count(shard.events),
                       f"{shard.bytes / 1e6:.1f} MB", (shard.sha256 or "")[:16])
    console.print()
    console.print(shards)
    if not index.consistent:
        console.print(f"[red]the shards add up to {index.shard_events}, not {index.events}[/red]")


@store.command("verify")
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option("--deep", is_flag=True, help="check the sha256 of every shard, not just its size")
@click.pass_context
def verify(context: click.Context, target: Path, deep: bool) -> None:
    """Check a store against its index: shards present, sizes, and (with --deep) digests."""
    report = verify_store(target, deep=deep)
    console = _console((context.obj or {}).get("plain", False))
    console.print(report.summary())
    if not report.ok:
        raise SystemExit(1)
