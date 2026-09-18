#!/usr/bin/env python3
"""Compare two YODA files object by object and bin by bin (P2-S06).

Written for the equivalence gate — "does the in-process pipeline produce the same physics as the
legacy FIFO one?" — and deliberately kept usable by hand:

    python tests/tools/yodacmp.py a.yoda b.yoda              # exact, up to ASCII precision
    python tests/tools/yodacmp.py a.yoda b.yoda --rtol 1e-6  # loosened
    python tests/tools/yodacmp.py a.yoda b.yoda --chi2        # statistical compatibility instead

Two levels of agreement, because two different questions get asked of it:

  * **identical** — the same events went through the same analysis, so every bin should agree to the
    precision YODA writes (~7 significant digits). This is what the gate demands of a single-thread
    run with the same seed.
  * **compatible** — different events (a different seed, a different thread count) cannot give
    identical bins, only statistically indistinguishable ones. `--chi2` reports χ²/ndf over the bins
    whose errors are known, which is the right test there (and what `hep compare` will use, 07 §5).

The helper becomes `hekit.compare` in P9-S02; until then it lives under tests/ so nothing ships that
has not been used in anger.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BinDifference:
    index: int
    left: float
    right: float
    what: str = "value"                      # value | error | edge

    @property
    def relative(self) -> float:
        scale = max(abs(self.left), abs(self.right))
        return abs(self.left - self.right) / scale if scale > 0 else 0.0


@dataclass
class ObjectDifference:
    path: str
    reason: str = ""                         # set when the objects cannot be compared at all
    bins: list[BinDifference] = field(default_factory=list)

    @property
    def worst(self) -> float:
        return max((difference.relative for difference in self.bins), default=0.0)

    def __str__(self) -> str:
        if self.reason:
            return f"{self.path}: {self.reason}"
        first = self.bins[0]
        return (f"{self.path}: {len(self.bins)} of its numbers differ, worst {self.worst:.3g} "
                f"relative (bin {first.index} {first.what} {first.left:.8g} vs {first.right:.8g})")


@dataclass
class Report:
    left: str
    right: str
    compared: int = 0
    bins: int = 0
    only_left: list[str] = field(default_factory=list)
    only_right: list[str] = field(default_factory=list)
    differences: list[ObjectDifference] = field(default_factory=list)
    chi2: float = 0.0
    ndf: int = 0

    @property
    def identical(self) -> bool:
        return not (self.differences or self.only_left or self.only_right)

    @property
    def chi2_per_ndf(self) -> float:
        return self.chi2 / self.ndf if self.ndf else 0.0

    def table(self) -> str:
        lines = [f"{self.compared} objects compared, {self.bins} numbers"]
        if self.only_left:
            lines.append(f"  only in {self.left}: {', '.join(sorted(self.only_left))}")
        if self.only_right:
            lines.append(f"  only in {self.right}: {', '.join(sorted(self.only_right))}")
        for difference in self.differences:
            lines.append(f"  {difference}")
        if self.ndf:
            lines.append(f"  chi2/ndf = {self.chi2_per_ndf:.4g} ({self.chi2:.4g} / {self.ndf})")
        if self.identical:
            lines.append("  identical")
        return "\n".join(lines)


def _load(path: str | Path) -> dict:
    import yoda                              # imported here so --help works without YODA
    return yoda.read(str(path))


def _values(ao) -> list[tuple[str, float, float]]:
    """(label, value, error) for every number in an object, whatever its shape."""
    found: list[tuple[str, float, float]] = []
    bins = getattr(ao, "bins", None)
    if callable(bins):
        for index, entry in enumerate(ao.bins()):
            found.append((f"{index}", _number(entry, "val"), _number(entry, "totalErrAvg")))
        return found
    # A scalar estimate (/_XSEC, /_EVTCOUNT) or a counter.
    found.append(("0", _number(ao, "val"), _number(ao, "totalErrAvg")))
    return found


def _number(owner, name: str) -> float:
    """`val()`/`totalErrAvg()` where they exist, NaN where they do not — an object with no error
    defined is not the same thing as one whose error is zero."""
    method = getattr(owner, name, None)
    if method is None:
        return math.nan
    try:
        return float(method())
    except Exception:                        # YODA raises for an error with no source
        return math.nan


def _edges(ao) -> list[float]:
    getter = getattr(ao, "xEdges", None)
    if getter is None:
        return []
    try:
        return [float(edge) for edge in getter()]
    except Exception:                        # pragma: no cover - a non-1D object
        return []


def _close(left: float, right: float, rtol: float, atol: float) -> bool:
    if math.isnan(left) and math.isnan(right):
        return True                          # both undefined is agreement
    if math.isnan(left) or math.isnan(right):
        return False
    return abs(left - right) <= atol + rtol * max(abs(left), abs(right))


def compare(left_path: str | Path, right_path: str | Path, *, rtol: float = 1e-6,
            atol: float = 0.0, raw: bool = False, chi2: bool = False) -> Report:
    """Compare two YODA files. `raw=False` skips Rivet's `/RAW/` copies and `/TMP/` scratch objects."""
    left_objects, right_objects = _load(left_path), _load(right_path)

    def wanted(path: str) -> bool:
        return raw or not (path.startswith("/RAW/") or path.startswith("/TMP/"))

    left_paths = {path for path in left_objects if wanted(path)}
    right_paths = {path for path in right_objects if wanted(path)}
    report = Report(left=str(left_path), right=str(right_path),
                    only_left=sorted(left_paths - right_paths),
                    only_right=sorted(right_paths - left_paths))

    for path in sorted(left_paths & right_paths):
        left, right = left_objects[path], right_objects[path]
        report.compared += 1
        if type(left).__name__ != type(right).__name__:
            report.differences.append(ObjectDifference(
                path, f"{type(left).__name__} on the left, {type(right).__name__} on the right"))
            continue

        left_edges, right_edges = _edges(left), _edges(right)
        if left_edges != right_edges:
            report.differences.append(ObjectDifference(path, "the binning differs"))
            continue

        left_values, right_values = _values(left), _values(right)
        if len(left_values) != len(right_values):
            report.differences.append(ObjectDifference(
                path, f"{len(left_values)} numbers on the left, {len(right_values)} on the right"))
            continue

        found = ObjectDifference(path)
        for index, ((_, left_value, left_error), (_, right_value, right_error)) in enumerate(
                zip(left_values, right_values)):
            report.bins += 1
            if not _close(left_value, right_value, rtol, atol):
                found.bins.append(BinDifference(index, left_value, right_value, "value"))
            if not _close(left_error, right_error, rtol, atol):
                found.bins.append(BinDifference(index, left_error, right_error, "error"))
            if chi2:
                spread = math.hypot(0.0 if math.isnan(left_error) else left_error,
                                    0.0 if math.isnan(right_error) else right_error)
                if spread > 0:
                    report.chi2 += ((left_value - right_value) / spread) ** 2
                    report.ndf += 1
        if found.bins:
            report.differences.append(found)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two YODA files bin by bin.")
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--rtol", type=float, default=1e-6, help="relative tolerance (default 1e-6)")
    parser.add_argument("--atol", type=float, default=0.0, help="absolute tolerance (default 0)")
    parser.add_argument("--raw", action="store_true", help="also compare /RAW/ and /TMP/ objects")
    parser.add_argument("--chi2", action="store_true", help="also report chi2/ndf over the bins")
    arguments = parser.parse_args(argv)

    report = compare(arguments.left, arguments.right, rtol=arguments.rtol, atol=arguments.atol,
                     raw=arguments.raw, chi2=arguments.chi2)
    print(report.table())
    return 0 if report.identical else 1


if __name__ == "__main__":
    sys.exit(main())
