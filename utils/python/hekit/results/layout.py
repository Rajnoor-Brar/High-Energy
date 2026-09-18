"""Where a run's files go, and how they get there safely (07 §1).

```
results/<project>/
  points/<group>/      one generation: spec, card, YODA, summary, provenance, logs
  studies/[NN_]<study>[_<label>]/   one run of a study: manifest, plots, comparisons
  legacy/              pre-rework results, frozen (D-Q4)
```

Two rules the layout exists to enforce:

* **A point is named by its physics, never by when it ran.** `points/<group>/` comes from the point
  name and its identity hash (03 §5), so two studies that reach the same physics share one generation
  and the skip rule can recognise it. The old flat `NN_<name>_<tags>.yoda` put the serial in the path,
  which is why the same physics ended up at four of them (00 §4.1).
* **The serial belongs to a study run** (decision **D-Q3**, P3-S01): `studies/01_pdf/`,
  `studies/02_pdf_thesis/`. It distinguishes runs, which is what a serial is for, and `[run].serial =
  false` drops it.

Everything here writes through a temporary name and renames into place, so a reader never sees a
half-written file and a crash never leaves one behind (D22, 00/B3).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..plan import naming

SERIAL = re.compile(r"^(?P<serial>\d{2,})_")
POINTS = "points"
STUDIES = "studies"
LEGACY = "legacy"
ADHOC = "adhoc"


# ── atomic writes ────────────────────────────────────────────────────────────

def write_atomic(path: Path, data: str | bytes) -> Path:
    """Write a file so that it appears complete or not at all.

    The temporary keeps the extension (`run.tmp.json`, not `run.json.tmp`): YODA and a few other
    readers identify a format from the suffix, and a partial file that cannot even be opened is worse
    than one that can (P0-S03 hit exactly this).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(marked(path.name, "tmp"))
    mode, payload = ("wb", data) if isinstance(data, bytes) else ("w", data)
    try:
        with open(temporary, mode, **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as out:
            out.write(payload)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return path


def write_json(path: Path, payload: Any) -> Path:
    return write_atomic(path, json.dumps(payload, indent=2, sort_keys=False) + "\n")


def marked(name: str, marker: str) -> str:
    """`analysis.yoda` + `partial` → `analysis.partial.yoda` (the marker goes before the suffix)."""
    stem, dot, suffix = name.rpartition(".")
    return f"{stem}.{marker}.{suffix}" if dot else f"{name}.{marker}"


# ── the layout ───────────────────────────────────────────────────────────────

@dataclass
class Layout:
    """The directories of one project's results. Built from a config, so `HEKIT_RESULTS` is honoured."""

    root: Path
    project: str = ""

    @classmethod
    def of(cls, config: Any) -> "Layout":
        return cls(root=naming.results_root(config), project=getattr(config, "project", ""))

    # points ─────────────────────────────────────────────────────────────────
    @property
    def points(self) -> Path:
        return self.root / POINTS

    def point(self, group_name: str) -> Path:
        return self.points / group_name

    def logs(self, group_name: str) -> Path:
        return self.point(group_name) / "logs"

    # studies ────────────────────────────────────────────────────────────────
    @property
    def studies(self) -> Path:
        return self.root / STUDIES

    @property
    def legacy(self) -> Path:
        return self.root / LEGACY

    def study_name(self, study: str, *, serial: int | None = None, label: str = "") -> str:
        """`01_pdf`, `01_pdf_thesis`, or `pdf` when serials are off (D-Q3)."""
        parts = [study or ADHOC]
        if label:
            parts.append(slug(label))
        name = "_".join(parts)
        return f"{serial:02d}_{name}" if serial is not None else name

    def next_serial(self) -> int:
        """One past the highest serial in use, across every study (they share one series, as the
        legacy `01_`…`04_` did — the number says "the Nth run", not "the Nth pdf run")."""
        highest = 0
        if self.studies.is_dir():
            for entry in self.studies.iterdir():
                match = SERIAL.match(entry.name)
                if entry.is_dir() and match:
                    highest = max(highest, int(match.group("serial")))
        return highest + 1

    def new_study(self, study: str, *, label: str = "", serial: bool = True) -> Path:
        """The directory for a *new* run of a study. Allocates the next serial when serials are on."""
        if not serial:
            return self.studies / self.study_name(study, label=label)
        # Loop rather than trust the scan: two `hep run`s started in the same second must not collide.
        number = self.next_serial()
        while True:
            candidate = self.studies / self.study_name(study, serial=number, label=label)
            try:
                candidate.mkdir(parents=True)
                return candidate
            except FileExistsError:
                number += 1

    def study_runs(self, study: str = "") -> list[Path]:
        """Every directory for a study (or all of them), newest serial first."""
        if not self.studies.is_dir():
            return []
        found = []
        for entry in sorted(self.studies.iterdir()):
            if not entry.is_dir():
                continue
            if study and study_of(entry.name) != study:
                continue
            found.append(entry)
        return sorted(found, key=lambda path: (serial_of(path.name) or 0, path.name), reverse=True)

    def latest_study(self, study: str) -> Path | None:
        runs = self.study_runs(study)
        return runs[0] if runs else None

    def pages(self, study_dir: Path) -> Path:
        return study_dir / "plots"

    # housekeeping ───────────────────────────────────────────────────────────
    def orphans(self) -> list[Path]:
        """Point directories with no result in them: a run that died before it wrote anything, or a
        `--write` preview someone left behind. `hep runs` shows these so they can be removed."""
        found = []
        if not self.points.is_dir():
            return found
        for entry in sorted(self.points.iterdir()):
            if not entry.is_dir():
                continue
            if not any(entry.glob("*.yoda")) and not (entry / "run.summary.json").is_file():
                found.append(entry)
        return found


def serial_of(name: str) -> int | None:
    match = SERIAL.match(name)
    return int(match.group("serial")) if match else None


def study_of(name: str) -> str:
    """The study a study-directory name belongs to, serial and label stripped."""
    match = SERIAL.match(name)
    return name[match.end():] if match else name


def slug(text: str) -> str:
    """A label as it may appear in a path: letters, digits and underscores, nothing surprising."""
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", text.strip()).strip("_")
    return cleaned[:60] or "run"
