"""`hep doctor` and `hep pdf` (P1-S07).

The probes are monkeypatched wherever a real toolchain would make the test depend on this machine; two
tests deliberately run against the real installation, because the step's verification rows are about
this machine (Herwig run-only, the four PDF sets the EIC config needs).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hekit.env import doctor, lhapdf
from hekit.prov import versions

REPO = Path(__file__).resolve().parents[3]
CONFIGS = REPO / "configs" / "PhotoProduction"


def run_hep(*arguments: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "hekit.cli", *arguments],
                          capture_output=True, text=True, cwd=cwd, timeout=180, input="")


# ── the probes ───────────────────────────────────────────────────────────────

def test_a_missing_tool_is_not_an_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    tools = versions.toolchain()
    assert all(not tool.present for name, tool in tools.items()
               if name not in {"MadGraph", "Delphes", "ONNX Runtime"})


def test_versions_are_read_from_the_tools(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(versions, "_run", lambda command, timeout=15.0: {
        "rivet": "rivet v4.1.3", "pythia8-config": "8.317", "Herwig": "Herwig 7.3.0\nThePEG 2.3.0",
        "Sherpa": "Sherpa version 3.0.5 (Erebus)"}.get(command[0], "1.2.3"))
    tools = versions.toolchain()
    assert tools["Rivet"].version == "4.1.3"
    assert tools["Pythia"].version == "8.317"
    assert tools["Herwig"].version == "7.3.0" and tools["Herwig"].detail == "ThePEG 2.3.0"
    assert tools["Sherpa"].version == "3.0.5 (Erebus)"      # the codename is kept


def test_herwig_without_the_thepeg_modules_is_run_only(monkeypatch):
    monkeypatch.setattr(doctor, "thepeg_modules", lambda: ["ACDCSampler", "BreitWignerMass"])
    tools = {name: versions.Tool(name, version="1.0", path="/x") for name in
             ("Pythia", "Sherpa", "Whizard", "MadGraph", "Herwig")}
    found = doctor.generators(tools)
    assert found["herwig"]["status"] == "run-only"
    assert "HepMC or Rivet" in found["herwig"]["detail"]
    assert "--with-hepmc" in found["herwig"]["fix"]


def test_herwig_with_the_modules_is_fine(monkeypatch):
    monkeypatch.setattr(doctor, "thepeg_modules", lambda: ["HepMCAnalysis", "RivetAnalysis"])
    tools = {name: versions.Tool(name, version="1.0", path="/x") for name in
             ("Pythia", "Sherpa", "Whizard", "MadGraph", "Herwig")}
    assert doctor.generators(tools)["herwig"]["status"] == "ok"
    assert doctor.generators(tools)["herwig"]["features"] == ["hepmc3", "rivet"]


def test_a_generator_that_is_not_installed_says_so():
    tools = {name: versions.Tool(name) for name in
             ("Pythia", "Sherpa", "Whizard", "MadGraph", "Herwig")}
    found = doctor.generators(tools)
    assert {item["status"] for item in found.values()} == {"not installed"}


def test_hepmc_compression_is_detected_from_the_headers(monkeypatch, tmp_path):
    include = tmp_path / "hepmc3" / "include" / "HepMC3"
    include.mkdir(parents=True)
    monkeypatch.setattr(versions, "install_root", lambda: tmp_path)
    assert doctor.hepmc_compression()["formats"] == []
    (include / "WriterGZ.h").touch()
    (include / "ReaderGZ.h").touch()
    assert doctor.hepmc_compression()["formats"] == ["gz"]


def test_hep_run_reports_how_to_build_it_when_absent(monkeypatch):
    monkeypatch.setattr(doctor, "hep_run_path", lambda: "")
    found = doctor.hep_run()
    assert found["status"] == "not built" and "cmake --build" in found["detail"]


def test_hep_run_is_found_in_the_build_directory(monkeypatch, tmp_path):
    """A built but not installed hep-run still counts: the build directory is searched too."""
    binary = tmp_path / "build" / "bin" / "hep-run"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("hekit.env.paths.repo_root", lambda: tmp_path)
    assert doctor.hep_run_path() == str(binary)


def test_hep_run_capabilities_are_reported(monkeypatch):
    """The real binary, when this checkout has been built."""
    if not doctor.hep_run_path():
        pytest.skip("hep-run is not built here")
    found = doctor.hep_run()
    assert found["status"] == "ok"
    assert found["spec_schema"] == 2
    assert set(found["components"]) <= {"rivet", "hepmc", "onnx", "delphes"}


def test_missing_python_modules_come_with_a_fix(monkeypatch):
    monkeypatch.setattr(doctor.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout='{"rich": false}',
                                                                    stderr=""))
    found = doctor.python_modules()
    assert found["rich"]["status"] == "missing" and "pip install rich" in found["rich"]["fix"]
    # a module the probe did not report on is "unknown", not "missing": the two mean different things
    assert found["yoda"]["status"] == "unknown"


def test_a_failed_probe_leaves_everything_unknown(monkeypatch):
    monkeypatch.setattr(doctor.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout="", stderr="boom"))
    assert {item["status"] for item in doctor.python_modules().values()} == {"unknown"}


def test_environment_checks_find_the_classic_mistakes(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/a::/b")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/lib:/lib")
    monkeypatch.setenv("HEKIT_ROOT", "/nowhere")
    monkeypatch.delenv("HEP_ENV_LOADED", raising=False)
    found = {entry["name"]: entry for entry in doctor.environment()}
    assert "empty entry" in found["PYTHONPATH"]["detail"]
    assert "repeats" in found["LD_LIBRARY_PATH"]["detail"]
    assert "does not look like the repository" in found["HEKIT_ROOT"]["detail"]
    assert "not loaded" in found["environment"]["detail"]


def test_a_clean_environment_passes(monkeypatch):
    for name in doctor.PATH_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HEP_ENV_LOADED", "1")
    monkeypatch.delenv("HEKIT_ROOT", raising=False)
    assert [entry["status"] for entry in doctor.environment()] == ["ok"]


# ── the cache ────────────────────────────────────────────────────────────────

def test_the_report_is_cached(monkeypatch, tmp_path):
    calls = []

    def fake_probe():
        calls.append(1)
        return doctor.Report(when=time.time(), install="/install", toolchain={}, python={},
                             generators={}, hep_run={}, data={}, env=[])

    monkeypatch.setattr(doctor, "probe", fake_probe)
    monkeypatch.setattr(versions, "install_root", lambda: Path("/install"))
    cache = tmp_path / "doctor.json"
    doctor.report(cache=cache)
    doctor.report(cache=cache)
    assert len(calls) == 1 and cache.is_file()
    doctor.report(cache=cache, refresh=True)
    assert len(calls) == 2


def test_a_moved_install_invalidates_the_cache(monkeypatch, tmp_path):
    cache = tmp_path / "doctor.json"
    cache.write_text(json.dumps({"when": time.time(), "install": "/old", "toolchain": {}, "python": {},
                                 "generators": {}, "hep_run": {}, "data": {}, "env": []}),
                     encoding="utf-8")
    monkeypatch.setattr(versions, "install_root", lambda: Path("/new"))
    calls = []
    monkeypatch.setattr(doctor, "probe", lambda: calls.append(1) or doctor.Report(install="/new"))
    doctor.report(cache=cache)
    assert calls, "a different $HEP_INSTALL must re-probe"


def test_a_stale_cache_is_refreshed(monkeypatch, tmp_path):
    cache = tmp_path / "doctor.json"
    cache.write_text(json.dumps({"when": time.time() - doctor.CACHE_SECONDS - 1, "install": "/i",
                                 "toolchain": {}, "python": {}, "generators": {}, "hep_run": {},
                                 "data": {}, "env": []}), encoding="utf-8")
    monkeypatch.setattr(versions, "install_root", lambda: Path("/i"))
    calls = []
    monkeypatch.setattr(doctor, "probe", lambda: calls.append(1) or doctor.Report(install="/i"))
    doctor.report(cache=cache)
    assert calls


def test_an_unwritable_cache_does_not_break_the_command(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "probe", lambda: doctor.Report(install="/i"))
    found = doctor.report(cache=tmp_path / "nowhere" / "x" / "doctor.json")
    assert found.install == "/i"


# ── PDF sets ─────────────────────────────────────────────────────────────────

def test_set_names_are_read_from_pythia_values():
    assert lhapdf.set_name("LHAPDF6:NNPDF23_lo_as_0130_qed") == "NNPDF23_lo_as_0130_qed"
    assert lhapdf.set_name("LHAPDF6:CT18NLO/0") == "CT18NLO"
    assert lhapdf.set_name(13) == ""                       # a Pythia internal set


def test_installed_sets_are_read_from_the_data_path(monkeypatch, tmp_path):
    for name in ("CT18NLO", "MSTW2008lo68cl"):
        (tmp_path / name).mkdir()
        (tmp_path / name / f"{name}.info").touch()
    (tmp_path / "not_a_set").mkdir()
    monkeypatch.setenv("LHAPDF_DATA_PATH", str(tmp_path))
    assert lhapdf.installed_sets() == ["CT18NLO", "MSTW2008lo68cl"]


def test_a_plan_declares_which_sets_it_needs(monkeypatch, tmp_path):
    from hekit import sweep
    from hekit.config import load_config
    from hekit.plan import build as builder

    config = load_config(CONFIGS / "eic.toml", machine_file=None, project="PhotoProduction")
    plan = builder.build(config, sweep.select(config, study="pdf"))
    needed = lhapdf.sets_in_plan(plan)
    assert set(needed) == {"MSTW2008lo68cl", "NNPDF23_lo_as_0130_qed", "NNPDF23_nlo_as_0119_qed",
                           "PDF4LHC21_40"}
    monkeypatch.setattr(lhapdf, "installed_sets", lambda: ["MSTW2008lo68cl"])
    checked = lhapdf.check(plan)
    assert checked["MSTW2008lo68cl"] is True and checked["PDF4LHC21_40"] is False


def test_install_needs_the_tool(monkeypatch):
    from hekit.errors import HepError

    monkeypatch.setattr("shutil.which", lambda name: None)
    with pytest.raises(HepError, match="lhapdf is not on PATH"):
        lhapdf.install(["CT18NLO"])


# ── the commands, against this machine ───────────────────────────────────────

def test_doctor_json_reports_herwig_as_run_only(tmp_path):
    """Verification row: ThePEG here has no HepMC or Rivet module (00 finding 5)."""
    done = run_hep("doctor", "--json", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    found = json.loads(done.stdout)
    assert found["generators"]["herwig"]["status"] == "run-only"
    assert found["generators"]["pythia"]["status"] == "ok"
    assert found["data"]["hepmc_compression"]["formats"] == ["gz"]


def test_pdf_check_finds_the_four_sets_the_eic_config_needs(tmp_path):
    done = run_hep("pdf", "check", str(CONFIGS / "eic.toml"), "--study", "pdf", "--json", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    found = json.loads(done.stdout)
    assert len(found) == 4 and all(found.values()), found


def test_doctor_brief_is_short_and_fast(tmp_path):
    start = time.monotonic()
    done = run_hep("doctor", "--brief", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert len(done.stdout.splitlines()) <= 10
    assert time.monotonic() - start < 5.0          # cached; the cold probe is a second or two
    assert "toolchain" in done.stdout and "generators" in done.stdout


def test_doctor_full_names_every_area(tmp_path):
    done = run_hep("doctor", cwd=tmp_path)
    for area in ("toolchain", "python", "generators", "hep-run", "data", "env"):
        assert area in done.stdout


def test_pdf_list(tmp_path):
    done = run_hep("pdf", "list", "NNPDF", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert all("NNPDF" in line for line in done.stdout.splitlines() if line)
