"""Finding and writing Rivet `.plot` files (07 §4).

A `.plot` file is the one place a histogram's title, axis labels, log scale and ratio settings are
written down, and both backends read the same keys — `rivet-mkhtml` natively, the mplhep backend by
parsing them (P4-S03). Keeping one source means a relabelled histogram is relabelled everywhere.

Where they are looked for, in order: the build tree (what `rivet-build` copied next to the plugin),
the project's `analyses/` directory, then `output/<project>/`. The same order as the plugin search, so
a `.plot` never comes from a different build than its analysis.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..env import paths

BLOCK = re.compile(r"#\s*BEGIN PLOT\s+(?P<path>\S+)(?P<body>.*?)#\s*END PLOT", re.S)


def search_paths(project: str) -> list[Path]:
    found = [paths.build_root() / "analyses" / project,
             paths.analyses_root() / project,
             paths.output_root() / project]
    return [path for path in found if path.is_dir()]


def find(analysis: str, project: str) -> Path | None:
    """The project's `.plot` file for an analysis, or None to let Rivet use its installed one."""
    base = analysis.split(":", 1)[0]
    for directory in search_paths(project):
        candidate = directory / f"{base}.plot"
        if candidate.is_file():
            return candidate
    return None


def parse(path: Path | str) -> dict[str, dict[str, str]]:
    """`{plot path: {key: value}}` — the same keys both backends honour."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    found: dict[str, dict[str, str]] = {}
    for match in BLOCK.finditer(text):
        settings: dict[str, str] = {}
        for line in match.group("body").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            settings[key.strip()] = value.strip()
        found[match.group("path").strip()] = settings
    return found


def write(blocks: dict[str, dict[str, str]], destination: Path) -> Path:
    """Write override blocks, in the order a reader expects (later files win in rivet-mkhtml)."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = []
    for plot_path, settings in sorted(blocks.items()):
        body = "".join(f"{key}={value}\n" for key, value in sorted(settings.items()))
        text.append(f"# BEGIN PLOT {plot_path}\n{body}# END PLOT\n")
    destination.write_text("\n".join(text), encoding="utf-8")
    return destination
