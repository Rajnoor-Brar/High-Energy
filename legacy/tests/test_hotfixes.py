"""Regression tests for the P0-S05 hotfixes to the legacy tools — **frozen with them (P4-S06)**.

These guard `rivpyth`, `ydplt` and `ydmrg`, which were retired once `hep run` and `hep plot` were shown
to reproduce them (P2-S06, P4-S02, P4-S06). They are kept here, beside the tools, so the hotfixes are
still checkable if anyone ever revives one; they are **not** part of the suite, because nothing in the
toolkit runs those tools any more, and `tests/` may not import from `legacy/`.

To run them by hand:

    python -m pytest legacy/tests/test_hotfixes.py

The behaviours that still matter to the new toolchain are tested there instead: the partial-output
naming in `tests/python/run/test_rivet_sink.py`, the locale restore in
`tests/python/results/test_layout_skip_provenance.py`, and the exit codes in
`tests/python/run/test_hep_run.py`.

Each test names the finding it guards. The long-running checks (kill, bogus analysis, unwritable
output) are recorded in the P0-S05 Log.
"""

import importlib.util
import locale
import subprocess
import sys
import types
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "tests" / "golden"))     # capture_legacy.py, the fixture recorder
sys.path.insert(0, str(_REPO / "legacy" / "tools"))     # the tools these hotfixes are for

import capture_legacy as cl                 # noqa: E402
import rivpyth_common as rc                 # noqa: E402

GENERATOR = cl.REPO / "output" / "PhotoProduction" / "generator.exe"


def load_rivpyth() -> types.ModuleType:
    """Import legacy/tools/rivpyth (no .py suffix) as a module."""
    spec = importlib.util.spec_from_loader(
        "rivpyth_tool", importlib.machinery.SourceFileLoader("rivpyth_tool", str(_REPO / "legacy" / "tools" / "rivpyth")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rivpyth = load_rivpyth()


def config_with(tmp_path: Path, *replacements: tuple[str, str]) -> Path:
    """A copy of the frozen eic.toml with literal (old, new) substitutions."""
    text = (cl.INPUTS / cl.PROJECT / "eic.toml").read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in text, old
        text = text.replace(old, new)
    path = tmp_path / "variant.toml"
    path.write_text(text, encoding="utf-8")
    return path


# ── 00/B2: seeds must be at least `threads` apart ────────────────────────────

def test_seed_step_below_threads_is_rejected(tmp_path):
    path = config_with(tmp_path, ("seed_step    = 20", "seed_step    = 1"))
    with pytest.raises(rc.ConfigError, match="seed_step = 1 is smaller than"):
        rc.read_config(path)


def test_seed_step_equal_to_threads_is_accepted(tmp_path):
    config = rc.read_config(config_with(tmp_path, ("seed_step    = 20", "seed_step    = 20")))
    assert config["sweep"].seed_step == 20


def test_single_thread_needs_no_seed_step(tmp_path):
    config = rc.read_config(config_with(tmp_path, ("seed_step    = 20", "seed_step    = 1"),
                                        ("threads    = 20", "threads    = 1")))
    assert config["sweep"].seed_step == 1


def test_shipped_configs_keep_seeds_apart():
    for name in ("eic", "zeus_validation"):
        config = rc.read_config(cl.REPO / "configs" / cl.PROJECT / f"{name}.toml")
        assert config["sweep"].seed_step >= config["threads"]


def test_point_seeds_step_by_seed_step():
    seeds = []
    for point in cl.expand_case("eic", {"study": "pdf"})["points"]:
        seeds += [value for key, value, _ in point["settings"] if key == "Random:seed"]
    assert seeds == ["270403", "270423", "270443", "270463"]


# ── 00/B3: a partial result never takes the final name ───────────────────────

def test_rivet_writes_a_partial_name():
    plan = {"generator": "g", "hepmc_file": "f", "base_cmnd": "b", "point_cmnd": "p",
            "yoda_file": "results/PhotoProduction/03_eic.yoda", "analysis": "photo_eic"}
    _, rivet = rivpyth.commands({}, plan)
    assert rivet[rivet.index("-o") + 1] == "results/PhotoProduction/03_eic.part.yoda"
    # YODA picks its format from the extension and rejects "<name>.yoda.part"
    assert rivet[rivet.index("-o") + 1].endswith(".yoda")


def test_partial_is_promoted_only_when_counts_agree(tmp_path):
    yoda = pytest.importorskip("yoda")
    final = tmp_path / "point.yoda"
    counter = yoda.Counter("/RAW/_EVTCOUNT")
    for _ in range(7):
        counter.fill()
    yoda.write([counter], rivpyth.partial_output(str(final)))
    plan = {"yoda_file": str(final)}

    short = types.SimpleNamespace(written=9)
    assert rivpyth.finish_output(plan, short) == 5
    assert not final.exists(), "a short result must keep the .part name"

    exact = types.SimpleNamespace(written=7)
    assert rivpyth.finish_output(plan, exact) == 0
    assert final.is_file() and not Path(rivpyth.partial_output(str(final))).exists()


def test_missing_output_is_an_error(tmp_path):
    assert rivpyth.finish_output({"yoda_file": str(tmp_path / "nothing.yoda")},
                                 types.SimpleNamespace(written=10)) == 5


def test_skip_existing_ignores_a_partial_file(tmp_path):
    final = tmp_path / "point.yoda"
    Path(rivpyth.partial_output(str(final))).write_text("partial", encoding="utf-8")
    assert not final.is_file(), "skip_existing tests the final name, which a partial run never creates"


# ── 00/B20: report the real failure, not the knock-on one ────────────────────

@pytest.mark.parametrize(("generator_status", "rivet_status", "expected"), [
    (-13, 1, ("rivet", 1)),        # rivet died first; the generator hit a closed pipe
    (-15, 1, ("rivet", 1)),        # rivet failed; we terminated the generator
    (1, -15, ("generator", 1)),    # the generator failed; we terminated rivet
    (1, 2, ("rivet", 2)),          # both real: rivet is reported, both statuses are printed
    (0, 0, ("", 0)),
    (-15, 0, ("generator", -15)),  # nothing real: the signal is still reported
])
def test_failure_attribution(generator_status, rivet_status, expected):
    assert rivpyth.first_failure(generator_status, rivet_status) == expected


# ── 00/B21: the generator fails loudly on an unwritable output ───────────────

@pytest.mark.skipif(not GENERATOR.is_file(), reason="generator.exe is not built")
def test_generator_rejects_an_unwritable_output(tmp_path):
    card = tmp_path / "quick.cmnd"
    card.write_text("Main:numberOfEvents = 1\nParallelism:numThreads = 1\nRandom:setSeed = on\n"
                    "Random:seed = 4242\nPartonLevel:MPI = off\nInit:showChangedSettings = off\n"
                    "Init:showMultipartonInteractions = off\nNext:numberShowInfo = 0\n"
                    "Next:numberShowProcess = 0\nNext:numberShowEvent = 0\n", encoding="utf-8")
    result = subprocess.run([str(GENERATOR), "/proc/forbidden/events.hepmc",
                             str(cl.INPUTS / cl.PROJECT / "photo_ep.cmnd"), str(card)],
                            capture_output=True, text=True, timeout=900)
    assert result.returncode == 4
    assert "could not open HepMC3 output" in result.stderr


# ── 00/B29: YODA's reader resets the locale ──────────────────────────────────

def test_reading_yoda_keeps_the_locale(tmp_path):
    pytest.importorskip("yoda")
    before = locale.setlocale(locale.LC_ALL)
    rivpyth.analysed_events(cl.RUN_DIR / "mini_27x920_ep_MSTW.yoda")
    assert locale.setlocale(locale.LC_ALL) == before
    # the point cmnd header is not ASCII, so a clobbered locale would break the next point
    (tmp_path / "cmnd").mkdir()
    plan = {"base_cmnd": str(cl.INPUTS / cl.PROJECT / "photo_ep.cmnd"),
            "point_cmnd": str(tmp_path / "cmnd" / "p.cmnd")}
    config = rc.read_config(cl.INPUTS / cl.PROJECT / "eic.toml")
    rc.apply_overrides(config, None, None)
    rc.write_point_cmnd(config, plan, rc.expand_points(config)[0])
    assert "—" in Path(plan["point_cmnd"]).read_text(encoding="utf-8")


def test_analysed_events_reads_the_raw_counter():
    pytest.importorskip("yoda")
    assert rivpyth.analysed_events(cl.RUN_DIR / "mini_27x920_ep_NNLO.yoda") == 4999


def test_analysed_events_survives_an_unreadable_file(tmp_path, capsys):
    broken = tmp_path / "broken.yoda"
    broken.write_text("not a yoda file", encoding="utf-8")
    assert rivpyth.analysed_events(broken) is None
