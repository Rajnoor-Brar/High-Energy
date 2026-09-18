"""The plot pipeline (P4-S01).

The transforms are ports of code whose output was validated against real plots, and they were checked
against the originals bin for bin while `tools/` still existed. P4-S06 retired those tools, so the
comparison is gone and the fixtures stay: the *outputs* the old tools produced are still compared, in
`tests/integration/test_plot_vs_legacy.py`, against the files P0-S04 froze. That is the durable
evidence — captured results outlive the code that made them.

What is left here is the behaviour itself, and the three findings: the data overlay must be explicit
(00/B5), a merged page must not lose a curve to a name collision (00/B17), and nothing may be written
to a fixed temporary path (00/B19).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from hekit.errors import HepError
from hekit.plot import data as data_module
from hekit.plot import io, plotfile, select, transform

yoda = pytest.importorskip("yoda")

REPO = Path(__file__).resolve().parents[3]


# ── fixtures ─────────────────────────────────────────────────────────────────

def histogram(path: str, edges: list[float], values: list[float], *, entries: list[int] | None = None):
    """A finalized Rivet-shaped histogram, with the `/RAW/` counterpart Rivet writes beside it."""
    estimate = yoda.BinnedEstimate1D(edges, path)
    for index, value in enumerate(values, start=1):
        estimate.bin(index).setVal(value)
        estimate.bin(index).setErr(math.sqrt(abs(value)) if value else 0.0)
    if entries is None:
        return [estimate]
    raw = yoda.Histo1D(edges, "/RAW" + path)
    for index, count in enumerate(entries):
        middle = (edges[index] + edges[index + 1]) / 2
        for _ in range(count):
            raw.fill(middle, 1.0)
    return [estimate, raw]


def a_curve(directory: Path, name: str, values: list[float], *, analysis: str = "photo_eic",
            edges: list[float] | None = None, entries: list[int] | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    edges = edges or [0.0, 1.0, 2.0, 3.0, 4.0]
    objects = histogram(f"/{analysis}/d01-x01-y01", edges, values, entries=entries)
    objects += histogram(f"/{analysis}/d02-x01-y01", edges, [1.0] * len(values))
    counter = yoda.Counter("/_EVTCOUNT")
    counter.fill(1000.0)
    objects.append(counter)
    path = directory / f"{name}.yoda"
    yoda.write(objects, str(path))
    return path


@pytest.fixture
def page(tmp_path: Path) -> list[Path]:
    """Two curves of the same analysis: bin 2 is empty in both, bin 3 only in one."""
    return [a_curve(tmp_path, "a", [5.0, 0.0, 0.0, 2.0], entries=[50, 0, 0, 20]),
            a_curve(tmp_path, "b", [4.0, 0.0, 3.0, 1.0], entries=[40, 0, 3, 10])]


# ── voiding, against the legacy implementation ───────────────────────────────

def test_voiding_blanks_a_bin_that_is_empty_in_every_curve(page, tmp_path):
    ours, report = transform.void_bins(page, tmp_path / "ours", void_empty=True)
    # The count is of voided *bins of a plot*, not of curve-bins: one bin in one histogram, blanked
    # in every curve of the page.
    assert report.bins == 1 and report.histograms == 1
    for path in ours:
        assert math.isnan(values_of(path)[1]), "bin 2 is zero in both curves"
        assert not math.isnan(values_of(path)[0])


def test_voiding_blanks_a_bin_too_few_entries_went_into(page, tmp_path):
    ours, report = transform.void_bins(page, tmp_path / "ours", void_empty=True, min_entries=25)
    # bins 2, 3 and 4 go: one is empty everywhere, the others have 3 and 20 raw entries in a curve.
    first = io.read(ours[0])["/photo_eic/d01-x01-y01"]
    assert math.isnan(first.bin(2).val()) and math.isnan(first.bin(3).val())
    assert not math.isnan(first.bin(1).val())
    assert report.bins == 3 and "25 entries" in report.rule


def test_voiding_is_a_no_op_when_nothing_is_asked_for(page, tmp_path):
    ours, report = transform.void_bins(page, tmp_path / "ours")
    assert ours == page and report.bins == 0, "the files are not even copied"


def test_a_void_is_decided_across_the_page_not_per_curve(page, tmp_path):
    """Curves must agree about which bins exist, or the ratio panel compares different x ranges."""
    ours, _ = transform.void_bins(page, tmp_path / "ours", void_empty=True)
    masks = [[math.isnan(value) for value in values_of(path)] for path in ours]
    assert masks[0] == masks[1]


def values_of(path: Path) -> list[float]:
    return io.values_of(io.read(path)["/photo_eic/d01-x01-y01"])


# ── auto-range, against the legacy implementation ────────────────────────────

def test_auto_range_clips_to_the_filled_bins(page, tmp_path):
    blocks = plotfile.parse(transform.auto_range(page, "photo_eic", tmp_path / "out", pad=0))
    assert blocks["/photo_eic/d01-x01-y01"] == {"XMin": "0", "XMax": "4"}


def test_auto_range_pads_by_whole_bins(tmp_path):
    only_middle = a_curve(tmp_path, "c", [0.0, 7.0, 0.0, 0.0])
    blocks = plotfile.parse(transform.auto_range([only_middle], "photo_eic", tmp_path / "out", pad=1))
    assert blocks["/photo_eic/d01-x01-y01"] == {"XMin": "0", "XMax": "3"}
    tight = plotfile.parse(transform.auto_range([only_middle], "photo_eic", tmp_path / "out2", pad=0))
    assert tight["/photo_eic/d01-x01-y01"] == {"XMin": "1", "XMax": "2"}


def test_auto_range_says_nothing_when_there_is_nothing_to_say(tmp_path):
    path = tmp_path / "empty.yoda"
    yoda.write(histogram("/photo_eic/d01-x01-y01", [0.0, 1.0, 2.0], [0.0, 0.0]), str(path))
    assert transform.auto_range([path], "photo_eic", tmp_path / "out") is None


# ── alignment, against the legacy implementation ─────────────────────────────

def test_an_object_is_trimmed_to_its_longest_aligned_run(tmp_path):
    mc_edges = [0.0, 1.0, 2.0, 3.0, 4.0]
    reference = yoda.BinnedEstimate1D([0.5, 1.0, 2.0, 3.0], "/REF/x/d01-x01-y01")
    for index in range(1, 4):
        reference.bin(index).setVal(float(index))
    assert io.edges_of(transform.align_to_edges(reference, mc_edges)) == [1.0, 2.0, 3.0]


def test_an_aligned_object_is_returned_unchanged(tmp_path):
    reference = yoda.BinnedEstimate1D([0.0, 1.0, 2.0], "/REF/x/d01-x01-y01")
    assert transform.align_to_edges(reference, [0.0, 1.0, 2.0, 3.0]) is reference


def test_an_object_that_cannot_align_is_refused(tmp_path):
    reference = yoda.BinnedEstimate1D([0.1, 0.9, 1.7], "/REF/x/d01-x01-y01")
    assert transform.align_to_edges(reference, [0.0, 1.0, 2.0]) is None


# ── the data map (00/B5) ─────────────────────────────────────────────────────

@pytest.fixture
def reference_file(tmp_path: Path) -> Path:
    objects = []
    for name in ("d01-x01-y01", "d08-x01-y01"):
        estimate = yoda.BinnedEstimate1D([0.0, 1.0, 2.0, 3.0, 4.0], f"/REF/ZEUS_2012_I1116258/{name}")
        for index in range(1, 5):
            estimate.bin(index).setVal(index * 1.5)
        estimate.setAnnotation("IsRef", 1)
        objects.append(estimate)
    path = tmp_path / "zeus.yoda"
    yoda.write(objects, str(path))
    return path


def test_a_data_file_without_a_map_is_not_overlaid(page, reference_file, tmp_path):
    """00/B5: name matching once drew this experiment's data over a different observable."""
    result = data_module.overlay(data_file=reference_file, mapping={}, curves=page,
                                 analysis="photo_eic", destination=tmp_path / "data.yoda")
    assert not result.drew_anything
    assert result.path is None and not (tmp_path / "data.yoda").exists()
    assert any("[plot.data].map is empty" in warning for warning in result.warnings)
    assert any("00/B5" in warning for warning in result.warnings)


def test_a_mapped_reference_is_overlaid_on_the_named_histogram(page, reference_file, tmp_path):
    result = data_module.overlay(
        data_file=reference_file,
        mapping={"d01-x01-y01": "/REF/ZEUS_2012_I1116258/d08-x01-y01"},
        curves=page, analysis="photo_eic", destination=tmp_path / "data.yoda")
    assert result.drew_anything
    objects = io.read(result.path)
    assert list(objects) == ["/REF/photo_eic/d01-x01-y01"], \
        "the map decides, so d08 can legitimately be drawn on d01 when the user says so"
    assert io.is_reference(objects["/REF/photo_eic/d01-x01-y01"], "/REF/photo_eic/d01-x01-y01")


def test_a_map_that_names_something_missing_is_an_error(page, reference_file, tmp_path):
    with pytest.raises(HepError, match="which zeus.yoda does not have"):
        data_module.overlay(data_file=reference_file,
                            mapping={"d01-x01-y01": "/REF/ZEUS_2012_I1116258/d99-x01-y01"},
                            curves=page, analysis="photo_eic", destination=tmp_path / "d.yoda")

    with pytest.raises(HepError, match="which /photo_eic/ does not have"):
        data_module.overlay(data_file=reference_file,
                            mapping={"d99-x01-y01": "/REF/ZEUS_2012_I1116258/d01-x01-y01"},
                            curves=page, analysis="photo_eic", destination=tmp_path / "d.yoda")


def test_a_plain_curve_must_match_the_mc_binning(page, reference_file, tmp_path):
    """Not a reference: it is drawn as a curve, so a different binning cannot be rebinned onto it."""
    objects = io.read(reference_file)
    odd = yoda.BinnedEstimate1D([0.1, 1.1, 2.1], "/REF/ZEUS_2012_I1116258/d01-x01-y01")
    odd.setAnnotation("IsRef", 1)
    path = tmp_path / "odd.yoda"
    yoda.write([odd], str(path))

    result = data_module.overlay(data_file=path,
                                 mapping={"d01-x01-y01": "/REF/ZEUS_2012_I1116258/d01-x01-y01"},
                                 curves=page, analysis="photo_eic",
                                 destination=tmp_path / "data.yoda", reference=False)
    assert not result.drew_anything
    assert result.skipped["d01-x01-y01"] == "binning differs from the MC curve"
    assert any("reference = true" in warning for warning in result.warnings)


def test_data_can_be_kept_out_of_the_main_panel(page, reference_file, tmp_path):
    result = data_module.overlay(
        data_file=reference_file, mapping={"d01-x01-y01": "/REF/ZEUS_2012_I1116258/d01-x01-y01"},
        curves=page, analysis="photo_eic", destination=tmp_path / "data.yoda", show=False)
    obj = io.read(result.path)["/REF/photo_eic/d01-x01-y01"]
    assert obj.annotation("MainPanel") in {"0", 0}


def test_a_suggested_map_is_only_a_suggestion(page, reference_file, tmp_path):
    """`--suggest-data-map` offers name matches; the plot is still drawn from the config's map."""
    found = data_module.suggest_map(reference_file, page, "photo_eic")
    assert found == {"d01-x01-y01": "/REF/ZEUS_2012_I1116258/d01-x01-y01"}
    assert "d08-x01-y01" not in found, "the MC has no d08, so nothing is suggested for it"


# ── curve namespaces (00/B17) ────────────────────────────────────────────────

def test_merged_curves_keep_their_own_namespaces(tmp_path):
    """`ydmrg` merged points into one namespace, so two curves could collide and one vanish."""
    first = a_curve(tmp_path / "one", "eic_5x41", [1.0, 2.0, 3.0, 4.0])
    second = a_curve(tmp_path / "two", "eic_27x920", [4.0, 3.0, 2.0, 1.0])
    curves = [select.Curve(name="eic_5x41", path=first, analysis="photo_eic"),
              select.Curve(name="eic_27x920", path=second, analysis="photo_eic")]

    moved = select.with_namespaces(curves, tmp_path / "merged")
    paths = {}
    for curve in moved:
        for obj_path in io.read(curve.path):
            assert obj_path.startswith(f"/{curve.name}/"), obj_path
            paths.setdefault(obj_path, []).append(curve.name)
    assert all(len(owners) == 1 for owners in paths.values()), "no path has two owners"
    assert io.denamespaced("/eic_5x41/photo_eic/d01-x01-y01", "eic_5x41") == \
        "/photo_eic/d01-x01-y01"


def test_namespacing_keeps_reference_objects_under_ref(tmp_path):
    assert io.namespaced("/REF/photo_eic/d01", "p1") == "/REF/p1/photo_eic/d01"
    assert io.denamespaced("/REF/p1/photo_eic/d01", "p1") == "/REF/photo_eic/d01"


# ── selection ────────────────────────────────────────────────────────────────

def test_an_option_variant_is_a_curve_not_a_page(tmp_path):
    """03 §4: one generation holds every variant, so selecting one is selecting an object path."""
    objects = []
    for radius in ("0.4", "0.7"):
        objects += histogram(f"/photo_eic:R={radius}/d01-x01-y01", [0.0, 1.0, 2.0], [1.0, 2.0])
    path = tmp_path / "variants.yoda"
    yoda.write(objects, str(path))

    assert select.variants_in(path) == ["photo_eic:R=0.4", "photo_eic:R=0.7"]

    class Point:
        name = "eic_5x41"
        legend = "5x41"
        yoda = path

    curves = select.curves_for([Point()], analysis="photo_eic")
    assert [curve.name for curve in curves] == ["eic_5x41_R0.4", "eic_5x41_R0.7"]
    assert curves[0].options == {"R": "0.4"}
    assert curves[0].legend == "5x41 (R=0.4)"
    assert all(curve.point == "eic_5x41" for curve in curves)


def test_curves_from_different_plugins_are_unified(tmp_path):
    first = a_curve(tmp_path / "one", "a", [1.0, 2.0, 3.0, 4.0], analysis="photo_eic")
    second = a_curve(tmp_path / "two", "b", [2.0, 3.0, 4.0, 5.0], analysis="photo_5x41")
    curves = [select.Curve(name="a", path=first, analysis="photo_eic"),
              select.Curve(name="b", path=second, analysis="photo_5x41")]

    analysis = select.common_analysis(curves)
    assert analysis == "photo_eic"
    unified = select.unify(curves, analysis, tmp_path / "unified")
    assert unified[0].path == first, "the curve that already matches is left alone"
    assert "/photo_eic/d01-x01-y01" in io.read(unified[1].path)
    assert unified[1].path != second


def test_unify_keeps_the_options_of_a_renamed_variant(tmp_path):
    objects = histogram("/photo_5x41:R=0.4/d01-x01-y01", [0.0, 1.0, 2.0], [1.0, 2.0])
    path = tmp_path / "old.yoda"
    yoda.write(objects, str(path))
    curve = select.Curve(name="b", path=path, analysis="photo_5x41:R=0.4", options={"R": "0.4"})
    unified = select.unify([curve], "photo_eic", tmp_path / "unified")
    assert "/photo_eic:R=0.4/d01-x01-y01" in io.read(unified[0].path)


def test_the_plot_analysis_can_be_forced(tmp_path):
    curves = [select.Curve(name="a", path=tmp_path / "a.yoda", analysis="photo_5x41")]
    assert select.common_analysis(curves, override="photo_eic") == "photo_eic"


# ── object paths ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,expected", [
    ("/photo_eic/d01-x01-y01", ("photo_eic", "d01-x01-y01")),
    ("/REF/photo_eic/d01-x01-y01", ("photo_eic", "d01-x01-y01")),
    ("/photo_eic:R=0.4/d01-x01-y01", ("photo_eic:R=0.4", "d01-x01-y01")),
    ("/RAW/photo_eic/d01-x01-y01", None),
    ("/TMP/_BEAMPZ", None),
    ("/_EVTCOUNT", None),
    ("/photo_eic/_internal", None),
    ("/", None),
])
def test_object_paths_are_split_the_way_rivet_writes_them(path, expected):
    assert io.split_object_path(path) == expected


def test_a_plot_key_ignores_options():
    """Two option variants are two curves on one plot, so they share a key (07 §4)."""
    assert io.plot_key("/photo_eic:R=0.4/d01") == io.plot_key("/photo_eic:R=0.7/d01")
    assert io.plot_key("/photo_eic/d01") == "/photo_eic/d01"
    assert io.plot_key("/RAW/photo_eic/d01") is None


# ── .plot files ──────────────────────────────────────────────────────────────

def test_a_plot_file_is_parsed_and_written_back(tmp_path):
    source = tmp_path / "x.plot"
    source.write_text("# BEGIN PLOT /photo_eic/d01-x01-y01\nTitle=Jets\nLogY=1\n# END PLOT\n\n"
                      "# BEGIN PLOT /photo_eic/d02-x01-y01\nXLabel=$E_T$\n# END PLOT\n",
                      encoding="utf-8")
    blocks = plotfile.parse(source)
    assert blocks["/photo_eic/d01-x01-y01"] == {"Title": "Jets", "LogY": "1"}
    assert blocks["/photo_eic/d02-x01-y01"] == {"XLabel": "$E_T$"}
    written = plotfile.write(blocks, tmp_path / "out.plot")
    assert plotfile.parse(written) == blocks


def test_the_project_plot_file_is_found_in_the_build_tree_first():
    """The same search order as the plugin, so a .plot never comes from a different build."""
    found = plotfile.find("photo_eic", "PhotoProduction")
    if found is None:                                     # pragma: no cover - plugin not built
        pytest.skip("the PhotoProduction plugin is not built")
    assert found.name == "photo_eic.plot"
    assert "build" in found.parts or "analyses" in found.parts


def test_an_unknown_analysis_has_no_project_plot_file():
    assert plotfile.find("nothing_like_this", "PhotoProduction") is None


# ── nothing writes to a fixed temporary path (00/B19) ────────────────────────

def test_every_transform_writes_where_it_is_told(page, reference_file, tmp_path):
    before = set(Path("/tmp").iterdir())
    workdir = tmp_path / "work"
    voided, _ = transform.void_bins(page, workdir, void_empty=True)
    ranged = transform.auto_range(page, "photo_eic", workdir)
    overlaid = data_module.overlay(
        data_file=reference_file, mapping={"d01-x01-y01": "/REF/ZEUS_2012_I1116258/d01-x01-y01"},
        curves=page, analysis="photo_eic", destination=workdir / "data.yoda")
    for path in [*voided, ranged, overlaid.path]:
        if path is not None and Path(path) not in page:
            assert workdir in Path(path).parents, path
    # Nothing *new* appears in the shared temporary directory: the old tools left fixed names there
    # (00/B19), and this pipeline must not.
    assert not [path for path in Path("/tmp").glob("hekit-plot*")], "no fixed /tmp name is used"
    assert set(Path("/tmp").iterdir()) - before == set(), "nothing new in the shared temporary tree"


def test_writing_a_yoda_leaves_no_temporary(tmp_path):
    objects = histogram("/photo_eic/d01-x01-y01", [0.0, 1.0], [1.0])
    directory = tmp_path / "out"
    io.write(objects, directory / "out.yoda")
    assert [path.name for path in directory.iterdir()] == ["out.yoda"]
