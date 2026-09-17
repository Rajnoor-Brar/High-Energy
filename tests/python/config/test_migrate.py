"""Migration, the generated reference and the starter file (P1-S06)."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from hekit import sweep
from hekit.config import load_config, schema as sch
from hekit.config.migrate import (bare, dumps, format_value, migrate_document, migrate_file, to_toml)
from hekit.config.reference import markdown, starter
from hekit.errors import HepError
from hekit.plan import build as builder

REPO = Path(__file__).resolve().parents[3]
INPUTS = REPO / "tests" / "golden" / "inputs" / "PhotoProduction"
CONFIGS = REPO / "configs" / "PhotoProduction"


@pytest.fixture(scope="module")
def migrated(tmp_path_factory) -> Path:
    """The frozen eic input migrated the way the committed file was."""
    directory = tmp_path_factory.mktemp("migrated")
    result = migrate_file(INPUTS / "eic.toml")
    path = directory / "eic.v2.toml"
    path.write_text(dumps(result, name=path.name, source="eic.toml"), encoding="utf-8")
    (directory / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    return path


def run_hep(*arguments: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "hekit.cli", *arguments],
                          capture_output=True, text=True, cwd=cwd, timeout=120, input="")


# ── what the migration produces ──────────────────────────────────────────────

def test_the_migrated_file_loads(migrated):
    config = load_config(migrated, machine_file=None, project="PhotoProduction")
    assert config.schema == 2
    assert config.run.name == "eic" and config.run.threads == 20 and config.run.events == 1_000_000
    assert config.generator.card == "photo_ep.cmnd"
    assert config.rivet.analyses == ["photo_eic"]
    assert len(config.studies) == 10


def test_quantities_are_renamed_to_match_their_types(migrated):
    config = load_config(migrated, machine_file=None, project="PhotoProduction")
    assert config.quantities["energies"].type == "energies"      # v1 called this "beams"
    assert config.quantities["beams"].type == "beams"            # v1 called this "lepton"
    assert config.quantities["beams"].side == "b"
    assert "lepton" not in config.quantities
    assert bare("cmnd.beams") == "energies" and bare("cmnd.lepton") == "beams"


def test_misleading_pdf_tags_are_renamed_with_a_note(migrated):
    """00/B12: the tags read like perturbative orders but name PDF sets."""
    config = load_config(migrated, machine_file=None, project="PhotoProduction")
    pdf = config.quantities["pdf"]
    assert pdf.tags == ["MSTW08lo", "NNPDF23lo", "NNPDF23nlo", "PDF4LHC21"]
    assert "NNPDF23lo was NNLO" in pdf.note


def test_the_selectors_follow_the_quantities(migrated):
    config = load_config(migrated, machine_file=None, project="PhotoProduction")
    assert config.settle.use == {"energies": "27x920", "beams": "ep"}
    assert config.studies["radius"].pin == {"energies": "18x275"}
    assert config.studies["energy_pdf"].across == ["energies", "pdf"]


def test_an_index_selector_becomes_an_explicit_index():
    """D-B22: a v1 integer pin meant a position, which is now written `#N`."""
    raw = tomllib.loads((INPUTS / "eic.toml").read_text(encoding="utf-8"))
    raw["settle"]["use"]["cmnd.pdf"] = 3
    document = migrate_document(raw, drop_undeclared_options=False).document
    assert document["settle"]["use"]["pdf"] == "#3"


def test_undeclared_option_quantities_are_dropped(tmp_path):
    """00/B14: ZEUS_2012_I1116258 declares no options, so scanning R was meaningless."""
    result = migrate_file(INPUTS / "zeus_validation.toml")
    assert "radius" not in result.document["quantity"]
    assert "etmin" not in result.document["quantity"]
    assert any("does not declare 'R'" in note for note in result.notes)


def test_dropped_quantities_leave_no_dangling_references():
    raw = tomllib.loads((INPUTS / "zeus_validation.toml").read_text(encoding="utf-8"))
    raw["sweep"]["across"] = ["rivet.radius"]
    raw["study"] = {"r": {"across": ["rivet.radius"], "overlay": "rivet.radius"}}
    result = migrate_document(raw, config_dir=INPUTS)
    assert result.document["sweep"]["across"] == []
    assert result.document["study"]["r"]["across"] == []
    assert "overlay" not in result.document["study"]["r"]
    assert any("no longer scans radius" in note for note in result.notes)


def test_everything_that_changes_is_reported():
    result = migrate_file(INPUTS / "eic.toml")
    joined = " ".join(result.notes)
    for expected in ("serial dropped", "seed_step dropped", "becomes type = \"energies\"",
                     "side = \"b\"", "tags renamed"):
        assert expected in joined


def test_a_schema_2_file_is_refused(migrated):
    with pytest.raises(HepError, match="already declares a schema version"):
        migrate_file(migrated)


def test_a_file_that_is_not_a_run_config_is_refused(tmp_path):
    path = tmp_path / "other.toml"
    path.write_text("[tool.black]\nline-length = 100\n", encoding="utf-8")
    with pytest.raises(HepError, match="does not look like a schema-1 run file"):
        migrate_file(path)


def test_a_table_valued_quantity_is_reported_rather_than_guessed():
    raw = tomllib.loads((INPUTS / "eic.toml").read_text(encoding="utf-8"))
    del raw["sweep"]["cmnd"]["pdf"]["setting"]
    raw["sweep"]["cmnd"]["pdf"]["values"] = [{"A:b": 1}, {"A:b": 2}]
    with pytest.raises(HepError, match="has no 'setting'"):
        migrate_document(raw)


def test_a_data_file_migrates_with_an_empty_map(tmp_path):
    """00/B5: schema 2 overlays reference data only where it is mapped explicitly."""
    raw = tomllib.loads((INPUTS / "eic.toml").read_text(encoding="utf-8"))
    raw["yoda"]["use_data"] = True
    raw["yoda"]["data_file"] = "datasets/zeus_eic.yoda"
    result = migrate_document(raw, config_dir=INPUTS)
    assert result.document["plot"]["data"]["file"] == "datasets/zeus_eic.yoda"
    assert result.document["plot"]["data"]["map"] == {}
    assert any("00/B5" in note for note in result.notes)


# ── the plan is the same ─────────────────────────────────────────────────────

def plan_of(path: Path, **arguments):
    config = load_config(path, machine_file=None, project="PhotoProduction")
    return builder.build(config, sweep.select(config, **arguments))


def test_the_committed_file_plans_like_a_fresh_migration(migrated):
    """The `.v2.toml` in configs/ must be exactly what the tool produces today."""
    committed = CONFIGS / "eic.v2.toml"
    fresh = migrate_file(CONFIGS / "eic.toml")
    assert to_toml(fresh.document) == to_toml(
        tomllib.loads(committed.read_text(encoding="utf-8")))


def test_the_migrated_plan_matches_the_in_memory_migration(migrated, tmp_path):
    """Same inputs, same plan: writing the file changes nothing."""
    in_memory = migrate_file(INPUTS / "eic.toml")
    other = tmp_path / "again.toml"
    other.write_text(to_toml(in_memory.document), encoding="utf-8")
    (tmp_path / "photo_ep.cmnd").write_bytes((INPUTS / "photo_ep.cmnd").read_bytes())
    first = plan_of(migrated, study="energy_pdf")
    second = plan_of(other, study="energy_pdf")
    assert [point.name for point in first.points] == [point.name for point in second.points]
    assert [group.identity.hash for group in first.groups] == \
           [group.identity.hash for group in second.groups]


def test_the_migration_only_renames_what_it_says(migrated):
    """Point names differ from the legacy ones exactly by the tag renames (00/B12)."""
    faithful = migrate_file(INPUTS / "eic.toml", rename_tags=False, drop_undeclared_options=False)
    path = migrated.with_name("faithful.toml")
    path.write_text(to_toml(faithful.document), encoding="utf-8")
    renamed = [point.name for point in plan_of(migrated, study="pdf").points]
    original = [point.name for point in plan_of(path, study="pdf").points]
    table = {"MSTW": "MSTW08lo", "NNLO": "NNPDF23lo", "NNNLO": "NNPDF23nlo", "LHC21": "PDF4LHC21"}
    assert renamed == [name.replace(old, new) for name, (old, new) in zip(original, table.items())]


# ── the emitter ──────────────────────────────────────────────────────────────

def test_short_arrays_stay_on_one_line():
    assert format_value([2212, 11]) == "[2212, 11]"
    assert format_value([[41, 5], [920, 27.5]]) == "[[41, 5], [920, 27.5]]"
    assert format_value([]) == "[]"


def test_long_arrays_are_wrapped():
    rendered = format_value(["a very long label indeed " * 2] * 5)
    assert rendered.startswith("[\n    ") and rendered.endswith("]")


def test_keys_that_need_quoting_get_it():
    text = to_toml({"settle": {"gen": {"PhaseSpace:pTHatMin": 6.0, "plain": 1}}})
    assert '"PhaseSpace:pTHatMin" = 6.0' in text
    assert "plain = 1" in text


def test_a_table_of_tables_gets_no_empty_header():
    text = to_toml({"quantity": {"pdf": {"type": "setting"}}})
    assert "[quantity]" not in text and "[quantity.pdf]" in text


def test_arrays_of_tables_are_emitted(tmp_path):
    text = to_toml({"sinks": {"module": [{"name": "a"}, {"name": "b"}]}})
    assert text.count("[[sinks.module]]") == 2
    assert tomllib.loads(text)["sinks"]["module"][1]["name"] == "b"


def test_the_emitter_round_trips_the_whole_config(migrated):
    document = tomllib.loads(migrated.read_text(encoding="utf-8"))
    assert tomllib.loads(to_toml(document)) == document


# ── the reference and the starter ────────────────────────────────────────────

def test_the_reference_documents_every_section():
    text = markdown()
    for name in sch.SECTIONS:
        assert f"`[{name}]`" in text
    for key in sch.TOP_LEVEL:
        assert f"`{key}`" in text
    assert "`[plot.data]`" in text
    assert "machine file" in text


def test_the_reference_is_deterministic():
    assert markdown() == markdown()


def test_the_committed_reference_is_current():
    committed = REPO / "docs" / "rework" / "reference" / "config.md"
    assert committed.read_text(encoding="utf-8") == markdown(), \
        "run: hep config reference --write docs/rework/reference/config.md"


def test_the_starter_file_says_what_is_still_missing(tmp_path):
    """A scaffold is incomplete by design; loading it must say exactly what to fill in."""
    path = tmp_path / "run.toml"
    path.write_text(starter("Demo"), encoding="utf-8")
    (tmp_path / "base.cmnd").write_text("Main:numberOfEvents = 10\n", encoding="utf-8")
    with pytest.raises(HepError) as raised:
        load_config(path, machine_file=None, project="Demo")
    assert "nothing would consume the events" in raised.value.message
    assert "[rivet].analyses" in raised.value.hint


def test_the_starter_file_is_valid_once_an_analysis_is_named(tmp_path):
    path = tmp_path / "run.toml"
    path.write_text(starter("Demo").replace("analyses = []", 'analyses = ["MC_JETS"]'), encoding="utf-8")
    (tmp_path / "base.cmnd").write_text("Main:numberOfEvents = 10\n", encoding="utf-8")
    config = load_config(path, machine_file=None, project="Demo")
    assert config.run.name == "demo" and config.generator.card == "base.cmnd"
    assert config.beams.ids == [2212, 11]


# ── the commands ─────────────────────────────────────────────────────────────

def test_migrate_to_stdout_can_be_validated(tmp_path):
    migrate = run_hep("config", "migrate", str(INPUTS / "eic.toml"), "--stdout", cwd=tmp_path)
    assert migrate.returncode == 0, migrate.stderr
    (tmp_path / "round.toml").write_text(migrate.stdout, encoding="utf-8")
    (tmp_path / "photo_ep.cmnd").write_text("Main:numberOfEvents = 1\n", encoding="utf-8")
    check = run_hep("config", "validate", str(tmp_path / "round.toml"), cwd=tmp_path)
    assert check.returncode == 0, check.stderr
    assert "valid schema-2 configuration" in check.stdout


def test_migrate_never_overwrites_silently(tmp_path):
    target = tmp_path / "out.toml"
    target.write_text("keep me\n", encoding="utf-8")
    done = run_hep("config", "migrate", str(INPUTS / "eic.toml"), "--write", str(target), cwd=tmp_path)
    assert done.returncode == 1 and "--force" in done.stderr
    assert target.read_text(encoding="utf-8") == "keep me\n"
    forced = run_hep("config", "migrate", str(INPUTS / "eic.toml"), "--write", str(target),
                     "--force", cwd=tmp_path)
    assert forced.returncode == 0 and "schema = 2" in target.read_text(encoding="utf-8")


def test_config_reference_and_init(tmp_path):
    reference = run_hep("config", "reference", cwd=tmp_path)
    assert reference.returncode == 0 and "Configuration reference" in reference.stdout
    init = run_hep("config", "init", "Demo", cwd=tmp_path)
    assert init.returncode == 0 and "schema = 2" in init.stdout


def test_validate_reports_the_committed_configs(tmp_path):
    for name in ("eic.v2.toml", "zeus_validation.v2.toml"):
        done = run_hep("config", "validate", str(CONFIGS / name), cwd=tmp_path)
        assert done.returncode == 0, done.stderr
        assert "valid schema-2 configuration for project 'PhotoProduction'" in done.stdout


def test_validate_explains_a_broken_file(tmp_path):
    path = tmp_path / "broken.toml"
    path.write_text("schema = 2\n[run]\nthreads = -3\n", encoding="utf-8")
    done = run_hep("config", "validate", str(path), cwd=tmp_path)
    assert done.returncode == 2 and "must be ≥ 0" in done.stderr
