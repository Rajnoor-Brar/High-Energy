"""The equivalence gate: in-process Rivet vs the legacy `generator.exe` → FIFO → `rivet` (P2-S06).

Rule 1 of the roadmap is that the rework may not change the physics. This is where that is checked
rather than asserted: the **legacy point cards** from the golden mini run (P0-S04) go through the new
binary at one thread with the same seed, and the resulting YODA is compared object by object and bin by
bin against the YODA the legacy pipeline produced.

The reference is `tests/golden/legacy_run/`, captured by `tests/golden/capture_legacy.py mini` from the
legacy tools before any of this existed. The two points cover both interesting cases:

  * `MSTW` — 5000 attempts, 5000 events written;
  * `NNLO` — 5000 attempts, 4999 written, because one `next()` failed. A pipeline that confused
    attempts with successes (00/B21) would disagree here and nowhere else.

Marked `slow` (about 15 s): `ctest -L slow -R equivalence`, or `pytest tests/integration`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tests" / "tools"))
import yodacmp                                               # noqa: E402

GOLDEN = REPO / "tests" / "golden" / "legacy_run"
INPUTS = REPO / "tests" / "golden" / "inputs" / "PhotoProduction"
RUN = REPO / "build" / "bin" / "hep-run"
PLUGIN_DIR = REPO / "build" / "analyses" / "PhotoProduction"

pytest.importorskip("yoda")
pytest.importorskip("tomli_w")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not RUN.is_file(), reason="build hep-run first (cmake --build build)"),
    pytest.mark.skipif(not (PLUGIN_DIR / "Rivet_photo_eic.so").is_file(),
                       reason="build the Rivet plugin first (target rivet_PhotoProduction)"),
    pytest.mark.skipif(not (GOLDEN / "run.json").is_file(),
                       reason="capture the golden legacy run first (tests/golden/capture_legacy.py mini)"),
]

#: point name → (the legacy card, the seed *in* that card, the legacy YODA)
POINTS = {
    "MSTW": ("mini_27x920_ep_MSTW.cmnd", 12345, "mini_27x920_ep_MSTW.yoda"),
    "NNLO": ("mini_27x920_ep_NNLO.cmnd", 12346, "mini_27x920_ep_NNLO.yoda"),
}
EVENTS = 5000


def legacy_facts() -> dict:
    return json.loads((GOLDEN / "run.json").read_text(encoding="utf-8"))


def run_the_legacy_card(point: str, directory: Path) -> tuple[Path, dict]:
    """Run the legacy point card through `hep-run`, one thread, its own seed. Returns the YODA path
    and the run summary."""
    import tomli_w

    card, seed, _ = POINTS[point]
    base = directory / "photo_ep.cmnd"
    base.write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    legacy_card = directory / "point.cmnd"
    legacy_card.write_bytes((GOLDEN / "cmnd" / card).read_bytes())

    # A minimal spec written by hand, because the point of the gate is the *legacy* card: nothing
    # `hep plan` does may come between the two pipelines.
    spec = {
        "meta": {"schema": 2, "point": f"mini_27x920_ep_{point}", "hash": "sha256:" + "0" * 64,
                 "origin": "tests/golden/legacy_mini.toml (P2-S06 equivalence gate)", "aliases": []},
        "run": {"events": EVENTS, "threads": 1, "seed": seed,
                "seeds": {"point": seed, "instances": [seed]}},
        "source": {"kind": "pythia", "cards": [str(base), str(legacy_card)]},
        "output": {"dir": str(directory), "yoda": "analysis.yoda", "summary": "run.summary.json"},
        "sink": [{"kind": "rivet", "analyses": ["photo_eic"], "paths": [str(PLUGIN_DIR)],
                  "xsec": "generator", "weights": "nominal", "dump_every": 0, "check_beams": True}],
        "status": {"fd": 3, "heartbeat_ms": 500},
    }
    spec_path = directory / "run.toml"
    spec_path.write_text(tomli_w.dumps(spec), encoding="utf-8")

    done = subprocess.run([str(RUN), str(spec_path), "--plain"], capture_output=True, text=True,
                          timeout=1800, cwd=os.fspath(REPO / "output" / "scratch"))
    assert done.returncode == 0, done.stderr[-4000:]
    summary = json.loads((directory / "run.summary.json").read_text(encoding="utf-8"))
    return directory / "analysis.yoda", summary


@pytest.fixture(scope="module")
def runs(tmp_path_factory) -> dict[str, tuple[Path, dict]]:
    base = tmp_path_factory.mktemp("equivalence")
    found = {}
    for point in POINTS:
        directory = base / point
        directory.mkdir()
        found[point] = run_the_legacy_card(point, directory)
    return found


# ── the gate ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("point", sorted(POINTS))
def test_every_bin_matches_the_legacy_pipeline(runs, point):
    """The same events through the same analysis: every number, including Rivet's `/RAW/` copies."""
    produced, _ = runs[point]
    reference = GOLDEN / POINTS[point][2]
    report = yodacmp.compare(reference, produced, rtol=1e-6, raw=True, chi2=True)
    assert report.identical, report.table()
    assert report.compared == 39, report.table()      # 17 histograms + xsec + evtcount, raw and final
    assert report.bins >= 1000, report.table()
    assert report.chi2_per_ndf == 0.0, "identical bins have no chi2 at all"


@pytest.mark.parametrize("point", sorted(POINTS))
def test_the_event_counts_match_including_the_failures(runs, point):
    """00/B21: the legacy run attempted 5000 and wrote 5000 (MSTW) or 4999 (NNLO). A pipeline that
    counted attempts as successes would produce a different number of events here."""
    _, summary = runs[point]
    index = sorted(POINTS).index(point)
    legacy = legacy_facts()["generator"][index]
    assert summary["run"]["attempted"] == legacy["generated"]
    assert summary["run"]["events"] == legacy["written"]


@pytest.mark.parametrize("point", sorted(POINTS))
def test_the_cross_section_matches_the_legacy_log(runs, point):
    """σ is the number the legacy run reported, to the precision it reported it (2 decimals)."""
    _, summary = runs[point]
    legacy = legacy_facts()["yoda"][POINTS[point][2]]
    assert summary["run"]["xsec_pb"] == pytest.approx(legacy["xsec_pb"], abs=0.005)


@pytest.mark.parametrize("point", sorted(POINTS))
def test_the_yoda_holds_the_same_event_count_as_the_legacy_one(runs, point):
    import yoda

    produced, summary = runs[point]
    legacy = legacy_facts()["yoda"][POINTS[point][2]]
    objects = yoda.read(str(produced))
    assert objects["/_EVTCOUNT"].val() == pytest.approx(legacy["numEntries"])
    assert objects["/_EVTCOUNT"].val() == pytest.approx(summary["run"]["events"])


def test_the_file_can_be_merged_by_rivet(runs, tmp_path):
    """07 §3 merges seed replicas with `rivet-merge -e`, which re-runs `finalize` from the `/RAW/`
    objects and refuses a file without them — which is exactly what this gate caught.

    `photo_eic` is still `Reentrant: false`, so the merge drops its objects and keeps only the run
    scalars; P4-S05 makes it re-entrant, and this test then tightens to the histograms."""
    import shutil

    import yoda

    produced, _ = runs["MSTW"]
    for name in ("a.yoda", "b.yoda"):
        shutil.copyfile(produced, tmp_path / name)
    environment = dict(os.environ, RIVET_ANALYSIS_PATH=str(PLUGIN_DIR))
    done = subprocess.run(["rivet-merge", "-e", "-o", "merged.yoda", "a.yoda", "b.yoda"],
                          capture_output=True, text=True, timeout=600, cwd=tmp_path,
                          env=environment)
    assert done.returncode == 0, done.stderr[-2000:]
    assert "Missing cross-section" not in done.stderr, "the /RAW/ objects have to be in the file"

    merged = yoda.read(str(tmp_path / "merged.yoda"))
    assert merged["/_EVTCOUNT"].val() == pytest.approx(2 * EVENTS), "two runs' events, added"
