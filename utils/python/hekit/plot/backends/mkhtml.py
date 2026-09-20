"""The `rivet-mkhtml` backend (07 §4).

Ported from `rivpyth_common.plot_arguments` and the `ydmrg`/`ydplt` flow, which between them had the
argument construction right — including the one subtlety worth preserving:

**a hidden reference curve still owns a legend entry.** With `[plot.data].show = false` the reference
is kept as the ratio denominator but not drawn, and `rivet-mkhtml` would then shift every legend label
by one. Naming the MC curves explicitly and passing `PLOT:LegendOnly=...` keeps each label on its own
curve. That is the sort of thing that is invisible in a test and obvious in a plot, so it is ported
verbatim rather than rediscovered.

The backend itself runs one process per page and never touches the pipeline's files.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...env import paths
from ...errors import HepError
from ..page import Page

TOOL = "rivet-mkhtml"


def available() -> bool:
    return shutil.which(TOOL) is not None


def environment(*, analysis_paths: list[Path] | None = None, run: str = "") -> dict[str, str]:
    """`RIVET_ANALYSIS_PATH` for the plugin's `.plot`/`.info`, and a private matplotlib cache.

    `rivet-mkhtml` imports matplotlib, which writes a font cache into `$HOME` and rebuilds it when it
    looks stale; two pages drawn at once can corrupt each other's (00/B19).
    """
    found = dict(os.environ)
    entries = [str(path) for path in (analysis_paths or []) if Path(path).is_dir()]
    if entries:
        inherited = found.get("RIVET_ANALYSIS_PATH", "")
        found["RIVET_ANALYSIS_PATH"] = os.pathsep.join(entries + ([inherited] if inherited else []))
    found["MPLCONFIGDIR"] = str(paths.mpl_config_dir(run or "plot"))
    return found


def arguments(page: Page, *, rivet_refs: bool = False, data_legend: str = "Data") -> list[str]:
    """The input arguments for one page: MC curves, then the data file if there is one."""
    found = ["--rmopts"] + ([] if rivet_refs else ["--no-rivet-refs"])
    inputs = [f"{curve.path}:Title={curve.legend.replace(':', ' ')}" if curve.legend
              else str(curve.path) for curve in page.curves]

    # `[plot].show_fits`: the fitted curves, already renamed onto their targets (12 §3).
    fits = getattr(page, "fits", None)
    if fits is not None and getattr(fits, "path", None) is not None:
        inputs.append(f"{fits.path}:Title=fit")

    overlay = page.data
    if overlay is None or overlay.path is None:
        return [*found, *inputs]

    # A reference is passed bare (rivet-mkhtml labels it with --reflabel); a plain curve carries its
    # own title.
    reference = _is_reference(overlay)
    if reference:
        found += ["--reflabel", data_legend]
        data_input = str(overlay.path)
    else:
        data_input = f"{overlay.path}:Title={data_legend}"

    if _drawn(overlay):
        return [*found, *inputs, data_input]

    names = [f"curve{index}" for index in range(1, len(inputs) + 1)]
    inputs = [f"{entry}:Name={name}" for entry, name in zip(inputs, names)]
    return [*found, *inputs, data_input, f"PLOT:LegendOnly={' '.join(names)}"]


def _is_reference(overlay: Any) -> bool:
    from .. import io

    if overlay.path is None:
        return False
    objects = io.read(overlay.path)
    return any(path.startswith("/REF/") for path in objects)


def _drawn(overlay: Any) -> bool:
    from .. import io

    objects = io.read(overlay.path)
    for obj in objects.values():
        if obj.hasAnnotation("MainPanel") and str(obj.annotation("MainPanel")) in {"0", "False"}:
            return False
    return True


def command(page: Page, output: Path, *, rivet_refs: bool = False,
            data_legend: str = "Data") -> list[str]:
    """The whole `rivet-mkhtml` command line, `.plot` overrides in the order they must be read."""
    found = [TOOL, "-o", str(output)]
    if page.plot_file is not None:
        found += ["-c", str(page.plot_file)]
    if page.ranges is not None:
        found += ["-c", str(page.ranges)]          # after the project's file: overrides only the range
    return [*found, *arguments(page, rivet_refs=rivet_refs, data_legend=data_legend)]


@dataclass
class Result:
    page: str
    output: Path
    status: int = 0
    command: list[str] | None = None

    @property
    def ok(self) -> bool:
        return self.status == 0

    @property
    def index(self) -> Path:
        return self.output / "index.html"


def draw(page: Page, output: Path, *, rivet_refs: bool = False, data_legend: str = "Data",
         analysis_paths: list[Path] | None = None, timeout: float = 3600.0,
         capture: bool = True) -> Result:
    """Draw one page. The process is the only thing that writes into `output`."""
    if not available():
        raise HepError(f"{TOOL} is not on PATH",
                       hint="it comes with Rivet; `hep doctor` reports what is installed")
    output.mkdir(parents=True, exist_ok=True)
    line = command(page, output, rivet_refs=rivet_refs, data_legend=data_legend)
    done = subprocess.run(line, env=environment(analysis_paths=analysis_paths, run=page.name),
                          capture_output=capture, text=True, timeout=timeout)
    return Result(page=page.name, output=output, status=done.returncode, command=line)
