"""utils/Env/stack.toml (V78): one registry of the software stack, read by flags.sh, the Makefile (KNOWN),
the tool folders' versions and `hep status --stack`."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

from runner import plugins, tools

REPO = Path(__file__).resolve().parents[2]
ENV = REPO / "utils" / "Env"


@pytest.fixture(scope="module")
def stack():
    return plugins.load(ENV / "stack.py", "stack")


def test_flags_sh_probes_what_the_stack_lists(stack):
    text = stack.bash()
    names = [n for n, e in stack.entries().items() if e.get("flags") or e.get("dir")]
    assert f"NAMES=({' '.join(names)})" in text
    assert "    probe pythia8 pythia8-config --cxxflags --ldflags" in text
    assert '    dir_lib delphes "${HEP_INSTALL-}/delphes" Delphes' in text
    assert text.startswith("TOOLS=(") and "pkg-config" in text.splitlines()[0]


def test_the_flags_cache_says_what_is_known_and_keys_on_the_stack():
    key = subprocess.run([str(ENV / "flags.sh"), "--key"], capture_output=True, text=True).stdout
    assert ";STACK=" in key
    flags = REPO / "build" / "flags.mk"
    if flags.exists():                                              # written by make, from the stack
        known = next((l for l in flags.read_text(encoding="utf-8").splitlines() if l.startswith("KNOWN := ")), "")
        assert known.split(" := ")[1].split() == [n for n, e in tomllib.loads((ENV / "stack.toml").read_text(encoding="utf-8")).items()
                                                  if e.get("flags") or e.get("dir")]


def test_every_tool_version_names_a_stack_entry(stack):
    """A tool folder's [identity] version = "stack:<name>" names an entry with a version."""
    for folder in tools.folders().values():
        command = folder.get("identity", "version")
        if isinstance(command, str):
            assert command.startswith("stack:"), folder.name
            assert stack.version_command(command.removeprefix("stack:")), folder.name


def test_a_file_version_reads_the_files_version_line(stack, monkeypatch, tmp_path):
    (tmp_path / "VERSION").write_text("version = 3.7.3\ndate = x\n", encoding="utf-8")
    monkeypatch.setenv("HEP_INSTALL", str(tmp_path / "x"))
    monkeypatch.setattr(stack, "entries", lambda: {"mg": {"version": {"file": str(tmp_path / "VERSION")}}})
    assert stack.version("mg") == "version = 3.7.3"
    assert stack.expand("${HEP_INSTALL-}/madgraph") == str(tmp_path / "x" / "madgraph")
