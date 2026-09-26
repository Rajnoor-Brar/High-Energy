"""P4 S2's gates, kept runnable: Delphes, Sherpa and Herwig through the runner (slow).

* Delphes (row 1): pythia → a file → delphes → a custom analysis; the Delphes tree holds the
  sidecar's written events.
* Sherpa (rows 3, 6): 18x275 LO, MPI off, σ consistent with v1's 9,636 ± 782 pb (L24); a rerun
  hits the integration cache.
* Herwig (rows 5–7): the count check passes, Rivet's σ (the last event's) is Herwig's own, the run
  file is read once and shared with a custom tool that asks for it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
yoda = pytest.importorskip("yoda")
uproot = pytest.importorskip("uproot")

pytestmark = pytest.mark.slow


def hep_run(scratch: Path, *args: str) -> str:
    env = dict(os.environ, HEKIT_OUTPUT=str(scratch / "output"), HEKIT_RESULTS=str(scratch / "results"))
    done = subprocess.run(["python3", str(REPO / "utils" / "Env" / "run"), "run", *args, "--plain"], env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return done.stdout


def xsec(path: Path) -> tuple[float, float]:
    ao = yoda.read(str(path))["/RAW/_XSEC"]
    return ao.val(), ao.errAvg()


@pytest.mark.skipif(not shutil.which("DelphesHepMC3"), reason="load_hep: DelphesHepMC3")
def test_delphes_file_chain_counts_every_event(scratch):
    hep_run(scratch, "PhotoProduction/eic", "delphes", "--set", "run.event_count=1000", "--set", "run.threads=2")
    point = "PhotoProduction/03_eic/12_delphes/point"
    written = json.loads((scratch / "output" / point / "showered.hepmc.json").read_text(encoding="utf-8", errors="replace"))["written"]
    assert uproot.open(scratch / "results" / point / "delphes.root")["Delphes"].num_entries == written
    assert json.loads((scratch / "results" / point / "jets_reco.json").read_text(encoding="utf-8", errors="replace"))["events"] == written


@pytest.mark.skipif(not shutil.which("Sherpa"), reason="load_hep: Sherpa")
def test_sherpa_sigma_matches_v1_and_the_integration_is_cached(scratch):
    first = hep_run(scratch, "PhotoProduction/sherpa")
    assert "sherpa:prepare: ok" in first
    value, error = xsec(scratch / "results" / "PhotoProduction/04_sherpa/single/point/photo.yoda")
    assert abs(value - 9636) < 3 * (error ** 2 + 782 ** 2) ** 0.5        # L24: v1's measurement
    again = hep_run(scratch, "PhotoProduction/sherpa", "--rerun")
    assert "sherpa:prepare: cached" in again


@pytest.mark.skipif(not shutil.which("Herwig") or not (REPO / "build/Herwig/HerwigDefaults.rpo").exists(),
                    reason="load_hep and hep build: Herwig and its repository")
def test_herwig_sigma_is_its_own_and_the_run_file_is_shared(scratch):
    hep_run(scratch, "PhotoProduction/herwig", "--set", "run.event_count=500")
    point = scratch / "output" / "PhotoProduction/05_herwig/single/point"
    report = next(point.glob("point-S*.out")).read_text(encoding="utf-8", errors="replace")
    stated = re.search(r"Total \(from generated events\):\s+(\d+)\s+\d+\s+([\d.]+)\((\d+)\)e([+-]\d+)", report)
    assert int(stated[1]) == 500
    nb = float(stated[2]) * 10 ** int(stated[4])
    value, _ = xsec(scratch / "results" / "PhotoProduction/05_herwig/single/point/photo.yoda")
    digits = len(stated[2].split(".")[1]) if "." in stated[2] else 0
    assert abs(value / 1000 - nb) <= 0.5 * 10 ** (int(stated[4]) - digits) * 1.0001   # to the digits Herwig prints
    out = hep_run(scratch, "PhotoProduction/herwig", "export")
    assert "herwig:prepare: cached" in out                               # the same card: one read
    probe = (scratch / "output" / "PhotoProduction/05_herwig/export/point/logs/probe.log").read_text(encoding="utf-8", errors="replace")
    assert "point.run" in probe
