"""docs/stack/build_stack.py: the stack's build, from packages.toml and settings.toml. Only plans and
dry runs here (nothing is built or downloaded); every prefix is a tmp_path."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from runner import plugins

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def bs():
    return plugins.load(REPO / "docs" / "stack" / "build_stack.py", "build_stack")


def planned(bs, prefix, *args):
    _, s, packages = bs.options([f"prefix={prefix}", *args])
    c = bs.context(s)
    return bs.plan(s, packages, c), packages, c


def test_core_and_all_follow_the_file(bs, tmp_path):
    (core, added), packages, _ = planned(bs, tmp_path)
    assert added == []
    assert core == [n for n, p in packages.items() if p.get("group", "core") == "core"]
    assert core[0] == "python" and core[-1] == "pdfsets"
    (everything, _), _, _ = planned(bs, tmp_path, "packages=all")
    assert everything == list(packages)
    for name in everything:                                        # each after what it needs
        assert all(everything.index(need) < everything.index(name) for need in packages[name].get("needs", []))


def test_needs_are_added_only_when_missing(bs, tmp_path):
    (order, added), _, _ = planned(bs, tmp_path, "packages=rivet")
    assert order == ["python", "hepmc3", "yoda", "fastjet", "fjcontrib", "rivet"]
    assert added == order[:-1]
    stamps = tmp_path / ".stamps"
    stamps.mkdir()
    for name in ("python", "hepmc3-3.3.1", "yoda-2.1.3"):
        (stamps / name).touch()
    (tmp_path / "install" / "fastjet" / "lib").mkdir(parents=True)  # FastJet installed otherwise: its dir
    (order, added), _, _ = planned(bs, tmp_path, "packages=rivet")
    assert order == ["fjcontrib", "rivet"]                         # fjcontrib's probe is its library


def test_overrides_reach_the_tarball_and_the_arguments(bs, tmp_path):
    (_, _), packages, c = planned(bs, tmp_path, "root.release=6.40.06", "graphics=OFF", "root_extra=-Da=1 -Db=2")
    file, url = bs.tarball("root", packages["root"], c)
    assert file.name == "root-6.40.06.tar.gz" and url.endswith("root_v6.40.06.source.tar.gz")
    k = bs.scope("root", packages["root"], c)
    args = bs.words(packages["root"]["args"], k)
    assert "-Dx11=OFF" in args and args[-2:] == ["-Da=1", "-Db=2"]   # a list setting gives its words
    _, s, packages = bs.options([f"prefix={tmp_path}", "madgraph.release=3.6.2"])
    assert "/3.6.x/" in bs.tarball("madgraph", packages["madgraph"], bs.context(s))[1]   # {series}


@pytest.mark.parametrize("arg", ["jobz=3", "root.relase=1", "nope.release=1", "bogus", "jobs=abc",
                                 "packages=foo"])
def test_mistakes_are_refused(bs, tmp_path, arg):
    with pytest.raises(SystemExit):
        planned(bs, tmp_path, arg)


def test_a_config_file_changes_and_adds_packages(bs, tmp_path):
    extra = tmp_path / "my.toml"
    extra.write_text('jobs = 3\n[root]\nrelease = "6.40.06"\n'
                     '[mine]\nrelease = "1"\nurl = "https://x/mine-{release}.tgz"\nkind = "cmake"\nneeds = ["root"]\n')
    (order, added), packages, c = planned(bs, tmp_path, "--config", str(extra), "packages=mine", "jobs=2")
    assert order == ["python", "root", "mine"] and added == ["python", "root"]
    assert c["jobs"] == 2 and packages["root"]["release"] == "6.40.06"   # the command line wins over the file


def test_the_dry_run_is_a_bash_script_and_writes_nothing(bs, tmp_path, capsys):
    prefix = tmp_path / "hep"
    bs.main(["--dry-run", f"prefix={prefix}", "packages=all", "system=false", "root_jobs=2"])
    script = capsys.readouterr().out
    assert not prefix.exists()
    assert script.isascii()                                         # any locale can print and save it
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0
    for line in ("set -euo pipefail", "-p0 -i " + str(REPO / "utils/Env/patches"), "--with-hepmcversion=3",
                 "make fragile-shared-install", f"cmake --build {prefix}/build/root -j2",
                 f"--with-root={prefix}/install/root", "lhapdf install CT14lo CT14nlo", "cat > "):
        assert line in script, line
    assert script.index("# == root") < script.index("# == pythia8")
