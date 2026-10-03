"""Paint against the legacy plotting (P3 S2 rows 2–3): ranges, voids and gutters, by --dump-ranges.

The legacy run (tests/reference/legacy_run) kept what its ydmrg step made from the two mini YODAs:
the voided copies (min_entries = 10, voided across both curves) and auto_range.plot (padded by one
bin, over the curves and the data). Paint must reproduce both for every object, from the raw YODAs.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import tomllib
from pathlib import Path

import pytest
import tomli_w

REPO = Path(__file__).resolve().parents[2]
PAINT = REPO / "build" / "Paint.exe"
YD2RT = REPO / "build" / "App_yd2rt.exe"
LEGACY = REPO / "tests" / "reference" / "legacy_run"
OBJECTS = [f"d{n:02d}-x01-y01" for n in range(1, 18)]

pytestmark = pytest.mark.skipif(not (PAINT.exists() and YD2RT.exists()), reason="make build/Paint.exe build/App_yd2rt.exe")


@pytest.fixture(scope="module")
def inputs(tmp_path_factory) -> dict[str, Path]:
    where = tmp_path_factory.mktemp("paint")
    out = {}
    for name, source in (("MSTW", LEGACY / "mini_27x920_ep_MSTW.yoda"), ("NNLO", LEGACY / "mini_27x920_ep_NNLO.yoda"),
                         ("data", LEGACY / "ydmrg" / "photo_eic_data.yoda")):
        out[name] = where / f"{name}.root"
        done = subprocess.run([str(YD2RT), str(source), str(out[name]), "--keep-raw"], capture_output=True, text=True, encoding="utf-8")
        assert done.returncode == 0, done.stderr
    out["dir"] = where
    return out


def page(inputs, obj: str, *, data: str | None = None, **keys) -> Path:
    document = {
        "page": {"name": obj, "output": str(inputs["dir"] / obj), **keys},
        "curve": [{"file": str(inputs[n]), "object": f"photo_eic/{obj}", "raw": f"RAW/photo_eic/{obj}", "label": n}
                  for n in ("MSTW", "NNLO")],
    }
    if data:
        document["data"] = {"file": str(inputs["data"]), "object": f"REF/photo_eic/{data}", "label": "data"}
    path = inputs["dir"] / f"{obj}.{abs(hash(json.dumps(keys, sort_keys=True, default=str)))}.toml"
    path.write_text(tomli_w.dumps(document))
    return path


def dump(path: Path) -> dict:
    done = subprocess.run([str(PAINT), str(path), "--dump-ranges"], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def legacy_ranges() -> dict[str, tuple[float, float]]:
    text = (LEGACY / "ydmrg" / "auto_range.plot").read_text()
    return {m[0]: (float(m[1]), float(m[2]))
            for m in re.findall(r"# BEGIN PLOT /photo_eic/(\S+)\nXMin=(\S+)\nXMax=(\S+)", text)}


def legacy_voids(name: str) -> dict[str, list[int]]:
    """1-based indices of the NaN bins of every Estimate1D in a legacy voided YODA."""
    text = (LEGACY / "ydmrg" / name).read_text()
    out = {}
    for obj, body in re.findall(r"BEGIN YODA_ESTIMATE1D_V3 /photo_eic/(\S+)\n(.*?)END YODA", text, re.S):
        rows = [line.split()[0] for line in body.split("# value", 1)[1].splitlines()[1:] if line.strip()]
        out[obj] = [i for i, value in enumerate(rows[1:-1], start=1) if value == "nan"]   # without under/overflow
    return out


LEGACY_PAGE = {"void_empty": True, "min_entries": 10, "auto_range": True, "range_pad": 1}


def test_auto_range_equals_the_legacy_ranges(inputs):
    want = legacy_ranges()
    assert sorted(want) == OBJECTS
    for obj in OBJECTS:
        got = dump(page(inputs, obj, data=obj if obj <= "d12" else None, **LEGACY_PAGE))["x"]
        assert got == pytest.approx(list(want[obj]), rel=1e-5), obj      # the legacy file wrote %g


def test_voided_bins_equal_the_legacy_voids(inputs):
    mstw, nnlo = legacy_voids("void_000_mini_27x920_ep_MSTW.yoda"), legacy_voids("void_001_mini_27x920_ep_NNLO.yoda")
    assert sorted(mstw) == OBJECTS and mstw == nnlo                          # voided across the page
    for obj in OBJECTS:
        assert dump(page(inputs, obj, **LEGACY_PAGE))["voided"] == mstw[obj], obj


def test_y_gutter_puts_the_top_at_one_plus_the_gutter_times_the_largest(inputs):
    uproot = pytest.importorskip("uproot")
    for obj in ("d01-x01-y01", "d02-x01-y01", "d13-x01-y01"):
        ranges = dump(page(inputs, obj, auto_range=False, y_gutter=0.5))
        largest = max(max(uproot.open(inputs[n])[f"photo_eic/{obj}"].values()) for n in ("MSTW", "NNLO"))
        assert ranges["largest"] == pytest.approx(largest, rel=1e-9)
        assert ranges["y"][1] == pytest.approx(1.5 * largest, rel=1e-9)
        assert ranges["y"][0] == 0.0


def test_x_gutter_widens_symmetrically(inputs):
    plain = dump(page(inputs, "d02-x01-y01", **LEGACY_PAGE))["x"]
    wide = dump(page(inputs, "d02-x01-y01", x_gutter=0.2, **LEGACY_PAGE))["x"]
    assert wide[1] - wide[0] == pytest.approx(1.2 * (plain[1] - plain[0]))
    assert wide[0] + wide[1] == pytest.approx(plain[0] + plain[1])


def test_log_y_gutter_is_a_fraction_of_the_decades(inputs):
    ranges = dump(page(inputs, "d01-x01-y01", logy=True, y_gutter=0.5, **LEGACY_PAGE))
    low, high, largest = ranges["y"][0], ranges["y"][1], ranges["largest"]
    assert low > 0
    assert math.log10(high / largest) == pytest.approx(0.5 * math.log10(largest / low))


def test_a_zero_gutter_ends_the_axis_at_the_largest_value(inputs):
    """V55: 0 is a gutter like any other (no headroom); only "default" leaves the range to ROOT."""
    ranges = dump(page(inputs, "d02-x01-y01", y_gutter=0, **LEGACY_PAGE))
    assert not ranges["y_tool"] and ranges["y"][1] == pytest.approx(ranges["largest"], rel=1e-12)


def test_no_gutter_leaves_the_range_to_root(inputs):
    """"default": the range ROOT picks for one histogram holding every drawn value (THistPainter:
    5% of the span above and below, 0 if that crosses it; on a log axis ×0.5 below and ×2·0.9/0.95 above)."""
    for value in ("default",):
        linear = dump(page(inputs, "d02-x01-y01", y_gutter=value, x_gutter=value, **LEGACY_PAGE))
        assert linear["y_tool"] and not linear["x_tool"]                    # x is auto_range's, not the tool's
        assert linear["x"] == dump(page(inputs, "d02-x01-y01", **LEGACY_PAGE))["x"]
        top, bottom = linear["y"][1], linear["y"][0]
        assert 0.0 <= bottom < linear["largest"]                                 # d02 sits well above 0
        assert top == pytest.approx(linear["largest"] + 0.05 * (linear["largest"] - bottom), rel=1e-9)
        log = dump(page(inputs, "d01-x01-y01", logy=True, y_gutter=value, **LEGACY_PAGE))
        assert log["y"][1] == pytest.approx(log["largest"] * 2 * 0.9 / 0.95, rel=1e-9)
    assert dump(page(inputs, "d02-x01-y01", x_gutter="default", auto_range=False))["x_tool"]


def test_a_gutter_is_a_number_or_default(inputs):
    for bad in (-1, "auto"):
        done = subprocess.run([str(PAINT), str(page(inputs, "d02-x01-y01", y_gutter=bad)), "--dump-ranges"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert done.returncode == 1 and "y_gutter" in done.stdout + done.stderr


def test_data_that_lines_up_nowhere_is_dropped(inputs):
    # an eta table of the data against an ET histogram: no edge in common
    assert dump(page(inputs, "d01-x01-y01", data="d02-x01-y01"))["data_bins"] == 0
    assert dump(page(inputs, "d01-x01-y01", data="d01-x01-y01"))["data_bins"] > 0


def test_a_page_is_saved_in_every_format(inputs):
    config = page(inputs, "d01-x01-y01", data="d01-x01-y01", formats=["pdf", "png", "svg"], ratio=True,
                  logy=True, title="-3.5 < #eta < 3.5", x_label="E_{T} [GeV]", **LEGACY_PAGE)
    done = subprocess.run([str(PAINT), str(config)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    for fmt in ("pdf", "png", "svg"):
        assert (inputs["dir"] / f"d01-x01-y01.{fmt}").stat().st_size > 1000


def test_exit_codes(inputs):
    usage = subprocess.run([str(PAINT)], capture_output=True, text=True, encoding="utf-8")
    bad = inputs["dir"] / "bad.toml"
    bad.write_text("[page]\nname = 'x'\n")                                   # no output, no curves
    missing = page(inputs, "d99-x01-y01")
    assert usage.returncode == 2
    assert subprocess.run([str(PAINT), str(bad)], capture_output=True).returncode == 1
    assert subprocess.run([str(PAINT), str(missing)], capture_output=True).returncode == 4


# ── v1's transform vectors (tests/python/plot/test_plot_pipeline.py at rework/v1-final) ────────

def v1_curve(where: Path, name: str, values, *, edges=(0.0, 1.0, 2.0, 3.0, 4.0), entries=None) -> Path:
    """A Rivet-shaped histogram, and its /RAW twin when `entries` is given, converted to ROOT."""
    yoda = pytest.importorskip("yoda")
    estimate = yoda.BinnedEstimate1D(list(edges), "/photo_eic/d01-x01-y01")
    for index, value in enumerate(values, start=1):
        estimate.bin(index).setVal(value)
        estimate.bin(index).setErr(math.sqrt(abs(value)) if value else 0.0)
    objects = [estimate]
    if entries is not None:
        raw = yoda.Histo1D(list(edges), "/RAW/photo_eic/d01-x01-y01")
        for index, count in enumerate(entries):
            for _ in range(count):
                raw.fill((edges[index] + edges[index + 1]) / 2, 1.0)
        objects.append(raw)
    source, target = where / f"{name}.yoda", where / f"{name}.root"
    yoda.write(objects, str(source))
    assert subprocess.run([str(YD2RT), str(source), str(target), "--keep-raw"], capture_output=True).returncode == 0
    return target


def v1_page(where: Path, curves: list[Path], *, data: Path | None = None, **keys) -> dict:
    keys = {"auto_range": True, **keys}             # v1's rule, stated: a page without it is ROOT's own range (V55)
    document = {"page": {"name": "v1", "output": str(where / "v1"), **keys},
                "curve": [{"file": str(c), "object": "photo_eic/d01-x01-y01", "label": c.stem,
                           **({"raw": "RAW/photo_eic/d01-x01-y01"} if keys.get("min_entries") else {})} for c in curves]}
    if data:
        document["data"] = {"file": str(data), "object": "photo_eic/d01-x01-y01", "label": "data"}
    path = where / f"v1.{len(list(where.glob('v1.*.toml')))}.toml"
    path.write_text(tomli_w.dumps(document))
    return dump(path)


@pytest.fixture
def v1(scratch):
    """Two curves: bin 2 is empty in both, bin 3 only in one."""
    return scratch, [v1_curve(scratch, "a", [5.0, 0.0, 0.0, 2.0], entries=[50, 0, 0, 20]),
                     v1_curve(scratch, "b", [4.0, 0.0, 3.0, 1.0], entries=[40, 0, 3, 10])]


def test_v1_a_bin_empty_in_every_curve_is_voided(v1):
    where, curves = v1
    assert v1_page(where, curves, void_empty=True)["voided"] == [2]


def test_v1_a_bin_too_few_entries_went_into_is_voided(v1):
    where, curves = v1
    assert v1_page(where, curves, void_empty=True, min_entries=25)["voided"] == [2, 3, 4]


def test_v1_voiding_is_a_no_op_when_nothing_is_asked_for(v1):
    where, curves = v1
    assert v1_page(where, curves)["voided"] == []


def test_v1_auto_range_clips_to_the_filled_bins(v1):
    where, curves = v1
    assert v1_page(where, curves, range_pad=0)["x"] == [0, 4]


def test_v1_auto_range_pads_by_whole_bins(scratch):
    middle = [v1_curve(scratch, "c", [0.0, 7.0, 0.0, 0.0])]
    assert v1_page(scratch, middle, range_pad=1)["x"] == [0, 3]
    assert v1_page(scratch, middle, range_pad=0)["x"] == [1, 2]


def test_v1_nothing_filled_leaves_the_full_range(scratch):
    empty = [v1_curve(scratch, "e", [0.0, 0.0], edges=(0.0, 1.0, 2.0))]
    assert v1_page(scratch, empty)["x"] == [0, 2]


def test_v1_data_is_trimmed_to_its_longest_aligned_run(scratch):
    mc = [v1_curve(scratch, "mc", [1.0, 1.0, 1.0, 1.0])]
    aligned = v1_curve(scratch, "ref", [1.0, 2.0, 3.0], edges=(0.5, 1.0, 2.0, 3.0))
    unaligned = v1_curve(scratch, "bad", [1.0, 2.0], edges=(0.1, 0.9, 1.7))
    assert v1_page(scratch, mc, data=aligned)["data_bins"] == 2           # [1, 2, 3]: the 0.5 edge goes
    assert v1_page(scratch, mc, data=unaligned)["data_bins"] == 0


# ── the style (Style.hh, utils/Apps/Paint/base.toml) ─────────────────────────────────────────

def dump_style(path: Path | None = None, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(PAINT), *([str(path)] if path else []), "--dump-style", *extra],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")


def test_the_base_style_is_base_toml():
    done = dump_style()
    assert done.returncode == 0, done.stderr
    assert tomllib.loads(done.stdout) == tomllib.loads((REPO / "utils/Apps/Paint/base.toml").read_text(encoding="utf-8"))


def test_a_page_style_merges_over_the_base_and_is_checked(inputs):
    config = page(inputs, "d01-x01-y01", formats=["png"])
    document = tomllib.loads(config.read_text())
    document["style"] = {"page": {"dpi": 100}, "legend": {"position": [0.4, 0.9]}}
    config.write_text(tomli_w.dumps(document))
    merged = tomllib.loads(dump_style(config).stdout)
    assert merged["page"]["dpi"] == 100 and merged["legend"]["position"] == [0.4, 0.9]
    assert merged["text"] == tomllib.loads((REPO / "utils/Apps/Paint/base.toml").read_text(encoding="utf-8"))["text"]
    done = subprocess.run([str(PAINT), str(config)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    Image = pytest.importorskip("PIL.Image")
    assert Image.open(inputs["dir"] / "d01-x01-y01.png").size == (467, 421)   # size × dpi
    for bad, message in (({"legend": {"place": 1}}, "legend.place"), ({"page": {"dpi": "x"}}, "page.dpi"),
                         ({"curves": {"errors": "dots"}}, "curves.errors")):
        document["style"] = bad
        config.write_text(tomli_w.dumps(document))
        done = subprocess.run([str(PAINT), str(config)], capture_output=True, text=True, encoding="utf-8")
        assert done.returncode == 1 and message in done.stderr + done.stdout


def test_many_pages_in_one_paint_each_with_its_outcome_and_ranges(inputs):
    """V64: one ROOT for many pages; a bad page does not stop the rest; --ranges writes what --dump-ranges prints."""
    good = page(inputs, "d01-x01-y01", **LEGACY_PAGE)
    other = page(inputs, "d02-x01-y01", **LEGACY_PAGE)
    bad = inputs["dir"] / "broken.toml"
    bad.write_text('[page]\nname = "x"\noutput = "/nonexistent/dir/x"\n', encoding="utf-8")   # no [[curve]]
    done = subprocess.run([str(PAINT), str(good), str(bad), str(other), "--ranges"], capture_output=True, text=True,
                          encoding="utf-8")
    lines = [json.loads(l) for l in done.stdout.splitlines() if l.startswith("{")]
    assert done.returncode == 1 and [l["ok"] for l in lines] == [True, False, True]
    assert "curve" in lines[1]["error"]
    for config in (good, other):
        written = json.loads(Path(str(config) + ".ranges.json").read_text())
        assert written == dump(config)


def test_a_curve_may_have_its_own_look(inputs):
    """V67: a curve's style (colour, line, width) is drawn; an unknown line is the page's error."""
    config = page(inputs, "d01-x01-y01")
    document = tomllib.loads(config.read_text(encoding="utf-8"))
    document["curve"][0]["style"] = {"colour": "#109618", "line": "dashed", "width": 2.0}
    config.write_text(tomli_w.dumps(document), encoding="utf-8")
    assert subprocess.run([str(PAINT), str(config)], capture_output=True).returncode == 0
    document["curve"][1]["style"] = {"line": "wavy"}
    config.write_text(tomli_w.dumps(document), encoding="utf-8")
    done = subprocess.run([str(PAINT), str(config)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 1 and "style.line" in done.stdout + done.stderr


def test_normalise_scales_every_curve_to_unit_area(v1):
    """V68: Σ y·Δx = 1 per curve over the drawn bins; a: 5/7 at most, b: 4/8."""
    where, curves = v1
    assert v1_page(where, curves)["largest"] == pytest.approx(5.0)
    assert v1_page(where, curves, normalise="area")["largest"] == pytest.approx(5.0 / 7.0)
    assert v1_page(where, curves, normalise=False)["largest"] == pytest.approx(5.0)


def test_normalise_is_area_or_false(v1):
    where, curves = v1
    path = where / "bad_normalise.toml"
    path.write_text(tomli_w.dumps({"page": {"name": "v1", "output": str(where / "v1"), "normalise": "peak"},
                                   "curve": [{"file": str(curves[0]), "object": "photo_eic/d01-x01-y01", "label": "a"}]}))
    done = subprocess.run([str(PAINT), str(path), "--dump-ranges"], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 1 and "normalise" in done.stdout + done.stderr
