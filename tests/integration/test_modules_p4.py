"""P4 S1's gates, kept runnable: module programs through the runner (slow: real generators).

* Lambda (rows 1–2): App_Pythia fans out to Lamriv (Rivet) and Lambda (the module) on the same
  events; the module's histograms equal Rivet's to the precision YODA writes (7 significant digits).
* InprocJets (rows 6–8): an integrated Pythia + Rivet program gets the chain's card and seeds, so at
  one thread its YODA equals the chain's bin for bin; at four its σ equals App_Pythia's sidecar;
  four Rivets on threads equal one (V34, L29); and the serial engine is reproducible.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
BUILT = [REPO / "build" / p for p in ("App_Pythia.exe", "Lambda/Lambda.exe", "PhotoProduction/InprocJets.exe")]
uproot = pytest.importorskip("uproot")
yoda = pytest.importorskip("yoda")

pytestmark = [pytest.mark.slow, pytest.mark.skipif(not all(p.exists() for p in BUILT), reason="hep build")]


def hep_run(scratch: Path, *args: str) -> tuple[Path, Path]:
    env = dict(os.environ, HEKIT_OUTPUT=str(scratch / "output"), HEKIT_RESULTS=str(scratch / "results"))
    done = subprocess.run(["python3", str(REPO / "utils" / "Env" / "run"), "run", *args, "--plain"],
                          env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    assert done.returncode == 0, done.stdout[-2000:] + done.stderr[-2000:]
    return scratch / "output", scratch / "results"


def test_lambda_module_and_rivet_agree_on_the_same_events(scratch):
    _, results = hep_run(scratch, "Lambda/lambda", "single", "--set", "run.event_count=200", "--set", "run.threads=2")
    point = results / "Lambda" / "lambda" / "single" / "point"
    report = json.loads((point / "lambda.root.json").read_text(encoding="utf-8", errors="replace"))
    assert report["events"] == json.loads((scratch / "output" / "Lambda" / "lambda" / "single" / "point" /
                                           "to_rivet.hepmc.json").read_text(encoding="utf-8", errors="replace"))["written"]   # named after its first output
    module, rivet = uproot.open(point / "lambda.root"), uproot.open(point / "lamriv.root")
    compared = 0
    for key in module.keys():
        if not key.startswith("Lambda/"):
            continue
        name = key.split("/")[1].split(";")[0]
        mine, theirs = module[key], rivet[f"Lamriv__RESERVED-2/{name}"]
        for a, b in ((mine.values(), theirs.values()), (mine.errors(), theirs.errors())):
            half = np.where(b != 0, 0.5 * 10.0 ** (np.floor(np.log10(np.abs(np.where(b != 0, b, 1)))) - 6), 0)
            assert np.all(np.abs(a - b) <= half * 1.0000001 + 1e-300), name     # YODA's rounding, nothing else
            assert np.array_equal(a == 0, b == 0), name
        compared += 1
    assert compared == 21


def test_inproc_equals_the_chain_at_one_thread(scratch):
    for configuration in ("single", "inproc"):
        hep_run(scratch, "PhotoProduction/eic", configuration, "--set", "run.event_count=2000", "--set", "run.threads=1")
    base = scratch / "results" / "PhotoProduction" / "03_eic"
    chain, inproc = base / "single" / "point", base / "11_inproc" / "point"
    technical = scratch / "output" / "PhotoProduction" / "03_eic"
    seeds = [json.loads((technical / c / "point" / "provenance.json").read_text(encoding="utf-8"))["seed"]
             for c in ("single", "11_inproc")]
    assert seeds[0] == seeds[1]
    a, b = yoda.read(str(chain / "photo.yoda")), yoda.read(str(inproc / "photo.yoda"))
    finals = [p for p in a if not p.startswith("/RAW") and "Estimate1D" in a[p].type()]
    assert len(finals) == 17
    for path in finals:
        assert np.array_equal(np.nan_to_num(a[path].vals(), nan=-1), np.nan_to_num(b[path].vals(), nan=-1)), path


def test_inproc_sigma_equals_the_sidecar_at_four_threads(scratch):
    for configuration in ("single", "inproc"):
        output, results = hep_run(scratch, "PhotoProduction/eic", configuration, "--set", "run.event_count=4000",
                                  "--set", "run.threads=4")
    point = output / "PhotoProduction" / "03_eic" / "single" / "point"
    sidecar = json.loads(min(point.glob("events*.hepmc.json")).read_text(encoding="utf-8", errors="replace"))  # sharded: .s1
    report = json.loads((results / "PhotoProduction" / "03_eic" / "11_inproc" / "point" / "photo.yoda.json").read_text(encoding="utf-8", errors="replace"))
    assert report["events"] == sidecar["written"]
    assert report["sigma_pb"] == pytest.approx(sidecar["sigma_pb"], rel=1e-6)


@pytest.mark.parametrize("config, product", [("PhotoProduction/InProcEIC", "photo.yoda"),
                                             ("PhotoProduction/InProcZeus", "zeus.yoda")])
def test_rivet_threads_equal_one_rivet(scratch, config, product):
    """V34, the gate: four Rivets on threads of their own, merged, equal one Rivet on the same events.
    Both analyses cluster with SISCone, which needs the patch for this (L29): without it the jets
    change or FastJet stops with an internal error."""
    results = []
    for k in (1, 4):
        _, res = hep_run(scratch / f"k{k}", config, "single", "--set", "run.event_count=4000", "--set", "run.threads=4",
                         "--set", f"tools.inproc.config.rivet_threads={k}")
        results.append(yoda.read(str(next(res.rglob(product)))))
    one, four = results
    assert one["/RAW/_EVTCOUNT"].numEntries() == four["/RAW/_EVTCOUNT"].numEntries()
    assert four["/_XSEC"].val() == pytest.approx(one["/_XSEC"].val(), rel=1e-12)
    compared = 0
    for path, histo in one.items():
        if path.startswith("/RAW/") and hasattr(histo, "sumW"):
            assert four[path].sumW() == pytest.approx(histo.sumW(), rel=1e-12), path
        elif histo.type() == "Estimate1D":
            assert np.array_equal(np.nan_to_num(histo.vals(), nan=-1), np.nan_to_num(four[path].vals(), nan=-1)), path
            compared += 1
    assert compared > 10


def test_the_serial_engine_is_reproducible(scratch):
    runs = []
    for attempt in range(2):
        _, results = hep_run(scratch, "PhotoProduction/eic", "inproc", "--rerun", "--set", "run.event_count=1000",
                             "--set", "run.threads=1", "--set", "tools.jets.config.engine=serial")
        runs.append((results / "PhotoProduction" / "03_eic" / "11_inproc" / "point" / "photo.yoda").read_bytes())
    assert runs[0] == runs[1]
