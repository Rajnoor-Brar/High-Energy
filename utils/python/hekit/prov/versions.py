"""Which versions of the toolchain are in use (08 §4, 07 §2).

Probes are deliberately cheap and forgiving: a missing tool is "not installed", never an exception, so
`hep doctor` works on a half-built machine and provenance records what was actually there.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

VERSION = re.compile(r"\d+\.\d+(?:\.\d+)?")


@dataclass(frozen=True)
class Tool:
    """One component of the toolchain."""

    name: str
    version: str = ""
    path: str = ""
    detail: str = ""

    @property
    def present(self) -> bool:
        return bool(self.version or self.path)


def _run(command: list[str], timeout: float = 15.0) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() or done.stderr.strip() if done.returncode == 0 else ""


def _first_version(text: str) -> str:
    match = VERSION.search(text)
    return match.group(0) if match else text.splitlines()[0].strip() if text else ""


def _from_command(name: str, command: list[str], *, keep_text: bool = False) -> Tool:
    from shutil import which

    executable = which(command[0])
    if executable is None:
        return Tool(name)
    output = _run(command)
    version = output.strip() if keep_text else _first_version(output)
    return Tool(name, version=version, path=executable)


def _from_file(name: str, path: Path, detail: str = "") -> Tool:
    return Tool(name, version="installed" if path.exists() else "", path=str(path) if path.exists() else "",
                detail=detail)


def install_root() -> Path:
    return Path(os.environ.get("HEP_INSTALL", Path.home() / "HEP" / "install"))


def herwig() -> Tool:
    """Herwig and the ThePEG it was built against; `Herwig --version` reports both."""
    from shutil import which

    if which("Herwig") is None:
        return Tool("Herwig")
    output = _run(["Herwig", "--version"])
    numbers = VERSION.findall(output)
    version = numbers[0] if numbers else ""
    detail = f"ThePEG {numbers[1]}" if len(numbers) > 1 else ""
    return Tool("Herwig", version=version, path=which("Herwig"), detail=detail)


def _sherpa() -> Tool:
    """Sherpa keeps its codename — "3.0.5 (Erebus)" is how its releases are referred to."""
    tool = _from_command("Sherpa", ["Sherpa", "--version"], keep_text=True)
    if not tool.present:
        return tool
    match = re.search(r"\d+\.\d+(?:\.\d+)?.*", tool.version)
    return Tool("Sherpa", version=match.group(0).strip() if match else tool.version, path=tool.path)


def toolchain() -> dict[str, Tool]:
    """Every component, in the order `hep doctor` prints them."""
    root = install_root()
    tools = [
        _from_command("LHAPDF", ["lhapdf-config", "--version"]),
        _from_command("HepMC3", ["HepMC3-config", "--version"]),
        _from_command("FastJet", ["fastjet-config", "--version"]),
        _from_command("ROOT", ["root-config", "--version"]),
        _from_command("YODA", ["yoda-config", "--version"]),
        _from_command("Pythia", ["pythia8-config", "--version"]),
        _from_command("Rivet", ["rivet", "--version"]),
        herwig(),
        _sherpa(),
        _from_command("Whizard", ["whizard", "--version"]),
        _from_file("MadGraph", root / "madgraph" / "bin" / "mg5_aMC"),
        _from_file("Delphes", root / "delphes" / "bin" / "DelphesHepMC3"),
        _from_file("ONNX Runtime", root / "onnxruntime" / "lib" / "libonnxruntime.so"),
    ]
    return {tool.name: tool for tool in tools}


