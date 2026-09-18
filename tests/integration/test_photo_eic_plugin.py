"""`photo_eic`'s own defects and its re-entrancy (P4-S05).

The plugin is the one piece of physics code the toolkit carries, and three things about it were either
wrong or unverified (00/B25, 00/B26, and `Reentrant: false` blocking the merge path of 07 §3). The
fast tests here check what the `.info` declares; the slow one earns the declaration by merging two
replicas and comparing them with a single run of the same size.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "utils" / "python"))

PLUGIN_SOURCE = REPO / "analyses" / "PhotoProduction" / "photo_eic.cc"
PLUGIN_INFO = REPO / "analyses" / "PhotoProduction" / "photo_eic.info"
BUILT = REPO / "build" / "analyses" / "PhotoProduction"
RUN = REPO / "build" / "bin" / "hep-run"
BASE_CARD = REPO / "tests" / "golden" / "inputs" / "PhotoProduction" / "photo_ep.cmnd"

yoda = pytest.importorskip("yoda")


# ── what the source and the .info say (fast) ─────────────────────────────────

def test_the_siscone_plugin_is_owned_by_its_jet_definition():
    """00/B25: FastJet's JetDefinition does not take ownership unless told to, so the plugin was
    leaked once per run — and once per worker in a sharded run."""
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")
    assert "new fastjet::SISConePlugin" in source
    assert "siscone.delete_plugin_when_unused();" in source


def test_the_eta_acceptance_does_not_depend_on_the_orientation():
    """00/B26: the range was built as [-etamax*orientation, +etamax*orientation], which is inverted
    when the proton runs along -z. Rivet normalises such a range, so it never bit — but the
    acceptance is symmetric and is now written that way, so it cannot."""
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")
    assert "Cuts::abseta < _etamax" in source
    assert "etaIn(-_etamax*orientation" not in source
    # The orientation still decides which eta is *binned*, which is the part that is real.
    assert "const double eta = orientation*jet.eta();" in source


def test_the_info_declares_reentrancy_and_beams():
    """`Reentrant: true` is what lets `rivet-merge -e` re-run finalize (07 §3) and what lets a dump
    be finalized rather than raw (05 §5)."""
    info = PLUGIN_INFO.read_text(encoding="utf-8")
    assert "Reentrant: true" in info
    assert "Beams:" in info
    assert "[p+, e-]" in info and "[p+, e+]" in info, "both lepton charges are run"


@pytest.mark.skipif(not (BUILT / "photo_eic.info").is_file(), reason="the plugin is not built")
def test_the_built_plugin_carries_the_same_info():
    """The build tree is what Rivet loads; a stale copy there would be the one that counts."""
    assert (BUILT / "photo_eic.info").read_text(encoding="utf-8") == \
        PLUGIN_INFO.read_text(encoding="utf-8")


# ── the merge the re-entrancy is for (slow) ──────────────────────────────────

pytestmark_slow = pytest.mark.slow


def write_spec(directory: Path, *, events: int, seed: int, threads: int = 2,
               dump_every: int = 0) -> Path:
    import tomli_w

    directory.mkdir(parents=True, exist_ok=True)
    (directory / "photo_ep.cmnd").write_bytes(BASE_CARD.read_bytes())
    (directory / "point.cmnd").write_text(
        "Beams:frameType = 2\nBeams:eA = 920\nBeams:eB = 27.5\nBeams:idB = -11\n"
        "PDF:pSet = LHAPDF6:MSTW2008lo68cl\n", encoding="utf-8")
    spec = {
        "meta": {"schema": 2, "point": directory.name, "hash": "sha256:" + "0" * 64,
                 "origin": "P4-S05", "aliases": []},
        "run": {"events": events, "threads": threads, "seed": seed,
                "seeds": {"point": seed, "instances": [seed + index for index in range(threads)]}},
        "source": {"kind": "pythia",
                   "cards": [str(directory / "photo_ep.cmnd"), str(directory / "point.cmnd")]},
        "output": {"dir": str(directory), "yoda": "analysis.yoda", "summary": "run.summary.json"},
        "sink": [{"kind": "rivet", "analyses": ["photo_eic"], "paths": [str(BUILT)],
                  "xsec": "generator", "weights": "nominal", "dump_every": dump_every,
                  "check_beams": True}],
        "status": {"fd": 3, "heartbeat_ms": 500},
    }
    path = directory / "run.toml"
    path.write_text(tomli_w.dumps(spec), encoding="utf-8")
    return path


def generate(directory: Path, **rest) -> Path:
    done = subprocess.run([str(RUN), str(write_spec(directory, **rest)), "--plain"],
                          capture_output=True, text=True, timeout=3600,
                          cwd=REPO / "output" / "scratch")
    assert done.returncode == 0, done.stderr[-3000:]
    return directory / "analysis.yoda"


@pytest.mark.slow
@pytest.mark.skipif(not RUN.is_file() or not (BUILT / "Rivet_photo_eic.so").is_file(),
                    reason="build hep-run and the plugin first")
def test_merged_replicas_agree_with_one_longer_run(tmp_path):
    """07 §3's merge path, end to end: `rivet-merge -e` re-runs finalize from the `/RAW/` objects,
    which only works for a re-entrant analysis, and the result must be compatible with a single run
    of the same total size."""
    from hekit.results import stats

    if shutil.which("rivet-merge") is None:              # pragma: no cover
        pytest.skip("rivet-merge is not on PATH")

    first = generate(tmp_path / "a", events=3000, seed=111111)
    second = generate(tmp_path / "b", events=3000, seed=222222)
    whole = generate(tmp_path / "whole", events=6000, seed=111111)

    merged = tmp_path / "merged.yoda"
    done = subprocess.run(["rivet-merge", "-e", "-o", str(merged), str(first), str(second)],
                          capture_output=True, text=True, timeout=900, cwd=tmp_path,
                          env={**__import__("os").environ, "RIVET_ANALYSIS_PATH": str(BUILT)})
    assert done.returncode == 0, done.stderr[-2000:]
    assert "Rerunning finalize" in done.stdout + done.stderr, \
        "a non-re-entrant analysis would have been skipped instead"

    objects = yoda.read(str(merged))
    assert len([path for path in objects if path.startswith("/photo_eic/")]) == 17, \
        "the histograms survive the merge; without Reentrant they are dropped"
    assert objects["/_EVTCOUNT"].val() == pytest.approx(
        yoda.read(str(whole))["/_EVTCOUNT"].val(), rel=0.01)

    report = stats.compare_files(merged, whole, reference=False)
    assert report.total_ndf > 100, "there is something to compare"
    assert report.chi2_per_ndf < 2.0, \
        f"merged replicas and one run disagree: chi2/ndf = {report.chi2_per_ndf:.2f}"


@pytest.mark.slow
@pytest.mark.skipif(not RUN.is_file() or not (BUILT / "Rivet_photo_eic.so").is_file(),
                    reason="build hep-run and the plugin first")
def test_a_periodic_dump_is_finalized(tmp_path):
    """05 §5: Rivet skips finalize in a dump for a non-re-entrant analysis, so the file would be raw
    counts wearing the name of a result."""
    directory = tmp_path / "dumping"
    generate(directory, events=1000, seed=909090, dump_every=400)

    dump = directory / "analysis.dump.yoda"
    assert dump.is_file(), "dump_every is honoured now that the analysis is re-entrant"
    objects = yoda.read(str(dump))
    assert "/_XSEC" in objects
    histogram = objects["/photo_eic/d01-x01-y01"]
    assert histogram.hasAnnotation("ScaledBy"), "finalize ran: the objects are scaled"
    raw = objects["/RAW/photo_eic/d01-x01-y01"]
    assert histogram.bin(1).val() > raw.bin(1).sumW(), \
        "the finalized value is a cross section, not a weight sum"
