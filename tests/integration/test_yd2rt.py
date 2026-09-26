"""App_yd2rt against YODA's own reading (P3 S1 rows 1–2): every object's contents and errors equal."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "build" / "App_yd2rt.exe"
REFERENCE = REPO / "tests" / "reference" / "legacy_run" / "mini_27x920_ep_MSTW.yoda"

pytestmark = pytest.mark.skipif(not APP.exists(), reason="make utils/App_yd2rt.exe")
uproot = pytest.importorskip("uproot")
yoda = pytest.importorskip("yoda")


def convert(source: Path, target: Path, *extra) -> subprocess.CompletedProcess:
    return subprocess.run([str(APP), str(source), str(target), *extra], capture_output=True, text=True)


def test_every_histogram_equals_the_yoda_values(scratch):
    out = scratch / "mini.root"
    assert convert(REFERENCE, out).returncode == 0
    root = uproot.open(out)
    compared = 0
    for path, ao in yoda.read(str(REFERENCE)).items():
        if path.startswith(("/RAW/", "/TMP/")) or ao.type() != "BinnedEstimate1D" and "Estimate1D" not in ao.type():
            continue
        values, errors = root[path.lstrip("/")].values(), root[path.lstrip("/")].errors()
        want_values = [v if v == v else 0.0 for v in ao.vals()]
        want_errors = [0.5 * (abs(b.quadSumNeg()) + abs(b.quadSumPos())) if b.numErrs() else 0.0 for b in ao.bins()]
        assert list(root[path.lstrip("/")].axis().edges()) == list(ao.xEdges())
        assert max(abs(a - b) for a, b in zip(values, want_values)) <= 1e-12 * max(1.0, max(map(abs, want_values)))
        assert max(abs(a - b) for a, b in zip(errors, want_errors)) <= 1e-12 * max(1.0, max(want_errors))
        compared += 1
    assert compared >= 17


def test_raw_and_tmp_are_skipped_unless_asked(scratch):
    out, raw = scratch / "a.root", scratch / "b.root"
    assert convert(REFERENCE, out).returncode == 0
    assert convert(REFERENCE, raw, "--keep-raw").returncode == 0
    assert not any(k.startswith("RAW") for k in uproot.open(out).keys())
    assert any(k.startswith("RAW/photo_eic") for k in uproot.open(raw).keys())


def test_a_variant_path_round_trips_through_the_paths_tree(scratch):
    source = scratch / "variant.yoda"
    source.write_text(REFERENCE.read_text(encoding="utf-8").replace("/photo_eic/d01-x01-y01", "/photo_eic:R=0.4/d01-x01-y01"),
                      encoding="utf-8")
    out = scratch / "variant.root"
    assert convert(source, out).returncode == 0
    root = uproot.open(out)
    assert "photo_eic__R-0.4/d01-x01-y01" in [k.split(";")[0] for k in root.keys()]
    table = root["paths"].arrays(library="np")
    mapping = dict(zip(table["root_path"], table["yoda_path"]))
    assert mapping["photo_eic__R-0.4/d01-x01-y01"] == "/photo_eic:R=0.4/d01-x01-y01"


def test_usage_and_input_errors(scratch):
    assert subprocess.run([str(APP)], capture_output=True).returncode == 2
    assert convert(scratch / "missing.yoda", scratch / "x.root").returncode == 4
