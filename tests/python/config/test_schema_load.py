"""Schema 2: layering, origins and every validation rule (P1-S02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hekit.config import load_config
from hekit.config import load as ld
from hekit.config import schema as sch
from hekit.config.fields import Field, check, parse_duration
from hekit.errors import HepError

MINIMAL = """\
schema = 2

[run]
name    = "demo"
events  = 1000
seed    = 270403
threads = 4

[generator]
tool = "pythia"
card = "photo_ep.cmnd"

[beams]
ids      = [2212, 11]
energies = [41, 5]

[rivet]
analyses = ["photo_eic"]
options  = { R = 1.0 }

[sweep]
across = ["pdf"]

[quantity.pdf]
type   = "setting"
key    = "PDF:pSet"
values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]
labels = ["MSTW 2008 LO", "NNPDF 2.3 LO"]
tags   = ["MSTW", "NNLO"]
use    = 2
"""


@pytest.fixture
def write(tmp_path: Path):
    """Write a config (or any TOML) into the test's own directory and return its path."""
    def writer(text: str, name: str = "run.toml") -> Path:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    return writer


def load(path: Path, **kwargs):
    kwargs.setdefault("machine_file", None)
    return load_config(path, **kwargs)


def variant(*replacements: tuple[str, str], base: str = MINIMAL) -> str:
    text = base
    for old, new in replacements:
        assert old in text, old
        text = text.replace(old, new, 1)
    return text


# ── the happy path ───────────────────────────────────────────────────────────

def test_minimal_config_loads(write):
    config = load(write(MINIMAL))
    assert config.schema == sch.SCHEMA_VERSION
    assert (config.run.name, config.run.events, config.run.threads) == ("demo", 1000, 4)
    assert config.generator.tool == "pythia"
    assert config.beams.ids == [2212, 11] and config.beams.energies == [41, 5]
    assert config.rivet.analyses == ["photo_eic"] and config.rivet.options == {"R": 1.0}
    assert config.quantities["pdf"].type == "setting"
    assert config.warnings == []


def test_defaults_fill_untouched_keys(write):
    config = load(write(MINIMAL))
    assert config.plot.backend == "mkhtml"              # never mentioned in the file
    assert config.terminal.stall_after == 300.0         # "5m" parsed
    assert config.output.tag_style == "tag"
    assert config.origin("plot.backend") == "default"


def test_project_comes_from_the_directory(write, tmp_path):
    path = tmp_path / "configs" / "PhotoProduction" / "eic.toml"
    path.parent.mkdir(parents=True)
    path.write_text(MINIMAL, encoding="utf-8")
    assert load(path).project == "PhotoProduction"
    assert load(path, project="Other").project == "Other"


# ── unknown keys and bad values ──────────────────────────────────────────────

def test_unknown_key_suggests_the_right_one(write):
    path = write(MINIMAL + "\n[plot]\nmin_entry = 3\n")
    with pytest.raises(HepError) as raised:
        load(path)
    assert "unknown key 'min_entry'" in raised.value.message
    assert "min_entries" in raised.value.hint
    assert f"{path}:" in raised.value.where       # the file and the line


def test_unknown_section_is_an_error(write):
    with pytest.raises(HepError, match="unknown section 'plto'") as raised:
        load(write(MINIMAL + "\n[plto]\nbackend = \"mpl\"\n"))
    assert "plot" in raised.value.hint


def test_unknown_top_level_key(write):
    with pytest.raises(HepError, match="unknown key 'shema'"):
        load(write("shema = 2\n" + MINIMAL))


def test_negative_thread_count_does_not_wrap(write):
    with pytest.raises(HepError, match="must be ≥ 0, not -1"):
        load(write(variant(("threads = 4", "threads = -1"))))


def test_thread_count_has_an_upper_bound(write):
    with pytest.raises(HepError, match="must be ≤ 4096"):
        load(write(variant(("threads = 4", "threads = 99999"))))


def test_bool_is_not_an_integer(write):
    with pytest.raises(HepError, match="must be an integer, not bool"):
        load(write(variant(("threads = 4", "threads = true"))))


def test_enum_value_is_checked(write):
    with pytest.raises(HepError) as raised:
        load(write(variant(('tool = "pythia"', 'tool = "pithya"'))))
    assert "not allowed" in raised.value.message and "'pythia'" in raised.value.hint


def test_a_table_where_a_value_belongs_is_rejected(write):
    # [quantity.*].key may be a per-tool table, so tables are kept whole and checked by their field
    with pytest.raises(HepError, match="must be a string, not table"):
        load(write(MINIMAL + '\n[rivet.mode]\nvalue = "inprocess"\n'))


def test_a_free_table_does_not_nest_twice(write):
    with pytest.raises(HepError, match="does not take nested keys"):
        load(write(MINIMAL + '\n[settle.gen.deeper]\n"A:b" = 1\n'))


def test_free_table_accepts_invented_keys(write):
    config = load(write(MINIMAL + '\n[settle.gen]\n"PhaseSpace:pTHatMin" = 4.0\n"PartonLevel:MPI" = false\n'))
    assert config.settle.gen == {"PhaseSpace:pTHatMin": 4.0, "PartonLevel:MPI": False}


def test_free_table_values_are_still_checked(write):
    with pytest.raises(HepError, match="must be a single value"):
        load(write(MINIMAL + '\n[settle.gen]\n"A:b" = [1, 2]\n'))


# ── layering ─────────────────────────────────────────────────────────────────

def test_extends_layers_left_to_right(write, tmp_path):
    write("schema = 2\n[run]\nthreads = 1\nlabel = \"from-a\"\n", "a.toml")
    write("schema = 2\n[run]\nthreads = 2\n", "b.toml")
    path = write(variant(('threads = 4', 'threads = 4')).replace(
        "schema = 2\n", "schema = 2\nextends = [\"a.toml\", \"b.toml\"]\n"))
    config = load(path)
    assert config.run.threads == 4                       # this file wins over both
    assert config.run.label == "from-a"                  # only a.toml sets it
    assert config.origin("run.label").endswith("a.toml:4")
    layers = [layer for layer, _, _ in config.explain("run.threads")]
    assert layers == ["default", str(tmp_path / "a.toml"), str(tmp_path / "b.toml"), str(path)]


def test_extends_paths_are_relative_to_the_file_that_names_them(write, tmp_path):
    write("schema = 2\n[run]\nlabel = \"deep\"\n", "common/base.toml")
    write("schema = 2\nextends = [\"base.toml\"]\n", "common/middle.toml")
    path = write(MINIMAL.replace("schema = 2\n", "schema = 2\nextends = [\"common/middle.toml\"]\n"))
    assert load(path).run.label == "deep"


def test_extends_cycle_names_the_files(write):
    write("schema = 2\nextends = [\"b.toml\"]\n", "a.toml")
    write("schema = 2\nextends = [\"a.toml\"]\n", "b.toml")
    path = write(MINIMAL.replace("schema = 2\n", "schema = 2\nextends = [\"a.toml\"]\n"))
    with pytest.raises(HepError, match="extends forms a cycle") as raised:
        load(path)
    assert "a.toml" in raised.value.hint and "b.toml" in raised.value.hint


def test_missing_extends_file_is_named(write):
    path = write(MINIMAL.replace("schema = 2\n", "schema = 2\nextends = [\"absent.toml\"]\n"))
    with pytest.raises(HepError, match="configuration file not found"):
        load(path)


def test_tables_merge_while_lists_replace(write):
    write('schema = 2\n[rivet]\nanalyses = ["old"]\noptions = { R = 0.4, ETMIN = 5 }\n', "a.toml")
    path = write(MINIMAL.replace("schema = 2\n", "schema = 2\nextends = [\"a.toml\"]\n"))
    config = load(path)
    assert config.rivet.analyses == ["photo_eic"]                 # list replaced
    assert config.rivet.options == {"R": 1.0, "ETMIN": 5}         # table merged, R overridden


def test_set_overrides_everything(write):
    config = load(write(MINIMAL), sets=("run.threads=8", "run.label=quick", "run.skip_existing=true"))
    assert (config.run.threads, config.run.label, config.run.skip_existing) == (8, "quick", True)
    assert config.origin("run.threads") == "cli"
    assert config.explain("run.threads")[-1][0] == "cli"


def test_set_needs_an_assignment(write):
    with pytest.raises(HepError, match="--set expects key=value"):
        load(write(MINIMAL), sets=("run.threads",))


def test_set_is_type_checked(write):
    with pytest.raises(HepError, match="must be an integer"):
        load(write(MINIMAL), sets=("run.threads=many",))


# ── the machine file ─────────────────────────────────────────────────────────

def test_machine_file_may_set_allow_listed_keys(write, tmp_path):
    machine = write("[run]\nthreads = 64\n[terminal]\nlog_tail = 20\n", "machine.toml")
    config = load_config(write(variant(("threads = 4\n", ""))), machine_file=machine)
    assert config.run.threads == 64 and config.terminal.log_tail == 20
    assert config.origin("run.threads").endswith("machine.toml:2")


def test_the_file_still_wins_over_the_machine_file(write):
    machine = write("[run]\nthreads = 64\n", "machine.toml")
    assert load_config(write(MINIMAL), machine_file=machine).run.threads == 4


def test_machine_file_may_not_change_physics(write):
    machine = write("[generator]\ncard = \"sneaky.cmnd\"\n", "machine.toml")
    with pytest.raises(HepError) as raised:
        load_config(write(MINIMAL), machine_file=machine)
    assert "may not set 'generator.card'" in raised.value.message
    assert "run.threads" in raised.value.hint


def test_missing_machine_file_is_fine(write, tmp_path):
    assert load_config(write(MINIMAL), machine_file=tmp_path / "absent.toml").run.threads == 4


# ── schema version ───────────────────────────────────────────────────────────

def test_schema_key_is_required(write):
    with pytest.raises(HepError, match="missing 'schema = 2'"):
        load(write(MINIMAL.replace("schema = 2\n", "")))


def test_unsupported_schema_version(write):
    with pytest.raises(HepError, match="unsupported schema version"):
        load(write(MINIMAL.replace("schema = 2", "schema = 3")))


def test_a_schema_1_file_points_at_the_migration():
    legacy = Path(__file__).resolve().parents[3] / "tests/golden/inputs/PhotoProduction/eic.toml"
    with pytest.raises(HepError) as raised:
        load(legacy)
    assert "schema-1" in raised.value.message
    assert "hep config migrate" in raised.value.hint
    assert "[analysis]" in raised.value.message and "[yoda]" in raised.value.message


# ── quantities ───────────────────────────────────────────────────────────────

def test_labels_must_match_the_value_count(write):
    with pytest.raises(HepError, match="labels has 1 entries for 2 values"):
        load(write(variant(('labels = ["MSTW 2008 LO", "NNPDF 2.3 LO"]', 'labels = ["only"]'))))


def test_tags_must_be_filename_safe_and_unique(write):
    with pytest.raises(HepError, match="not filename-safe"):
        load(write(variant(('tags   = ["MSTW", "NNLO"]', 'tags   = ["MSTW", "a/b"]'))))
    with pytest.raises(HepError, match="tags must be unique"):
        load(write(variant(('tags   = ["MSTW", "NNLO"]', 'tags   = ["same", "same"]'))))


def test_use_must_be_within_the_values(write):
    with pytest.raises(HepError, match="use = 5 is outside 1..2"):
        load(write(variant(("use    = 2", "use    = 5"))))


def test_quantity_name_must_be_an_identifier(write):
    with pytest.raises(HepError, match="is not a valid quantity name"):
        load(write(variant(("[quantity.pdf]", '[quantity."pdf set"]'), ('across = ["pdf"]', "across = []"))))


def test_setting_quantity_needs_a_key(write):
    with pytest.raises(HepError, match="needs a key"):
        load(write(variant(('key    = "PDF:pSet"\n', ""))))


def test_per_tool_keys_are_checked(write):
    config = load(write(variant(('key    = "PDF:pSet"',
                                 'key    = { pythia = "PDF:pSet", sherpa = "PDF_SET" }'))))
    assert config.quantities["pdf"].key == {"pythia": "PDF:pSet", "sherpa": "PDF_SET"}
    with pytest.raises(HepError, match="no such tool 'pytia'"):
        load(write(variant(('key    = "PDF:pSet"', 'key    = { pytia = "PDF:pSet" }'))))


def test_option_quantity_rules(write):
    good = variant(('type   = "setting"', 'type   = "option"'), ('key    = "PDF:pSet"', 'option = "R"'),
                   ('values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]',
                    "values = [0.4, 1.0]"))
    assert load(write(good)).quantities["pdf"].option == "R"
    with pytest.raises(HepError, match="needs the option name"):
        load(write(good.replace('option = "R"\n', "")))
    with pytest.raises(HepError, match="without ':' or '='"):
        load(write(good.replace("values = [0.4, 1.0]", 'values = ["a:b", "c"]')))


def test_beams_quantity_wants_pdg_ids(write):
    beams = variant(("[quantity.pdf]", "[quantity.beam]"), ('across = ["pdf"]', 'across = ["beam"]'),
                    ('type   = "setting"', 'type   = "beams"'), ('key    = "PDF:pSet"', 'side   = "b"'),
                    ('values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]',
                     "values = [11, -11]"))
    assert load(write(beams)).quantities["beam"].values == [11, -11]
    with pytest.raises(HepError) as raised:
        load(write(beams.replace("values = [11, -11]", 'values = ["e-", "e+"]')))
    assert "particle names are not accepted" in raised.value.message and "11" in raised.value.hint
    # without `side`, each value is a pair
    with pytest.raises(HepError, match=r"\[idA, idB\]"):
        load(write(beams.replace('side   = "b"\n', "")))


def test_energies_quantity_rules(write):
    energies = variant(("[quantity.pdf]", "[quantity.energies]"), ('across = ["pdf"]', 'across = ["energies"]'),
                       ('type   = "setting"', 'type   = "energies"'), ('key    = "PDF:pSet"\n', ""),
                       ('values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]',
                        "values = [[41, 5], [275, 18]]"))
    assert load(write(energies)).quantities["energies"].values == [[41, 5], [275, 18]]
    with pytest.raises(HepError, match="both positive"):
        load(write(energies.replace("[[41, 5], [275, 18]]", "[[41, 0], [275, 18]]")))
    # a scalar is √s
    assert load(write(energies.replace("[[41, 5], [275, 18]]", "[28.6, 63.2]"))).quantities["energies"].values


def test_side_only_applies_to_beams(write):
    with pytest.raises(HepError, match="side applies only"):
        load(write(variant(('use    = 2', 'use    = 2\nside   = "b"'))))


# ── cross-section checks ─────────────────────────────────────────────────────

def test_store_needs_an_input(write):
    with pytest.raises(HepError, match="needs input"):
        load(write(variant(('tool = "pythia"\ncard = "photo_ep.cmnd"', 'tool = "store"'))))


def test_store_does_not_take_a_card(write):
    with pytest.raises(HepError, match="card does not apply"):
        load(write(variant(('tool = "pythia"', 'tool = "store"\ninput = "eic_5x41"'))))


def test_input_belongs_to_the_store_tool(write):
    with pytest.raises(HepError, match="input applies only"):
        load(write(variant(('card = "photo_ep.cmnd"', 'card = "photo_ep.cmnd"\ninput = "x"'))))


def test_a_generator_needs_its_card(write):
    with pytest.raises(HepError, match="needs its native card"):
        load(write(variant(('card = "photo_ep.cmnd"\n', ""))))


def test_shower_belongs_to_madgraph(write):
    with pytest.raises(HepError, match="shower applies only"):
        load(write(variant(('card = "photo_ep.cmnd"', 'card = "a.cmnd"\nshower = "s.cmnd"'))))


def test_native_rivet_mode_is_sherpa_only(write):
    with pytest.raises(HepError, match="only available for Sherpa"):
        load(write(variant(('analyses = ["photo_eic"]', 'analyses = ["photo_eic"]\nmode = "native"'))))


def test_something_must_consume_the_events(write):
    with pytest.raises(HepError, match="nothing would consume the events"):
        load(write(variant(('analyses = ["photo_eic"]\n', ""))))


def test_a_store_alone_is_enough(write):
    config = load(write(variant(('analyses = ["photo_eic"]', "")) + "\n[store]\nenabled = true\n"))
    assert config.store.enabled and config.rivet.analyses == []


def test_xsec_is_generator_or_a_number(write):
    assert load(write(variant(('options  = { R = 1.0 }', "xsec = 71422.0")))).rivet.xsec == 71422.0
    with pytest.raises(HepError, match="positive cross-section"):
        load(write(variant(('options  = { R = 1.0 }', "xsec = -1.0"))))
    with pytest.raises(HepError, match="is not understood"):
        load(write(variant(('options  = { R = 1.0 }', 'xsec = "whatever"'))))


def test_yodamerge_is_not_judged_at_load_time(write):
    """00/B7: the scan that runs decides, and a study can change it (checked in hekit.sweep)."""
    assert load(write(MINIMAL + '\n[plot]\nmerge = "yodamerge"\n')).plot.merge == "yodamerge"
    seeds = variant(("[quantity.pdf]", "[quantity.replica]"), ('across = ["pdf"]', 'across = ["replica"]'),
                    ('type   = "setting"', 'type   = "seed"'), ('key    = "PDF:pSet"\n', ""),
                    ('values = ["LHAPDF6:MSTW2008lo68cl", "LHAPDF6:NNPDF23_lo_as_0130_qed"]',
                     "values = [11, 22]"))
    assert load(write(seeds + '\n[plot]\nmerge = "yodamerge"\n')).quantities["replica"].type == "seed"


def test_overlay_must_be_scanned(write):
    with pytest.raises(HepError, match="overlay 'pdf' is not in across"):
        load(write(variant(('across = ["pdf"]', 'across = []\noverlay = "pdf"'))))


def test_unknown_quantity_in_across(write):
    with pytest.raises(HepError, match="undeclared quantity 'pdfs'") as raised:
        load(write(variant(('across = ["pdf"]', 'across = ["pdfs"]'))))
    assert "pdf" in raised.value.hint


def test_hidden_data_needs_to_be_the_reference(write):
    text = MINIMAL + '\n[plot.data]\nfile = "datasets/zeus.yoda"\nshow = false\nreference = false\n'
    with pytest.raises(HepError, match="show = false needs reference = true"):
        load(write(text))


def test_data_without_a_map_warns(write):
    config = load(write(MINIMAL + '\n[plot.data]\nfile = "datasets/zeus.yoda"\n'))
    assert any("00/B5" in warning for warning in config.warnings)
    mapped = MINIMAL + ('\n[plot.data]\nfile = "datasets/zeus.yoda"\n'
                        '[plot.data.map]\n"d01-x01-y01" = "/REF/ZEUS_2012_I1116258/d01-x01-y01"\n')
    config = load(write(mapped))
    assert config.warnings == []
    assert config.plot.data.map == {"d01-x01-y01": "/REF/ZEUS_2012_I1116258/d01-x01-y01"}


def test_scalar_energy_with_different_beams_warns(write):
    config = load(write(variant(("energies = [41, 5]", "energies = 28.6"))))
    assert any("CM frame" in warning for warning in config.warnings)


def test_scalar_energy_with_equal_beams_is_quiet(write):
    config = load(write(variant(("ids      = [2212, 11]", "ids      = [2212, 2212]"),
                                ("energies = [41, 5]", "energies = 13000"))))
    assert config.warnings == []


# ── arrays of tables ─────────────────────────────────────────────────────────

def test_module_sinks_are_checked(write):
    config = load(write(MINIMAL + '\n[[sinks.module]]\nname = "mymodule"\noptions = { window = 0.01 }\n'))
    assert config.module_sinks == [{"name": "mymodule", "options": {"window": 0.01}}]
    with pytest.raises(HepError, match="needs 'name'"):
        load(write(MINIMAL + '\n[[sinks.module]]\noptions = { window = 0.01 }\n'))
    with pytest.raises(HepError, match="unknown key 'nmae'"):
        load(write(MINIMAL + '\n[[sinks.module]]\nnmae = "mymodule"\n'))


def test_proc_fits_are_checked(write):
    text = MINIMAL + ('\n[[proc.fit]]\nname = "peak"\ntarget = "/m/x"\nmodel = "gauss"\n'
                      'range = [1.16, 1.08]\n')
    with pytest.raises(HepError, match=r"range must be \[low, high\]"):
        load(write(text))
    config = load(write(text.replace("[1.16, 1.08]", "[1.08, 1.16]")))
    assert config.proc_fits[0]["backend"] == "auto"       # default filled in


def test_proc_hist_bins(write):
    text = MINIMAL + ('\n[[proc.hist]]\nname = "jetpt"\nsource = "delphes.root"\n'
                      'expression = "Jet.PT"\nbins = [0, 0, 100]\n')
    with pytest.raises(HepError, match="n > 0 and low < high"):
        load(write(text))


# ── studies ──────────────────────────────────────────────────────────────────

def test_study_overrides_are_kept_for_later(write):
    text = MINIMAL + ('\n[study.quick]\ndescription = "fast"\nacross = ["pdf"]\n'
                      'pin = { pdf = "MSTW" }\n[study.quick.run]\nevents = 5000\n')
    study = load(write(text)).studies["quick"]
    assert study.description == "fast" and study.pin == {"pdf": "MSTW"}
    assert study.overrides == {("run", "events"): 5000}


def test_study_override_keys_are_validated(write):
    text = MINIMAL + '\n[study.quick]\nacross = ["pdf"]\n[study.quick.run]\nevnets = 5000\n'
    with pytest.raises(HepError, match="unknown key 'evnets'"):
        load(write(text))


def test_study_overlay_must_be_in_its_own_across(write):
    text = MINIMAL + '\n[study.quick]\nacross = []\noverlay = "pdf"\n'
    with pytest.raises(HepError, match="overlay 'pdf' is not in its own across"):
        load(write(text))


def test_study_pin_must_name_a_quantity(write):
    text = MINIMAL + '\n[study.quick]\nacross = []\npin = { pdfs = 1 }\n'
    with pytest.raises(HepError, match="undeclared quantity 'pdfs'"):
        load(write(text))


def test_settle_use_must_name_a_quantity(write):
    with pytest.raises(HepError, match="undeclared quantity 'pdfs'"):
        load(write(MINIMAL + '\n[settle.use]\npdfs = 1\n'))


# ── pieces ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("text", "seconds"), [("500ms", 0.5), ("30s", 30.0), ("5m", 300.0),
                                               ("1h", 3600.0), ("12", 12.0), (7, 7.0)])
def test_durations(text, seconds):
    assert parse_duration(text, "[terminal] stall_after") == seconds


@pytest.mark.parametrize("bad", ["soon", "5 m", "-3s", "", "5x"])
def test_bad_durations(bad):
    with pytest.raises(HepError):
        parse_duration(bad, "[terminal] stall_after")


def test_origin_scanner_finds_lines():
    text = ('schema = 2\n\n[run]\nname = "a"\n\n[[sinks.module]]\nname = "m"\n'
            '[[sinks.module]]\nname = "n"\n[quantity.pdf]\nvalues = [\n 1,\n 2,\n]\n')
    origins = ld.scan_origins(text, "f.toml")
    assert origins[("schema",)] == "f.toml:1"
    assert origins[("run", "name")] == "f.toml:4"
    assert origins[("sinks", "module", "1", "name")] == "f.toml:7"
    assert origins[("sinks", "module", "2", "name")] == "f.toml:9"
    assert origins[("quantity", "pdf", "values")] == "f.toml:11"


def test_list_length_is_checked():
    spec = Field("list", [], "two ids", item="int", minimum=2, maximum=2)
    assert check(spec, [1, 2], "[beams] ids") == [1, 2]
    with pytest.raises(HepError, match="needs at least 2 entries"):
        check(spec, [1], "[beams] ids")
    with pytest.raises(HepError, match="takes at most 2 entries"):
        check(spec, [1, 2, 3], "[beams] ids")
    with pytest.raises(HepError, match=r"\[beams\] ids\[2\]"):
        check(spec, [1, "two"], "[beams] ids")


def test_every_field_has_documentation():
    for name, section in sch.SECTIONS.items():
        for key, spec in section.fields.items():
            assert spec.doc, f"{name}.{key} has no doc"
            assert spec.describe()
        for sub in section.subsections.values():
            for key, spec in sub.fields.items():
                assert spec.doc, f"{sub.name}.{key} has no doc"


def test_every_documented_section_exists():
    # 03 §1 lists these tables; the loader must know them all
    for name in ("run", "generator", "beams", "rivet", "store", "delphes", "output", "plot",
                 "terminal", "quantity", "sweep", "settle", "study"):
        assert name in sch.SECTIONS
    assert sch.section_of(("sinks", "module", "1", "name"))[0] is sch.MODULE_SINK
    assert sch.section_of(("plot", "data", "file"))[0] is sch.PLOT_DATA
