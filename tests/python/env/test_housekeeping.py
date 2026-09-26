"""The end state: no transitional code, and the two housekeeping commands (P10-S01, 07 §6).

**The shim check is an AST walk, not a grep**, and the difference is the point. The step's
Verification row asks for `git grep rivpyth|ydmrg|…` to be empty outside `legacy/`, and it never can
be: the names appear in `config/migrate.py`, which is *exactly* where the Goal says v1 reading
belongs, and in a dozen docstrings that record where a function was ported from. Deleting those
comments to make a grep pass would destroy the only record of why some of this code is shaped the
way it is, and would not remove a single line of transitional behaviour.

So the check here asks the question the row means: **is there executable code outside `migrate` that
still speaks v1?** Docstrings and comments are excluded by parsing rather than by pattern, which is
the only way to tell "this code reads `[rivpyth]`" from "this comment says the old tool did".

The rest is `hep clean` — whose contract is as much about what it refuses to touch as what it
removes — and `hep new`, whose scaffolds have to actually build.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "utils" / "python"))

from hekit.env import scaffold                                           # noqa: E402
from hekit.errors import HepError                                        # noqa: E402
from hekit.results import clean as clean_module                          # noqa: E402

#: The legacy tools, and the storage design that was rejected (D13).
LEGACY_NAMES = ("rivpyth", "ydmrg", "ydplt", "NtupleAnalyzer", "RNTuple")

#: Where v1 may still be spoken. The Goal names `migrate`; `validate` only *detects* a v1 file so it
#: can say "run hep config migrate" instead of a wall of unknown-key errors, which is the error path
#: rather than a shim.
ALLOWED = {"config/migrate.py", "config/validate.py"}


def python_sources() -> list[Path]:
    return sorted((REPO / "utils" / "python" / "hekit").rglob("*.py"))


def executable_text(path: Path) -> list[str]:
    """Every string literal and identifier that is *not* a docstring or a comment."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))

    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstrings:
                found.append(node.value)
        elif isinstance(node, ast.Name):
            found.append(node.id)
        elif isinstance(node, ast.Attribute):
            found.append(node.attr)
    return found


# ── the end state ────────────────────────────────────────────────────────────

def test_no_executable_code_speaks_v1_outside_migrate():
    """Rule 1's end state, asked as a question about behaviour rather than about text."""
    offenders: list[str] = []
    for path in python_sources():
        relative = path.relative_to(REPO / "utils" / "python" / "hekit").as_posix()
        if relative in ALLOWED:
            continue
        for text in executable_text(path):
            for name in LEGACY_NAMES:
                if name in text:
                    offenders.append(f"{relative}: {text!r}")
    assert not offenders, "transitional code outside migrate:\n  " + "\n  ".join(offenders)


def test_the_rejected_storage_design_is_gone_entirely():
    """D13 chose HepMC3 shards over ROOT ntuples; no code should mention the road not taken."""
    for path in python_sources():
        text = path.read_text(encoding="utf-8")
        assert "NtupleAnalyzer" not in text, path
        assert "RNTuple" not in text, path


def test_sources_is_gone():
    """The pre-rework tree had a `sources/` directory; the end state does not."""
    assert not (REPO / "sources").exists()


# ── hep clean: what it refuses to touch ──────────────────────────────────────

class FakeLayout:
    """Just enough of `results.layout.Layout` for the survey functions."""

    def __init__(self, root: Path):
        self.root = root
        self.project = "P"
        self.points = root / "points"
        self.studies = root / "studies"

    def orphans(self):
        found = []
        if self.points.is_dir():
            for entry in sorted(self.points.iterdir()):
                if entry.is_dir() and not any(entry.glob("*.yoda")) \
                        and not (entry / "run.summary.json").is_file():
                    found.append(entry)
        return found


@pytest.fixture
def results(tmp_path):
    """A results tree with one real point, one orphan, a store, plots and a cache."""
    point = tmp_path / "points" / "good"
    (point / "events").mkdir(parents=True)
    (point / "analysis.yoda").write_text("x" * 100, encoding="utf-8")
    (point / "run.summary.json").write_text("{}", encoding="utf-8")
    (point / "events" / "events.0.hepmc").write_text("y" * 4096, encoding="utf-8")
    (point / "events" / "events.index.json").write_text('{"shards": 1}', encoding="utf-8")

    orphan = tmp_path / "points" / "died"
    orphan.mkdir(parents=True)
    (orphan / "logs").mkdir()

    plots = tmp_path / "studies" / "01_first" / "plots" / "page"
    plots.mkdir(parents=True)
    (plots / "index.html").write_text("z" * 2048, encoding="utf-8")
    return tmp_path


def test_the_survey_finds_each_category(results):
    layout = FakeLayout(results)
    groups = {group.kind: group for group in
              clean_module.survey(layout, kinds=("events", "plots", "orphans"))}
    assert groups["events"].items and groups["events"].bytes >= 4096
    assert groups["plots"].items and groups["plots"].bytes >= 2048
    assert [item.path.name for item in groups["orphans"].items] == ["died"]


def test_removing_events_keeps_the_index_as_a_tombstone(results):
    """11 §1: a removed store must still be able to say what it held."""
    layout = FakeLayout(results)
    group = clean_module.stores(layout)
    removed, freed = clean_module.remove(group)

    assert removed == 1 and freed >= 4096
    events = results / "points" / "good" / "events"
    assert (events / "events.index.json").is_file(), "the tombstone was removed"
    assert not (events / "events.0.hepmc").exists()


def test_results_are_never_in_a_removable_category(results):
    """07 §6: YODA files, fits.json and provenance are never touched automatically."""
    layout = FakeLayout(results)
    kept = results / "points" / "good" / "analysis.yoda"
    for group in clean_module.survey(layout, kinds=clean_module.KINDS):
        for item in group.items:
            # Nothing offered for removal may be, or contain, a result.
            assert item.path != kept
            assert kept not in item.path.rglob("*") if item.path.is_dir() else True

    clean_module.remove(clean_module.plots(layout))
    clean_module.remove(clean_module.orphans(layout))
    assert (results / "points" / "good" / "analysis.yoda").is_file()
    assert (results / "points" / "good" / "run.summary.json").is_file()


def test_older_than_keeps_recent_stores(results):
    """`--older-than` is what makes `--events` safe to run on a live tree."""
    layout = FakeLayout(results)
    assert clean_module.stores(layout, days=0).items          # no age limit: found
    assert not clean_module.stores(layout, days=7).items      # written seconds ago: kept


def test_sizes_are_human_readable():
    assert clean_module.human(0) == "0 B"
    assert clean_module.human(2048) == "2.0 KiB"
    assert clean_module.human(5 * 1024 ** 3).endswith("GiB")


# ── hep new: the scaffolds have to build ─────────────────────────────────────

def test_a_name_must_work_as_a_class_and_a_file_stem():
    scaffold.check_name("MyAnalysis", "analysis")
    for bad in ("", "9lives", "my-analysis", "my analysis", "my.analysis"):
        with pytest.raises(HepError):
            scaffold.check_name(bad, "analysis")


def test_nothing_is_overwritten(tmp_path):
    """The worst possible bug in a convenience command."""
    path = tmp_path / "a.txt"
    scaffold.write(path, "first")
    with pytest.raises(HepError) as raised:
        scaffold.write(path, "second")
    assert "already exists" in str(raised.value)
    assert path.read_text(encoding="utf-8") == "first"


def test_the_analysis_scaffold_is_a_complete_plugin():
    source = scaffold.analysis_source("Demo")
    assert "RIVET_DECLARE_PLUGIN(Demo)" in source
    assert "RIVET_DEFAULT_ANALYSIS_CTOR(Demo)" in source
    for verb in ("void init()", "void analyze(", "void finalize()"):
        assert verb in source
    # Scaling belongs in finalize, and the scaffold must not teach otherwise.
    assert source.index("scale(") > source.index("void finalize()")

    info = scaffold.analysis_info("Demo")
    assert info.startswith("Name: Demo")
    assert "Reentrant: true" in info


def test_the_module_scaffold_obeys_the_scaling_contract():
    """05 §5: fills are raw weights, and scaling happens only in `finalize`."""
    source = scaffold.module_source("Demo")
    assert 'HEKIT_MODULE("Demo", Demo)' in source
    for verb in ("void configure(", "void book(", "void process(", "void finalize("):
        assert verb in source
    # `normalise` only after `finalize`, and no scaling inside `process`.
    process = source.index("void process(")
    finalize = source.index("void finalize(")
    assert source.index("results.normalise") > finalize
    assert "normalise" not in source[process:finalize]
    assert "threadSafe" in source, "a first module must be told about 00/B31"


def test_the_project_scaffold_is_a_loadable_config(tmp_path):
    from hekit.config import load_config

    (tmp_path / "base.cmnd").write_text(scaffold.project_card("Demo"), encoding="utf-8")
    path = tmp_path / "demo.toml"
    path.write_text(scaffold.project_config("Demo", "DemoAnalysis"), encoding="utf-8")

    config = load_config(path)
    assert config.project == "Demo"
    assert config.rivet.analyses == ["DemoAnalysis"]
    assert config.run.events > 0


# ── the commands are wired, not just the modules ─────────────────────────────

def _invoke(*arguments):
    from click.testing import CliRunner

    from hekit.cli import hep

    return CliRunner().invoke(hep, list(arguments))


def test_hep_clean_is_no_longer_a_placeholder():
    result = _invoke("clean", "--help")
    assert result.exit_code == 0
    for category in clean_module.KINDS:
        assert f"--{category}" in result.output
    assert "--dry-run" in result.output


def test_hep_clean_says_what_it_needs():
    """Without a config it cannot know which project's results to look at."""
    result = _invoke("clean")
    assert result.exit_code != 0
    assert "config" in str(result.exception)


def test_hep_new_is_wired_and_writes_what_it_says(tmp_path):
    result = _invoke("new", "module", "Wired", "--into", str(tmp_path))
    assert result.exit_code == 0, result.output
    written = tmp_path / "modules" / "Wired" / "Wired.cc"
    assert written.is_file()
    assert 'HEKIT_MODULE("Wired", Wired)' in written.read_text(encoding="utf-8")
    assert str(written) in result.output


def test_hep_new_refuses_an_unknown_kind():
    result = _invoke("new", "telescope", "Thing")
    assert result.exit_code != 0
