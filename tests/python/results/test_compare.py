"""`hep compare` and the shared statistics (P4-S04).

χ² is easy to compute and easy to compute *wrongly*, so the tests use fixtures whose answer is known by
hand: a curve one combined error away from its reference in every bin has χ²/ndf = 1, and a curve two
away has 4. The rest is about what must **not** enter the sum — unaligned bins, voided bins and bins
with no error — because each of those turns a χ² into a number that looks meaningful and is not.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from hekit.errors import HepError
from hekit.plot import page as page_module
from hekit.plot.select import Curve
from hekit.results import compare as compare_module
from hekit.results import stats

yoda = pytest.importorskip("yoda")

EDGES = [0.0, 1.0, 2.0, 3.0, 4.0]


def estimate(path: str, values, errors, edges=None):
    obj = yoda.BinnedEstimate1D(list(edges or EDGES), path)
    for index, (value, error) in enumerate(zip(values, errors), start=1):
        obj.bin(index).setVal(value)
        if error is None:
            obj.bin(index).rmErrs()
        else:
            obj.bin(index).setErr(error)
    return obj


# ── known answers ────────────────────────────────────────────────────────────

def test_identical_curves_have_no_chi2():
    obj = estimate("/photo_eic/d01", [10.0, 20.0, 30.0, 40.0], [1.0, 1.0, 1.0, 1.0])
    found = stats.compare_objects(obj, obj.clone())
    assert found.chi2 == 0.0 and found.ndf == 4
    assert found.chi2_per_ndf == 0.0 and found.max_pull == 0.0


def test_one_sigma_apart_gives_chi2_per_ndf_of_one():
    """Errors combine in quadrature: 1 and 1 make √2, so a √2 offset is one pull."""
    spread = math.sqrt(2.0)
    left = estimate("/photo_eic/d01", [10 + spread, 20 + spread, 30 + spread, 40 + spread],
                    [1.0] * 4)
    right = estimate("/photo_eic/d01", [10.0, 20.0, 30.0, 40.0], [1.0] * 4)
    found = stats.compare_objects(left, right)
    assert found.ndf == 4
    assert found.chi2 == pytest.approx(4.0)
    assert found.chi2_per_ndf == pytest.approx(1.0)
    assert found.max_pull == pytest.approx(1.0)


def test_two_sigma_apart_gives_four():
    spread = 2 * math.sqrt(2.0)
    left = estimate("/photo_eic/d01", [10 + spread] * 4, [1.0] * 4)
    right = estimate("/photo_eic/d01", [10.0] * 4, [1.0] * 4)
    found = stats.compare_objects(left, right)
    assert found.chi2_per_ndf == pytest.approx(4.0)
    assert found.max_pull == pytest.approx(2.0)


def test_the_largest_pull_is_reported_with_its_bin_and_sign():
    left = estimate("/photo_eic/d01", [10.0, 20.0, 27.0, 40.0], [1.0] * 4)
    right = estimate("/photo_eic/d01", [10.0, 20.0, 30.0, 40.0], [1.0] * 4)
    found = stats.compare_objects(left, right)
    assert found.max_pull == pytest.approx(-3 / math.sqrt(2.0))
    assert found.max_pull_bin == 3
    assert found.max_pull < 0, "the sign says which way it moved"


def test_errors_from_both_sides_count():
    """A reference with its own error makes the comparison less significant, not more."""
    left = estimate("/photo_eic/d01", [12.0], [3.0], edges=[0.0, 1.0])
    right = estimate("/photo_eic/d01", [10.0], [4.0], edges=[0.0, 1.0])
    found = stats.compare_objects(left, right)
    assert found.max_pull == pytest.approx(2.0 / 5.0)      # hypot(3, 4) = 5


# ── what must not enter the sum ──────────────────────────────────────────────

def test_only_aligned_bins_are_used():
    """Verification row 'Alignment': two binnings with no relationship have no bin-by-bin χ²."""
    left = estimate("/photo_eic/d01", [10.0, 20.0, 30.0, 40.0], [1.0] * 4)
    right = estimate("/photo_eic/d01", [10.0, 20.0], [1.0] * 2, edges=[0.0, 2.0, 4.0])
    found = stats.compare_objects(left, right)
    assert found.used == 0 and found.skipped_unaligned == 4
    assert not found.comparable and found.note == "no bins align"
    assert math.isnan(found.chi2_per_ndf)


def test_a_partly_aligned_binning_uses_the_bins_that_line_up():
    left = estimate("/photo_eic/d01", [10.0, 20.0, 30.0, 40.0], [1.0] * 4)
    # The reference covers 1–3 with the same edges, and nothing else.
    right = estimate("/photo_eic/d01", [20.0, 31.0], [1.0] * 2, edges=[1.0, 2.0, 3.0])
    found = stats.compare_objects(left, right)
    assert found.used == 2 and found.skipped_unaligned == 2
    assert found.chi2 == pytest.approx(0.5)                # only bin 3 differs, by 1/√2


def test_voided_bins_are_excluded_not_counted_as_zero():
    """A void means "no information" (07 §4); treating it as a measurement of zero would invent a
    huge χ² out of a deliberately blanked bin."""
    left = estimate("/photo_eic/d01", [10.0, float("nan"), 30.0, 40.0], [1.0, None, 1.0, 1.0])
    right = estimate("/photo_eic/d01", [10.0, 20.0, 30.0, 40.0], [1.0] * 4)
    found = stats.compare_objects(left, right)
    assert found.used == 3 and found.skipped_void == 1
    assert found.chi2 == 0.0


def test_a_bin_with_no_error_is_excluded_and_counted():
    """Dividing by zero is how a χ² becomes infinite and a study becomes nonsense."""
    left = estimate("/photo_eic/d01", [11.0, 20.0], [0.0, 1.0], edges=[0.0, 1.0, 2.0])
    right = estimate("/photo_eic/d01", [10.0, 20.0], [0.0, 1.0], edges=[0.0, 1.0, 2.0])
    found = stats.compare_objects(left, right)
    assert found.used == 1 and found.skipped_no_error == 1
    assert math.isfinite(found.chi2)


def test_a_comparison_with_nothing_usable_says_why():
    left = estimate("/photo_eic/d01", [float("nan")] * 2, [None, None], edges=[0.0, 1.0, 2.0])
    right = estimate("/photo_eic/d01", [1.0, 2.0], [1.0, 1.0], edges=[0.0, 1.0, 2.0])
    found = stats.compare_objects(left, right)
    assert not found.comparable
    assert "voided" in found.note
    assert "not comparable" in str(found)


# ── whole files ──────────────────────────────────────────────────────────────

def a_file(tmp_path: Path, name: str, values, *, reference: bool = False) -> Path:
    prefix = "/REF/photo_eic" if reference else "/photo_eic"
    objects = [estimate(f"{prefix}/d01-x01-y01", values, [1.0] * len(values)),
               estimate(f"{prefix}/d02-x01-y01", values, [1.0] * len(values))]
    if reference:
        for obj in objects:
            obj.setAnnotation("IsRef", 1)
    path = tmp_path / f"{name}.yoda"
    yoda.write(objects, str(path))
    return path


def test_two_files_are_compared_histogram_by_histogram(tmp_path):
    left = a_file(tmp_path, "left", [10.0, 20.0, 30.0, 40.0])
    right = a_file(tmp_path, "right", [10.0, 20.0, 30.0, 41.0])
    report = stats.compare_files(left, right)
    assert [row.path for row in report.rows] == ["/photo_eic/d01-x01-y01", "/photo_eic/d02-x01-y01"]
    assert report.total_ndf == 8
    # The last bin differs by 1.0 in *both* histograms of the file: 2 x (1/sqrt(2))^2 = 1.0.
    assert report.total_chi2 == pytest.approx(1.0)
    assert report.chi2_per_ndf == pytest.approx(1.0 / 8)
    assert report.worst.path in {"/photo_eic/d01-x01-y01", "/photo_eic/d02-x01-y01"}


def test_a_reference_file_is_matched_under_ref(tmp_path):
    left = a_file(tmp_path, "left", [10.0, 20.0, 30.0, 40.0])
    right = a_file(tmp_path, "data", [10.0, 20.0, 30.0, 40.0], reference=True)
    report = stats.compare_files(left, right, reference=True)
    assert len(report.rows) == 2 and report.total_chi2 == 0.0


# ── the table ────────────────────────────────────────────────────────────────

def a_page(tmp_path: Path) -> page_module.Page:
    curves = []
    for name, values in (("base", [10.0, 20.0, 30.0, 40.0]), ("shifted", [11.0, 21.0, 31.0, 41.0])):
        path = a_file(tmp_path, name, values)
        curves.append(Curve(name=name, path=path, analysis="photo_eic", legend=name))
    return page_module.Page(name="by_pdf", analysis="photo_eic", curves=curves, workdir=tmp_path)


def test_comparing_against_a_curve_of_the_page(tmp_path):
    """`--ref POINT`: how far each variation is from the baseline."""
    table = compare_module.against_curve(a_page(tmp_path), "base")
    assert table.reference == "base"
    assert {row.curve for row in table.rows} == {"shifted"}, "the reference is not compared to itself"
    assert {row.histogram for row in table.rows} == {"d01-x01-y01", "d02-x01-y01"}
    assert all(row.comparison.chi2_per_ndf == pytest.approx(0.5) for row in table.rows)


def test_an_unknown_reference_names_the_curves(tmp_path):
    with pytest.raises(HepError, match="curves: base, shifted"):
        compare_module.against_curve(a_page(tmp_path), "nothing")


def test_comparing_against_data_needs_data(tmp_path):
    with pytest.raises(HepError, match="no reference data"):
        compare_module.against_reference(a_page(tmp_path))


def test_comparing_against_the_overlaid_reference(tmp_path):
    from hekit.plot import data as data_module

    page = a_page(tmp_path)
    page.data = data_module.DataOverlay(
        path=a_file(tmp_path, "data", [10.0, 20.0, 30.0, 40.0], reference=True),
        mapped={"d01-x01-y01": "x"})
    table = compare_module.against_reference(page)
    assert {row.curve for row in table.rows} == {"base", "shifted"}
    per_curve = table.per_curve()
    assert per_curve["base"].total_chi2 == pytest.approx(0.0)
    assert per_curve["shifted"].chi2_per_ndf == pytest.approx(0.5)


def test_the_table_is_written_as_markdown(tmp_path, redirect_results):
    table = compare_module.against_curve(a_page(tmp_path), "base")
    written = table.write(tmp_path / "study")
    text = written.read_text(encoding="utf-8")
    assert written.name == "compare.md"
    assert "| curve | histogram | chi2/ndf | bins | max pull | note |" in text
    assert "shifted" in text and "d01-x01-y01" in text
    assert "## Totals" in text
    assert not list((tmp_path / "study").glob("*.tmp.*")), "written atomically like everything else"


def test_the_table_reports_what_it_skipped(tmp_path):
    left = a_file(tmp_path, "left", [10.0, float("nan"), 30.0, 40.0])
    right = a_file(tmp_path, "right", [10.0, 20.0, 30.0, 40.0])
    page = page_module.Page(
        name="p", analysis="photo_eic", workdir=tmp_path,
        curves=[Curve(name="left", path=left, analysis="photo_eic"),
                Curve(name="right", path=right, analysis="photo_eic")])
    table = compare_module.against_curve(page, "right")
    assert "voided" in table.markdown()
