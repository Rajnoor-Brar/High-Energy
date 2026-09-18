"""Comparing two curves, honestly (07 §5).

This is the shared statistics module: `hep compare` uses it on results, `hep proc` (P9-S01) will use it
on fits, and `tests/tools/yodacmp.py` — written for the P2-S06 equivalence gate — is promoted into it,
so the comparison the gate trusts is the one the user sees.

Three rules that decide whether a number means anything:

* **only aligned bins are compared.** Two histograms with different binning have no bin-by-bin
  relationship; the pipeline's `align_to_edges` rule already says which bins line up, and only those
  count. The rest are reported as skipped, never silently dropped.
* **a voided bin is not a zero.** Voiding blanks bins that carry no information (00/B3's neighbour in
  07 §4), leaving NaN. A NaN bin is excluded from χ² rather than treated as a measurement of zero.
* **a bin with no error is excluded, and said so.** Dividing by a zero error is how a χ² becomes
  infinite and a study becomes nonsense; those bins are counted separately.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..plot import io
from ..plot.transform import edge_index


@dataclass
class BinPull:
    index: int
    left: float
    right: float
    spread: float

    @property
    def pull(self) -> float:
        return (self.left - self.right) / self.spread if self.spread > 0 else math.nan


@dataclass
class Comparison:
    """What comparing one histogram with another came to."""

    path: str
    chi2: float = 0.0
    ndf: int = 0
    used: int = 0
    skipped_unaligned: int = 0
    skipped_void: int = 0
    skipped_no_error: int = 0
    max_pull: float = 0.0
    max_pull_bin: int = 0
    note: str = ""

    @property
    def chi2_per_ndf(self) -> float:
        return self.chi2 / self.ndf if self.ndf else math.nan

    @property
    def comparable(self) -> bool:
        return self.ndf > 0

    def __str__(self) -> str:
        if not self.comparable:
            return f"{self.path}: not comparable ({self.note or 'no usable bins'})"
        return (f"{self.path}: chi2/ndf = {self.chi2_per_ndf:.3g} ({self.chi2:.4g}/{self.ndf}), "
                f"{self.used} bins, max pull {self.max_pull:.2g}")


def compare_objects(left: Any, right: Any, *, path: str = "") -> Comparison:
    """χ²/ndf, bins used and the largest pull between two 1D objects.

    `left` is the curve under test and `right` the reference. Errors are combined in quadrature,
    which is the right thing when the two are independent — a curve against *its own* smoothed
    version is not, and that is `hep proc`'s problem, not this one.
    """
    result = Comparison(path=path or getattr(left, "path", lambda: "")())
    left_edges, right_edges = io.edges_of(left), io.edges_of(right)
    if left_edges is None or right_edges is None:
        result.note = "not a binned 1D object"
        return result

    left_values, right_values = io.values_of(left), io.values_of(right)
    for index, (low, high) in enumerate(zip(left_edges, left_edges[1:])):
        # Aligned means both edges of this bin are edges of the reference too (07 §4's rule).
        first = edge_index(right_edges, low)
        second = edge_index(right_edges, high)
        if first is None or second is None or second != first + 1:
            result.skipped_unaligned += 1
            continue
        value, other = left_values[index], right_values[first]
        if math.isnan(value) or math.isnan(other):
            result.skipped_void += 1                       # a voided bin is not a measurement
            continue
        spread = math.hypot(_error(left, index + 1), _error(right, first + 1))
        if not spread > 0:
            result.skipped_no_error += 1
            continue
        pull = (value - other) / spread
        result.chi2 += pull * pull
        result.ndf += 1
        result.used += 1
        if abs(pull) > abs(result.max_pull):
            result.max_pull, result.max_pull_bin = pull, index + 1
    if not result.comparable and not result.note:
        result.note = _why(result)
    return result


def _error(obj: Any, number: int) -> float:
    try:
        error = float(obj.bin(number).totalErrAvg())
    except Exception:                                      # a void: its errors were removed
        return 0.0
    return 0.0 if math.isnan(error) else error


def _why(result: Comparison) -> str:
    if result.skipped_unaligned and not (result.skipped_void or result.skipped_no_error):
        return "no bins align"
    if result.skipped_void:
        return "every comparable bin was voided"
    if result.skipped_no_error:
        return "no bin has an error to divide by"
    return "no usable bins"


@dataclass
class Report:
    """Every histogram of one curve against one reference."""

    left: str
    right: str
    rows: list[Comparison] = field(default_factory=list)

    @property
    def total_chi2(self) -> float:
        return sum(row.chi2 for row in self.rows if row.comparable)

    @property
    def total_ndf(self) -> int:
        return sum(row.ndf for row in self.rows if row.comparable)

    @property
    def chi2_per_ndf(self) -> float:
        return self.total_chi2 / self.total_ndf if self.total_ndf else math.nan

    @property
    def worst(self) -> Comparison | None:
        comparable = [row for row in self.rows if row.comparable]
        return max(comparable, key=lambda row: abs(row.max_pull)) if comparable else None


def compare_files(left_path, right_path, *, analysis: str = "", reference: bool = True) -> Report:
    """Compare every histogram two files share.

    With `reference=True` the right-hand objects are looked up under `/REF/` as well, because that is
    where a reference lives after the data overlay (07 §4).
    """
    left_objects = io.read(left_path)
    right_objects = io.read(right_path)
    report = Report(left=str(left_path), right=str(right_path))

    for obj_path, obj in sorted(left_objects.items()):
        if obj_path.startswith(("/RAW/", "/REF/")) or not io.is_binned_1d(obj):
            continue
        parsed = io.split_object_path(obj_path)
        if parsed is None:
            continue
        if analysis and io.base_analysis(parsed[0]) != io.base_analysis(analysis):
            continue
        other = _match(right_objects, obj_path, parsed, reference=reference)
        if other is None:
            continue
        report.rows.append(compare_objects(obj, other, path=obj_path))
    return report


def _match(objects: dict[str, Any], obj_path: str, parsed: tuple[str, str], *,
           reference: bool) -> Any | None:
    """The object to compare against: the same path, its `/REF/` twin, or the same histogram of
    another analysis variant."""
    candidates = [obj_path]
    if reference:
        candidates.append("/REF" + obj_path)
        candidates.append(f"/REF/{io.base_analysis(parsed[0])}/{parsed[1]}")
    candidates.append(f"/{io.base_analysis(parsed[0])}/{parsed[1]}")
    for candidate in candidates:
        found = objects.get(candidate)
        if found is not None and io.is_binned_1d(found):
            return found
    return None
