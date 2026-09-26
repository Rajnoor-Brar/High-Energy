"""`hep plot` against `ydmrg`/`ydplt`, by their intermediates (P4-S02).

The HTML `rivet-mkhtml` produces is not the thing to compare — it carries timestamps, and it is the
*inputs* that decide what a plot shows. P0-S04 therefore kept, from a real run of the old tools, every
file they handed to `rivet-mkhtml`:

```
tests/golden/legacy_run/ydmrg/      void_000_*.yoda  void_001_*.yoda  photo_eic_data.yoda  auto_range.plot
tests/golden/legacy_run/ydplt_p1/   the same, for a single point
run.json["mkhtml"]                  the exact argument lists
```

This runs the new pipeline on the same YODAs with the same settings and compares those four things.
The one deliberate difference is the data map: `ydmrg` matched data to MC **by histogram name**
(00/B5), so the comparison passes that same mapping explicitly — which is exactly the point of the
finding. `suggest_map()` reproduces what the old tool did implicitly.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hekit.plot import data as data_module
from hekit.plot import io, page as page_module, plotfile, select, transform
from hekit.plot.backends import mkhtml

yoda = pytest.importorskip("yoda")

REPO = Path(__file__).resolve().parents[2]
GOLDEN = REPO / "tests" / "golden" / "legacy_run"
DATA = REPO / "datasets" / "zeus_eic.yoda"

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (GOLDEN / "run.json").is_file(),
                       reason="capture the golden legacy run first"),
]

#: what `legacy_mini.toml` set
SETTINGS = dict(void_empty=True, min_entries=10, auto_range=True, range_pad=1)
CURVES = [("mini_27x920_ep_MSTW", "MSTW 2008 LO"), ("mini_27x920_ep_NNLO", "NNPDF 2.3 QCD+QED LO")]


def golden() -> dict:
    return json.loads((GOLDEN / "run.json").read_text(encoding="utf-8"))


def points_for(names: list[tuple[str, str]]) -> list[page_module.PointFile]:
    return [page_module.PointFile(name=name, yoda=GOLDEN / f"{name}.yoda", legend=legend)
            for name, legend in names]


def build(names: list[tuple[str, str]], workdir: Path) -> page_module.Page:
    """The new pipeline, with the settings the legacy config used."""
    points = points_for(names)
    mapping = data_module.suggest_map(DATA, [point.yoda for point in points], "photo_eic")
    return page_module.prepare(points, workdir, name="page", project="PhotoProduction",
                               data_file=DATA, data_map=mapping, data_reference=True,
                               data_show=True, **SETTINGS)


def values(path: Path, obj_path: str) -> list[float]:
    return io.values_of(io.read(path)[obj_path])


def common_paths(left: Path, right: Path) -> list[str]:
    return sorted(set(io.read(left)) & set(io.read(right)))


# ── the page ydmrg drew ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def page(tmp_path_factory):
    return build(CURVES, tmp_path_factory.mktemp("page"))


def test_the_voided_curves_match_the_legacy_ones(page):
    """Every bin, including the NaNs voiding leaves behind."""
    for curve, (name, _) in zip(page.curves, CURVES):
        reference = GOLDEN / "ydmrg" / f"void_{CURVES.index((name, _)):03d}_{name}.yoda"
        assert reference.is_file(), reference
        mine, theirs = io.read(curve.path), io.read(reference)
        shared = sorted(set(mine) & set(theirs))
        assert len(shared) > 20, "the files should hold the same objects"
        for obj_path in shared:
            if not io.is_binned_1d(mine[obj_path]):
                continue
            assert io.values_of(mine[obj_path]) == pytest.approx(
                io.values_of(theirs[obj_path]), nan_ok=True, rel=1e-12), obj_path


def test_the_same_bins_were_voided(page):
    """The count is the interesting part: voiding is decided across the page, so a different rule
    would show up as a different number of NaNs."""
    mine = sum(1 for curve in page.curves
               for obj_path, obj in io.read(curve.path).items() if io.is_binned_1d(obj)
               for value in io.values_of(obj) if math.isnan(value))
    theirs = 0
    for index, (name, _) in enumerate(CURVES):
        objects = io.read(GOLDEN / "ydmrg" / f"void_{index:03d}_{name}.yoda")
        theirs += sum(1 for obj in objects.values() if io.is_binned_1d(obj)
                      for value in io.values_of(obj) if math.isnan(value))
    assert mine == theirs > 0


def test_the_auto_range_file_matches(page):
    assert page.ranges is not None
    assert plotfile.parse(page.ranges) == plotfile.parse(GOLDEN / "ydmrg" / "auto_range.plot")


def test_the_remapped_data_matches(page):
    """Given the same mapping, the overlaid reference must be the same file (00/B5 aside)."""
    assert page.data is not None and page.data.path is not None
    mine, theirs = io.read(page.data.path), io.read(GOLDEN / "ydmrg" / "photo_eic_data.yoda")
    assert sorted(mine) == sorted(theirs)
    for obj_path in sorted(mine):
        assert io.edges_of(mine[obj_path]) == io.edges_of(theirs[obj_path]), obj_path
        assert io.values_of(mine[obj_path]) == pytest.approx(io.values_of(theirs[obj_path]),
                                                             nan_ok=True), obj_path


def test_the_mkhtml_arguments_match(page):
    """Same flags, same order, same titles — only the paths differ, because they are ours."""
    mine = mkhtml.arguments(page, rivet_refs=False, data_legend="Data")
    theirs = golden()["mkhtml"]["ydmrg"]["inputs"]

    assert mine[:4] == theirs[:4] == ["--rmopts", "--no-rivet-refs", "--reflabel", "Data"]
    assert [entry.split(":Title=", 1)[-1] for entry in mine[4:6]] == \
           [entry.split(":Title=", 1)[-1] for entry in theirs[4:6]]
    assert [Path(entry.split(":Title=", 1)[0]).name for entry in mine[4:6]] == \
           [Path(entry.split(":Title=", 1)[0]).name for entry in theirs[4:6]]
    assert Path(mine[-1]).name == Path(theirs[-1]).name == "photo_eic_data.yoda"


def test_the_project_plot_file_is_the_same_analysis(page):
    """`ydmrg` used `sources/PhotoProduction/photo_eic.plot`; the analysis moved to `analyses/`."""
    assert page.plot_file is not None and page.plot_file.name == "photo_eic.plot"
    legacy_plot = REPO / "legacy" / "sources" / "PhotoProduction" / "photo_eic.plot"
    if legacy_plot.is_file():
        assert plotfile.parse(page.plot_file).keys() >= plotfile.parse(legacy_plot).keys()


# ── the single point ydplt drew ──────────────────────────────────────────────

def test_a_single_point_page_matches_ydplt(tmp_path):
    """`--points`: one curve is a page with one curve, and the same transforms apply."""
    single = build(CURVES[:1], tmp_path)
    reference = GOLDEN / "ydplt_p1" / f"void_000_{CURVES[0][0]}.yoda"
    mine, theirs = io.read(single.curves[0].path), io.read(reference)
    for obj_path in sorted(set(mine) & set(theirs)):
        if io.is_binned_1d(mine[obj_path]):
            assert io.values_of(mine[obj_path]) == pytest.approx(
                io.values_of(theirs[obj_path]), nan_ok=True, rel=1e-12), obj_path

    assert plotfile.parse(single.ranges) == plotfile.parse(GOLDEN / "ydplt_p1" / "auto_range.plot")
    arguments = mkhtml.arguments(single, data_legend="Data")
    theirs_arguments = golden()["mkhtml"]["ydplt_p1"]["inputs"]
    assert arguments[:4] == theirs_arguments[:4]
    assert len(arguments) == len(theirs_arguments)


def test_voiding_differs_between_a_page_and_a_single_point(tmp_path):
    """Not a defect: a bin that is empty in *every* curve of a page may be filled for one point, and
    both tools agree about that — which is why the fixtures differ."""
    page_bins = set(_nan_bins(build(CURVES, tmp_path / "page").curves[0].path))
    single_bins = set(_nan_bins(build(CURVES[:1], tmp_path / "single").curves[0].path))
    assert single_bins <= page_bins


def _nan_bins(path: Path) -> list[tuple[str, int]]:
    found = []
    for obj_path, obj in io.read(path).items():
        if io.is_binned_1d(obj):
            found += [(obj_path, index) for index, value in enumerate(io.values_of(obj))
                      if math.isnan(value)]
    return found


# ── what the new pipeline does differently, on purpose ───────────────────────

def test_without_a_map_the_data_is_not_overlaid_at_all(tmp_path):
    """00/B5: the legacy tools matched by name; this one refuses to guess."""
    points = points_for(CURVES)
    built = page_module.prepare(points, tmp_path, name="page", project="PhotoProduction",
                                data_file=DATA, data_map={}, **SETTINGS)
    assert built.data is not None and built.data.path is None
    assert any("00/B5" in warning for warning in built.warnings)
    arguments = mkhtml.arguments(built)
    assert not any("_data.yoda" in entry for entry in arguments)


def test_the_suggested_map_is_what_the_legacy_tool_did_implicitly():
    points = points_for(CURVES)
    found = data_module.suggest_map(DATA, [point.yoda for point in points], "photo_eic")
    overlaid = io.read(GOLDEN / "ydmrg" / "photo_eic_data.yoda")
    assert {f"/REF/photo_eic/{name}" for name in found} == set(overlaid)
