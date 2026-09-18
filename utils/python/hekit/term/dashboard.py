"""The live dashboard (06 §1).

```
 hep run eic.toml --study pdf                     PhotoProduction · 0a10209+dirty
 ───────────────────────────────────────────────────────────────────────────────
  points ██████████░░░░░░░░░░ 2/4      elapsed 18:42      eta ≈ 37 min
  ✔ 1  eic_5x41_em_MSTW    1.00 M ev   σ = 1.832e+04 pb ± 0.3 %   9m12s
  ▶ 2  eic_5x41_em_NNLO
       generate+rivet  ████████░░░░  642 113 / 1 000 000  64 %  1.18 k ev/s
  · 3  eic_5x41_em_NNNLO   queued
 ─ log (curated) ───────────────────────────────────────────────────────────────
  12:41:07  pythia  W  SpaceShower::pT2nearThreshold: stuck in loop          ×2
 ───────────────────────────────────────────────────────────────────────────────
  Ctrl-C: stop at next checkpoint (partial YODA kept) · Ctrl-C ×2: abort
```

It renders **inline** — no alternate screen — so the final summary stays in the scrollback, and it
draws from the same `RunView` the plain renderer and `hep watch` use. `rich` handles SIGWINCH, colour
detection and cursor restore; the one thing this module must get right itself is that the terminal is
returned to the user whatever happens, including an exception mid-render, which is what `__exit__` and
the `atexit` hook are for.
"""

from __future__ import annotations

import atexit
import time
from dataclasses import dataclass, field
from typing import Any

from . import theme
from .model import FINISHED, RunView

FOOTER = "Ctrl-C: stop at the next checkpoint (partial outputs kept) · Ctrl-C ×2: abort"


def _t(text: str) -> str:
    return theme.t(text)


def _rich():
    """Imported lazily: `hep --help` must not pay for rich (08 §2)."""
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text
    return Console, Group, Live, Panel, Rule, Table, Text


@dataclass
class Dashboard:
    """Draws a `RunView`. Use it as a context manager; it always restores the terminal."""

    view: RunView
    console: Any = None
    refresh_per_second: float = 8.0
    width: int = 0
    _live: Any = None
    _stopped: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        Console, *_ = _rich()
        if self.console is None:
            self.console = Console(width=self.width or None)

    # ── lifetime ─────────────────────────────────────────────────────────────

    def __enter__(self) -> "Dashboard":
        _, _, Live, *_ = _rich()
        # transient=False: the last frame stays in the scrollback, which is the point of rendering
        # inline rather than on the alternate screen (06 §1).
        self._live = Live(self.render(), console=self.console, transient=False,
                          refresh_per_second=self.refresh_per_second, redirect_stdout=False,
                          redirect_stderr=False)
        self._live.__enter__()
        atexit.register(self.stop)
        return self

    def __exit__(self, *exception) -> None:
        self.stop()

    def stop(self) -> None:
        """Restore the terminal. Safe to call twice, and safe to call from `atexit`."""
        if self._stopped or self._live is None:
            self._stopped = True
            return
        self._stopped = True
        try:
            self._live.update(self.render(), refresh=True)
        except Exception:                            # pragma: no cover - a broken pipe on the way out
            pass
        try:
            self._live.__exit__(None, None, None)
        finally:
            # `rich` normally does this itself; doing it again costs nothing and covers the case where
            # Live never started cleanly, which is exactly when a user is left without a cursor.
            try:
                self.console.show_cursor(True)
            except Exception:                        # pragma: no cover
                pass
            try:
                atexit.unregister(self.stop)
            except Exception:                        # pragma: no cover
                pass

    def refresh(self) -> None:
        if self._live is not None and not self._stopped:
            self._live.update(self.render(), refresh=True)

    # ── drawing ──────────────────────────────────────────────────────────────

    def render(self) -> Any:
        _, Group, _, _, Rule, _, _ = _rich()
        blocks = [self.header(), self.overall()]
        blocks.extend(self.point_lines())
        logs = self.log_pane()
        if logs is not None:
            blocks.append(Rule(title="log (curated)", style="dim"))
            blocks.append(logs)
        blocks.append(Rule(style="dim"))
        blocks.append(self.footer())
        return Group(*blocks)

    def header(self) -> Any:
        *_, Text = _rich()
        left = self.view.command or "hep run"
        right = _t(" · ").join(part for part in (self.view.project, self.view.git) if part)
        text = Text(left, style="bold")
        text.append("  ")
        text.append(right, style="dim")
        return text

    def overall(self) -> Any:
        *_, Text = _rich()
        done, total = self.view.done_points, len(self.view.points)
        remaining = self.view.eta_seconds()
        text = Text("  points ", style="bold")
        text.append(theme.bar(done, total), style="cyan")
        text.append(f"  {done}/{total}")
        text.append(f"      elapsed {theme.duration(self.view.elapsed())}", style="dim")
        if remaining is not None:
            text.append(_t(f"      eta ≈ {theme.duration(remaining)}"), style="dim")
        return text

    def point_lines(self) -> list[Any]:
        *_, Text = _rich()
        lines: list[Any] = []
        for point in self.view.points:
            head = Text(_t(f"  {point.glyph} {point.index}  "), style=point.colour)
            head.append(f"{point.name:<28}")
            head.append(_t(self.point_summary(point)), style="dim")
            lines.append(head)
            if point.running:
                for stage in point.stages.values():
                    lines.append(self.stage_line(stage))
                if point.xsec_pb:
                    detail = Text("       ")
                    detail.append(theme.sigma(point.xsec_pb, point.xsec_err_pb,
                                              running=not point.xsec_final), style="dim")
                    if point.warning_count:
                        sources = _t(" · ").join(f"{name} {count}"
                                                 for name, count in sorted(point.warnings.items()))
                        detail.append(_t(f" · warnings {point.warning_count} ({sources})"),
                                      style="yellow")
                    lines.append(detail)
        return lines

    def point_summary(self, point) -> str:
        if point.state == "queued":
            return "queued"
        if point.state == "skipped":
            return f"skipped · {point.reason}" if point.reason else "skipped"
        if point.state == "failed":
            return f"exit {point.exit_code} · {point.reason}" if point.reason else \
                   f"exit {point.exit_code}"
        if point.state in FINISHED:
            bits = [f"{theme.count(point.events)} ev"]
            if point.xsec_pb:
                bits.append(theme.sigma(point.xsec_pb, point.xsec_err_pb))
            bits.append(theme.duration(point.elapsed()))
            bits.append(f"{point.warning_count} warnings")
            return "   ".join(bits)
        return ""

    def stage_line(self, stage) -> Any:
        *_, Text = _rich()
        text = Text("       ")
        text.append(f"{stage.name:<16}")
        if stage.total:
            text.append(theme.bar(stage.done, stage.total, 22), style="cyan")
            remaining = stage.eta_seconds()
            text.append(f"  {theme.grouped(stage.done)} / {theme.grouped(stage.total)}"
                        f"  {theme.percent(stage.done, stage.total)}  {theme.rate(stage.rate)}")
            if remaining is not None:
                text.append(f"  eta {theme.duration(remaining)}")
        else:
            # No count from this tool: a phase and the elapsed time, which is all there is to say.
            text.append(f"{stage.phase or 'working'}  {theme.duration(stage.elapsed())}", style="dim")
            if stage.last_line:
                text.append(f"  {stage.last_line[:60]}", style="dim")
        return text

    def log_pane(self) -> Any | None:
        _, _, _, _, _, Table, Text = _rich()
        entries = self.view.recent_logs()
        if not entries:
            return None
        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim", no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(ratio=1)
        table.add_column(justify="right", style="dim")
        for entry in entries:
            table.add_row(
                " " + theme.clock(entry.time),
                Text(entry.source, style="dim"),
                Text(theme.LEVEL_LETTER.get(entry.level, "?"),
                     style=theme.LEVEL_COLOUR.get(entry.level, "")),
                Text(entry.message[:90]),
                _t(f"×{entry.count}") if entry.count > 1 else "")
        return table

    def footer(self) -> Any:
        *_, Text = _rich()
        if self.view.finished:
            done = sum(1 for point in self.view.points if point.state == "done")
            failed = len(self.view.failed_points)
            text = Text(f"  {done} done", style="green")
            if failed:
                text.append(_t(f" · {failed} failed"), style="red")
            text.append(_t(f" · {theme.duration(self.view.elapsed())}"), style="dim")
            return text
        return Text(_t("  " + FOOTER), style="dim")


def render_once(view: RunView, *, width: int = 100, record: bool = True) -> str:
    """Draw one frame into a string — how the snapshot tests read the dashboard."""
    import io

    Console, *_ = _rich()
    # file=StringIO, or the frame is printed to the real stdout *and* returned.
    console = Console(width=width, record=record, force_terminal=False, no_color=True,
                      legacy_windows=False, file=io.StringIO())
    dashboard = Dashboard(view=view, console=console)
    console.print(dashboard.render())
    return console.export_text()
