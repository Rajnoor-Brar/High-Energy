"""P4 S3's gates, kept runnable (slow: real generators).

* MadGraph (row 1): the process directory built once, a launch per point, the LHE showered by
  Pythia, and Rivet's count checked against the shower; Rivet's σ is MadGraph's.
* Whizard (row 2): a direct-photoproduction point runs; its σ is its integration's.
* The generator comparison (row 3): three points, one page per spectrum with three curves.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from support import REPO, folder, hep_ok
yoda = pytest.importorskip("yoda")

pytestmark = pytest.mark.slow


def hep_run(scratch: Path, *args: str) -> str:
    return hep_ok(scratch, *args, timeout=3600)


@pytest.mark.skipif(not shutil.which("mg5_aMC"), reason="load_hep: mg5_aMC")
def test_madgraph_to_pythia_to_rivet(scratch):
    out = hep_run(scratch, "PhotoProduction/madgraph", "--set", "run.event_count=300")
    assert "count ok: 300 events" in (scratch / "output" / folder("PhotoProduction/madgraph") / "point/provenance.json").read_text(encoding="utf-8", errors="replace")
    log = (scratch / "output" / folder("PhotoProduction/madgraph") / "point/logs/madgraph.log").read_text(encoding="utf-8", errors="replace")
    stated = float(re.findall(r"Cross-section :\s+([\d.eE+-]+)", log)[-1])
    rivet = yoda.read(str(scratch / "results" / folder("PhotoProduction/madgraph") / "point/photo.yoda"))["/RAW/_XSEC"].val()
    assert rivet == pytest.approx(stated, rel=1e-3)
    again = hep_run(scratch, "PhotoProduction/madgraph", "--set", "run.event_count=300", "--rerun")
    assert "madgraph:prepare: cached" in again and "madgraph:prepare" in out


@pytest.mark.skipif(not shutil.which("whizard"), reason="load_hep: whizard")
def test_whizard_direct_photoproduction_runs(scratch):
    hep_run(scratch, "PhotoProduction/whizard", "--set", "run.event_count=500")
    point = scratch / "output" / folder("PhotoProduction/whizard") / "point"
    assert "count ok: 500 events" in (point / "provenance.json").read_text(encoding="utf-8", errors="replace")
    integration = (scratch / "output" / folder("PhotoProduction/whizard") / "point/logs/whizard.prepare.log").read_text(encoding="utf-8", errors="replace")
    blocks = integration.split("Starting integration for process")[1:]
    summary = r"^\s+\d+\s+\d+\s+([\d.]+E[+-]\d+)\s+[\d.]+E[+-]\d+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+[\d.]+\s+\d+\s*$"
    totals = [re.findall(summary, block, re.M)[-1] for block in blocks]  # each process's final summary row
    assert len(totals) == 2 and all(float(t) > 0 for t in totals)       # both subprocesses integrated, in fb


@pytest.mark.skipif(not (shutil.which("Herwig") and shutil.which("Sherpa")) or
                    not (REPO / "build/Herwig/HerwigDefaults.rpo").exists(), reason="load_hep and hep build")
def test_three_generators_one_page_per_spectrum(scratch):
    out = hep_run(scratch, "Comparison/generators", "--set", "run.event_count=500")
    assert "3 done, 0 failed" in out and "plot: 4 of 4 page(s) drawn" in out
    page = (scratch / "output/Comparison/generators/compare/plots/nch.toml").read_text(encoding="utf-8", errors="replace")
    assert page.count("[[curve]]") == 3
