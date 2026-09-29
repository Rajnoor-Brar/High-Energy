"""`hep plot FILE…`: any YODA or ROOT files overlaid through Paint, with no run TOML; and the merged
sweep file (App_yd2rt --merge) read back as one curve per point."""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

import pytest

from runner import plot
from runner.errors import HepError

REPO = Path(__file__).resolve().parents[2]
LEGACY = REPO / "tests" / "reference" / "legacy_run"
YODAS = [LEGACY / "mini_27x920_ep_MSTW.yoda", LEGACY / "mini_27x920_ep_NNLO.yoda"]
BUILT = all((REPO / "build" / n).exists() for n in ("Paint.exe", "App_yd2rt.exe"))

pytestmark = pytest.mark.skipif(not BUILT, reason="make utils/Apps/Paint.exe utils/App_yd2rt.exe")


def configs(scratch_output: Path) -> list[dict]:
    return [tomllib.loads(p.read_text()) for p in sorted(scratch_output.glob("plots/*/photo_eic/*.toml"))]


def test_two_yoda_files_one_page_per_object(scratch, monkeypatch):
    monkeypatch.setenv("HEKIT_OUTPUT", str(scratch / "output"))
    said = []
    assert plot.files([str(p) for p in YODAS], scratch / "pages", labels=["MSTW", "NNLO"], formats=["png"],
                      say=said.append) == 0
    assert len(list((scratch / "pages" / "photo_eic").glob("*.png"))) == 17 and "2 curve(s)" in said[-1]
    first = configs(scratch / "output")[0]
    assert [c["label"] for c in first["curve"]] == ["MSTW", "NNLO"]
    assert first["curve"][0]["raw"].startswith("f0/RAW/photo_eic/")        # min_entries can void
    assert first["page"]["x_label"]                                          # labels from the .plot


def test_a_merged_sweep_is_one_curve_per_point(scratch, monkeypatch):
    monkeypatch.setenv("HEKIT_OUTPUT", str(scratch / "output"))
    points = scratch / "points.json"
    points.write_text(json.dumps({"points": [
        {"name": "a", "values": {"pdf": {"label": "MSTW 2008 LO", "swept": True}}},
        {"name": "b", "values": {"pdf": {"label": "NNPDF 2.3 LO", "swept": True}}}]}))
    sweep = scratch / "sweep.root"
    done = subprocess.run([str(REPO / "build" / "App_yd2rt.exe"), "--merge", str(sweep), f"a={YODAS[0]}", f"b={YODAS[1]}",
                           "--keep-raw", "--points", str(points)], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    pytest.importorskip("uproot")
    assert plot.files([str(sweep)], scratch / "pages", objects=["/photo_eic/d01*"], formats=["png"], say=lambda _: None) == 0
    [page] = configs(scratch / "output")
    assert [c["label"] for c in page["curve"]] == ["MSTW 2008 LO", "NNPDF 2.3 LO"]
    assert [c["object"] for c in page["curve"]] == ["a/photo_eic/d01-x01-y01", "b/photo_eic/d01-x01-y01"]
    assert (scratch / "pages" / "photo_eic" / "d01-x01-y01.png").stat().st_size > 1000


def test_mistakes_are_named(scratch):
    with pytest.raises(HepError, match="no such file"):
        plot.files([str(scratch / "none.yoda")], scratch / "pages")
    with pytest.raises(HepError, match="2 names for 1 files"):
        plot.files([str(YODAS[0])], scratch / "pages", labels=["x", "y"])


def test_hep_plot_picks_file_mode_by_the_names(scratch):
    env = {"HEKIT_OUTPUT": str(scratch / "output"), "HEKIT_RESULTS": str(scratch / "results")}
    import os
    done = subprocess.run(["python3", str(REPO / "utils" / "Env" / "run"), "plot", str(YODAS[0]), "--objects", "/photo_eic/d01*",
                           "--formats", "png"], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=dict(os.environ, **env))
    assert done.returncode == 0, done.stderr
    assert (scratch / "results" / "plots" / "mini_27x920_ep_MSTW" / "photo_eic" / "d01-x01-y01.png").exists()
