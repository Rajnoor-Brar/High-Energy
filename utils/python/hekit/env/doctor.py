"""`hep doctor`: what is installed, what works, and what to do about what does not (08 §4).

Every check answers a question someone has actually had to debug: why `import ROOT` fails, why Herwig
events never reach Rivet, whether HepMC3 can write compressed events, whether an empty entry in a path
variable is silently adding the current directory. Each failed check carries the fix.

Results are cached for a day in `~/.cache/hekit/doctor.json`, keyed by `$HEP_INSTALL`, because probing
Herwig and Sherpa costs seconds.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any

from ..prov import versions

CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "hekit" / "doctor.json"
CACHE_SECONDS = 24 * 3600

#: Python modules the toolkit uses, and what to do when one is missing.
PYTHON_MODULES = {
    "yoda": ("required", "part of the YODA install; check PYTHONPATH"),
    "rivet": ("required", "part of the Rivet install; check PYTHONPATH"),
    "lhapdf": ("required", "part of the LHAPDF install; check PYTHONPATH"),
    "ROOT": ("optional", "add $HEP_INSTALL/root/lib to PYTHONPATH (hep proc and Delphes reading)"),
    "pythia8": ("optional", "add $HEP_INSTALL/pythia8/lib to PYTHONPATH"),
    "pyHepMC3": ("optional", "part of the HepMC3 install; only needed for Python event inspection"),
    "rich": ("required", "pip install rich — without it the live dashboard is disabled"),
    "tomli_w": ("required", "pip install tomli_w — needed to write resolved specs"),
    "click": ("required", "pip install click"),
    "numpy": ("optional", "pip install numpy"),
    "matplotlib": ("optional", "pip install matplotlib (the mpl plotting backend)"),
    "mplhep": ("optional", "pip install mplhep (house plot style)"),
    "uproot": ("optional", "pip install uproot (reading Delphes output without ROOT)"),
    "scipy": ("optional", "pip install scipy (fit fallback for hep proc)"),
    "onnxruntime": ("optional", "pip install onnxruntime (ML inference)"),
}

#: Path variables an empty entry in which silently means "the current directory".
PATH_VARIABLES = ("PATH", "LD_LIBRARY_PATH", "PYTHONPATH", "RIVET_ANALYSIS_PATH", "LHAPDF_DATA_PATH")


@dataclass
class Check:
    """One line of the report."""

    name: str
    status: str                  # ok | warn | missing | unknown
    detail: str = ""
    fix: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"status": self.status, "detail": self.detail, "fix": self.fix}


@dataclass
class Report:
    toolchain: dict[str, Any] = dataclass_field(default_factory=dict)
    python: dict[str, Any] = dataclass_field(default_factory=dict)
    generators: dict[str, Any] = dataclass_field(default_factory=dict)
    hep_run: dict[str, Any] = dataclass_field(default_factory=dict)
    data: dict[str, Any] = dataclass_field(default_factory=dict)
    env: list[dict[str, str]] = dataclass_field(default_factory=list)
    when: float = 0.0
    install: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"when": self.when, "install": self.install, "toolchain": self.toolchain,
                "python": self.python, "generators": self.generators, "hep_run": self.hep_run,
                "data": self.data, "env": self.env}

    @property
    def problems(self) -> list[str]:
        found = [f"{name}: {item['detail']}" for name, item in self.python.items()
                 if item["status"] == "missing" and item["need"] == "required"]
        found += [f"{name}: {item['status']}" for name, item in self.generators.items()
                  if item["status"] not in {"ok", "not installed"}]
        found += [entry["detail"] for entry in self.env if entry["status"] != "ok"]
        return found


def python_modules() -> dict[str, Any]:
    """Which Python modules import, without importing them into this process."""
    names = list(PYTHON_MODULES)
    code = ("import importlib.util, json;"
            f"print(json.dumps({{name: importlib.util.find_spec(name) is not None for name in {names!r}}}))")
    try:
        done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        found = json.loads(done.stdout) if done.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        found = {}
    report: dict[str, Any] = {}
    for name, (need, fix) in PYTHON_MODULES.items():
        present = found.get(name)
        report[name] = {"status": "ok" if present else ("unknown" if present is None else "missing"),
                        "need": need, "detail": "" if present else fix, "fix": fix}
    return report


def hepmc_compression() -> dict[str, Any]:
    """Whether this HepMC3 can read and write compressed events (11 §1, D-Q9)."""
    include = versions.install_root() / "hepmc3" / "include" / "HepMC3"
    headers = {"gz": (include / "WriterGZ.h").is_file() and (include / "ReaderGZ.h").is_file(),
               "compressed_io": (include / "CompressedIO.h").is_file()}
    formats = [name for name in ("gz",) if headers.get(name)]
    return {"status": "ok" if formats else "missing", "formats": formats,
            "detail": "compile with -DHEPMC3_USE_COMPRESSION -DHEPMC3_Z_SUPPORT and link -lz"
                      if formats else "no compression headers found"}


def thepeg_modules() -> list[str]:
    """ThePEG plugin modules that decide whether Herwig can reach HepMC or Rivet."""
    directory = versions.install_root() / "herwig7" / "lib" / "ThePEG"
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.so"))


def generators(tools: dict[str, versions.Tool]) -> dict[str, Any]:
    """What each generator can do here (04 §2)."""
    found: dict[str, Any] = {}
    found["pythia"] = _generator_state(tools["Pythia"], ["hepmc3", "rivet", "in-process"])
    found["sherpa"] = _generator_state(tools["Sherpa"], ["hepmc3", "rivet"])
    found["whizard"] = _generator_state(tools["Whizard"], ["hepmc3"])
    found["madgraph"] = _generator_state(tools["MadGraph"], ["lhe → pythia shower"])

    herwig = tools["Herwig"]
    modules = thepeg_modules()
    has_hepmc = any("HepMC" in module for module in modules)
    has_rivet = any("Rivet" in module for module in modules)
    if not herwig.present:
        found["herwig"] = {"status": "not installed", "features": [], "detail": ""}
    elif has_hepmc and has_rivet:
        found["herwig"] = {"status": "ok", "features": ["hepmc3", "rivet"], "detail": herwig.detail}
    else:
        absent = [name for name, present in (("HepMC", has_hepmc), ("Rivet", has_rivet)) if not present]
        missing = " or ".join(absent)
        found["herwig"] = {
            "status": "run-only",
            "features": [],
            "detail": f"ThePEG has no {missing} module{'s' if len(absent) > 1 else ''}, so Herwig "
                      "events cannot reach a file or Rivet",
            "fix": "rebuild ThePEG --with-hepmc --with-rivet, then Herwig (P7-S06)",
        }
    return found


def _generator_state(tool: versions.Tool, features: list[str]) -> dict[str, Any]:
    if not tool.present:
        return {"status": "not installed", "features": [], "detail": ""}
    return {"status": "ok", "features": features, "detail": tool.version}


def hep_run_path() -> str:
    """Where `hep-run` is: on PATH, or in the repository's build directory."""
    from shutil import which

    found = which("hep-run")
    if found:
        return found
    try:
        from .paths import repo_root

        for candidate in (repo_root() / "build" / "bin" / "hep-run",
                          repo_root() / "output" / "scratch" / "build" / "bin" / "hep-run"):
            if candidate.is_file():
                return str(candidate)
    except Exception:                   # noqa: BLE001 - a missing repository is not an error here
        pass
    return ""


def hep_run() -> dict[str, Any]:
    """`hep-run --capabilities`, once it is built (P2-S01 builds a stub, P2-S04 the real loop)."""
    executable = hep_run_path()
    if not executable:
        return {"status": "not built", "components": [],
                "detail": "build it with: cmake -S . -B build && cmake --build build"}
    try:
        done = subprocess.run([executable, "--capabilities"], capture_output=True, text=True, timeout=30)
        payload = json.loads(done.stdout) if done.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        payload = {}
    return {"status": "ok" if payload else "unknown", "path": executable,
            "components": payload.get("components", []),
            "compression": payload.get("compression", ""),
            "spec_schema": payload.get("spec_schema"),
            "detail": f"built {payload.get('built', '?')} ({payload.get('build', '?')})"
                      if payload else "did not report its capabilities"}


def data() -> dict[str, Any]:
    from . import lhapdf

    sets = lhapdf.installed_sets()
    return {"lhapdf_data_path": os.environ.get("LHAPDF_DATA_PATH", ""),
            "sets": len(sets), "status": "ok" if sets else "warn",
            "detail": "" if sets else "no PDF sets found; check LHAPDF_DATA_PATH"}


def environment() -> list[dict[str, str]]:
    """Sanity of the shell environment (00 §4.6)."""
    checks: list[Check] = []
    for name in PATH_VARIABLES:
        value = os.environ.get(name)
        if value is None:
            continue
        if "::" in f":{value}:".replace(":::", "::"):
            checks.append(Check(name, "warn", f"{name} has an empty entry, which means the current "
                                              "directory", "remove it (env/hep_env.sh does)"))
        duplicates = [entry for entry in value.split(os.pathsep)
                      if entry and value.split(os.pathsep).count(entry) > 1]
        if duplicates:
            checks.append(Check(name, "warn", f"{name} repeats {sorted(set(duplicates))[0]}",
                                "source the environment once, or use hep_refresh"))
    root = os.environ.get("HEKIT_ROOT")
    if root and not (Path(root) / "docs" / "rework").is_dir():
        checks.append(Check("HEKIT_ROOT", "warn", f"HEKIT_ROOT={root} does not look like the repository",
                            "unset it, or point it at the checkout"))
    if not os.environ.get("HEP_ENV_LOADED"):
        checks.append(Check("environment", "warn", "the HEP environment is not loaded",
                            "run load_hep (source ~/HEP/setup.sh)"))
    if not checks:
        checks.append(Check("environment", "ok", "paths are clean"))
    return [{"name": check.name, "status": check.status, "detail": check.detail, "fix": check.fix}
            for check in checks]


def probe() -> Report:
    """Run every check (a second or two; use `report()` for the cached version)."""
    tools = versions.toolchain()
    return Report(
        toolchain={name: {"version": tool.version, "path": tool.path, "detail": tool.detail}
                   for name, tool in tools.items()},
        python=python_modules(),
        generators=generators(tools),
        hep_run=hep_run(),
        data={**data(), "hepmc_compression": hepmc_compression()},
        env=environment(),
        when=time.time(),
        install=str(versions.install_root()),
    )


def environment_key() -> str:
    """What the probe's answers actually depend on.

    The install root is not enough. Every check here resolves through `PATH` and `PYTHONPATH`, so a
    probe run in a stripped shell — a container, a `env -u` invocation, a test — finds almost
    nothing, and keying only on the install root means that answer is then handed back to a *normal*
    shell for the next day. Found in P10-S03, by running the N6 degradation check and watching it
    poison the cache for everything afterwards.
    """
    import hashlib

    parts = [str(versions.install_root()), os.environ.get("PATH", ""),
             os.environ.get("PYTHONPATH", "")]
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:16]


def report(*, refresh: bool = False, cache: Path = CACHE) -> Report:
    """The cached report, re-probing when it is older than a day or the environment changed."""
    if not refresh and cache.is_file():
        try:
            stored = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stored = {}
        fresh = time.time() - stored.get("when", 0) < CACHE_SECONDS
        if fresh and stored.get("install") == str(versions.install_root()) \
                and stored.get("env_key") == environment_key():
            return Report(**{key: stored[key] for key in
                             ("toolchain", "python", "generators", "hep_run", "data", "env", "when",
                              "install") if key in stored})
    found = probe()
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        payload = found.as_dict()
        payload["env_key"] = environment_key()
        cache.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    except OSError:                     # a read-only home must not break the command
        pass
    return found


# ── rendering ────────────────────────────────────────────────────────────────

MARK = {"ok": "ok", "warn": "warn", "missing": "missing", "run-only": "run-only",
        "not installed": "—", "not built": "—", "unknown": "?"}


def brief(found: Report) -> str:
    """One line per area — what `hep_status` shows."""
    tools = [f"{name} {item['version']}" for name, item in found.toolchain.items() if item["version"]]
    missing = [name for name, item in found.python.items()
               if item["status"] == "missing" and item["need"] == "required"]
    lines = [f"toolchain  {len(tools)} components: " + " · ".join(tools[:6]),
             f"           {' · '.join(tools[6:])}" if len(tools) > 6 else "",
             f"python     {'all required modules present' if not missing else 'missing ' + ', '.join(missing)}",
             f"generators " + " · ".join(f"{name} {MARK.get(item['status'], item['status'])}"
                                         for name, item in found.generators.items()),
             f"hep-run    {found.hep_run['status']}",
             f"data       {found.data['sets']} PDF sets · HepMC compression: "
             f"{', '.join(found.data['hepmc_compression']['formats']) or 'none'}"]
    problems = found.problems
    if problems:
        lines.append("issues     " + "; ".join(problems[:3]))
    return "\n".join(line for line in lines if line)


def full(found: Report) -> str:
    """The whole report, with a fix on every line that needs one."""
    lines = [f"toolchain   (install: {found.install})"]
    for name, item in found.toolchain.items():
        detail = f"  {item['detail']}" if item["detail"] else ""
        lines.append(f"  {name:<14}{item['version'] or '—'}{detail}")
    lines.append("python")
    for name, item in found.python.items():
        note = "" if item["status"] == "ok" else f"  ({item['detail']})"
        lines.append(f"  {name:<14}{MARK.get(item['status'], item['status'])}{note}"
                     f"{'' if item['need'] == 'required' else '   [optional]'}")
    lines.append("generators")
    for name, item in found.generators.items():
        features = f"  ({', '.join(item['features'])})" if item["features"] else ""
        lines.append(f"  {name:<14}{MARK.get(item['status'], item['status'])}{features}")
        if item.get("detail") and item["status"] != "ok":
            lines.append(f"  {'':<14}{item['detail']}")
        if item.get("fix"):
            lines.append(f"  {'':<14}fix: {item['fix']}")
    lines.append(f"hep-run       {found.hep_run['status']}  {found.hep_run.get('detail', '')}")
    compression = found.data["hepmc_compression"]
    lines.append(f"data          {found.data['sets']} PDF sets in "
                 f"{found.data['lhapdf_data_path'] or 'LHAPDF_DATA_PATH (unset)'}")
    lines.append(f"              HepMC compression: {', '.join(compression['formats']) or 'none'}"
                 f"  ({compression['detail']})")
    lines.append("env")
    for entry in found.env:
        lines.append(f"  {entry['name']:<14}{MARK.get(entry['status'], entry['status'])}  {entry['detail']}")
        if entry["fix"]:
            lines.append(f"  {'':<14}fix: {entry['fix']}")
    return "\n".join(lines)
