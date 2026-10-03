"""P1's physics gates, kept runnable (docs/07_Record.md §8, S1 rows 2–4).

* The reference gate: the legacy pipeline's cards → App_Pythia → FIFO → rivet reproduce the legacy
  reference YODAs byte for byte. It uses photo_eic as it was when the reference was captured
  (a2eac4e), because the analysis' ETMIN/ETMIN2 defaults changed since.
* The σ gate: at 4 threads the σ Rivet normalised to equals App_Pythia's combined σ (L1, L2),
  and Rivet's event count equals the sidecar's written count (L7).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "build" / "App_Pythia.exe"
REF = REPO / "tests" / "reference" / "legacy_run"

pytestmark = [pytest.mark.slow,
              pytest.mark.skipif(not APP.exists(), reason="build/App_Pythia.exe not built (make)")]


def chain(workdir: Path, cards: list[Path], plugin_dir: Path, name: str) -> tuple[Path, dict]:
    """App_Pythia → FIFO → rivet, by hand. Returns the YODA path and the sidecar."""
    fifo = workdir / f"{name}.hepmc"
    if fifo.exists():
        fifo.unlink()
    os.mkfifo(fifo)
    env = dict(os.environ, RIVET_ANALYSIS_PATH=str(plugin_dir))
    env.pop("HEP_STATUS_FD", None)
    yoda = workdir / f"{name}.yoda"
    rivet = subprocess.Popen(["rivet", "--analysis=photo_eic", "-o", str(yoda), str(fifo)], cwd=workdir, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pythia = subprocess.run([str(APP), str(fifo), *map(str, cards)], cwd=workdir, env=env,
                            capture_output=True, text=True, encoding="utf-8", timeout=1800)
    assert rivet.wait(timeout=1800) == 0
    assert pythia.returncode == 0, pythia.stderr
    fifo.unlink()
    return yoda, json.loads(Path(f"{fifo}.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def capture_plugin(tmp_path_factory) -> Path:
    where = tmp_path_factory.mktemp("capture_photo_eic")
    for ext in ("cc", "info", "plot"):
        text = subprocess.run(["git", "show", f"a2eac4e:sources/PhotoProduction/photo_eic.{ext}"], cwd=REPO,
                              capture_output=True, text=True, encoding="utf-8", check=True).stdout
        (where / f"photo_eic.{ext}").write_text(text, encoding="utf-8")
    subprocess.run(["rivet-build", "Rivet_photo_eic.so", "photo_eic.cc"], cwd=where, check=True,
                   capture_output=True)
    return where


@pytest.mark.parametrize("point", ["MSTW", "NNLO"])
def test_the_legacy_reference_is_reproduced_byte_for_byte(scratch, capture_plugin, point):
    yoda, side = chain(scratch, [REF / "photo_ep.cmnd", REF / "cmnd" / f"mini_27x920_ep_{point}.cmnd"],
                       capture_plugin, point)
    reference = REF / f"mini_27x920_ep_{point}.yoda"
    assert yoda.read_bytes() == reference.read_bytes()
    assert side["written"] == {"MSTW": 5000, "NNLO": 4999}[point]


def test_sigma_at_four_threads_is_the_combination(scratch):
    point = scratch / "point.cmnd"
    point.write_text("Main:numberOfEvents = 20000\nParallelism:numThreads = 4\n"
                     "Parallelism:seeds = {1001,1002,1003,1004}\nBeams:eA = 920\nBeams:eB = 27.5\n"
                     "Beams:idB = -11\n", encoding="utf-8")
    yoda, side = chain(scratch, [REPO / "tests" / "fixtures" / "configs" / "PhotoProduction" / "photo_ep.cmnd", point],
                       REPO / "build" / "Rivet", "t4")
    text = yoda.read_text(encoding="utf-8")
    xsec = float(re.search(r"/_XSEC\n.*?# value[^\n]*\n(\S+)", text, re.S).group(1))
    assert abs(xsec - side["sigma_pb"]) / side["sigma_pb"] < 1e-6
    entries = re.search(r"/RAW/_EVTCOUNT\n.*?# sumW[^\n]*\n\S+\s+\S+\s+(\S+)", text, re.S).group(1)
    assert round(float(entries)) == side["written"]
