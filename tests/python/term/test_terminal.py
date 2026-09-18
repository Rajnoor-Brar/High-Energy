"""The terminal: one view model, two renderers, and three commands over files (P3-S04).

The dashboard is checked by snapshot — the exact frame, rendered into a string — because the thing that
breaks a terminal view is a layout change nobody meant to make. The frames here are built from the same
kind of `status.jsonl` a real run writes, so the snapshots also pin the journal format.
"""

from __future__ import annotations

import json
import os
import pty
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

from hekit.run import journal
from hekit.term import model, theme
from hekit.term.dashboard import Dashboard, render_once
from hekit.term.plain import PlainRenderer, render_lines

#: A fixed clock, so every snapshot renders the same text on every machine.
T0 = 1_789_700_000.0


def a_run(*, finished: bool = False) -> model.RunView:
    """The run from 06 §1: four points, one done, one going, two queued."""
    view = model.RunView(command="hep run eic.toml --study pdf", project="PhotoProduction",
                         git="0a10209+dirty", started=T0)
    for name in ("eic_5x41_em_MSTW", "eic_5x41_em_NNLO", "eic_5x41_em_NNNLO", "eic_5x41_em_LHC21"):
        view.add_point(name)

    first = view.point("eic_5x41_em_MSTW")
    view.start_point(first, T0)
    first.events = 1_000_000
    first.xsec_pb, first.xsec_err_pb, first.xsec_final = 18320.0, 55.0, True
    view.finish_point(first, state=model.DONE, exit_code=0, when=T0 + 552)

    second = view.point("eic_5x41_em_NNLO")
    view.start_point(second, T0 + 552)
    view.feed({"k": "init", "threads": 20, "mode": "serial", "t": T0 + 553},
              point=second.name, stage="generate+rivet")
    view.feed({"k": "progress", "done": 642_113, "total": 1_000_000, "rate": 1180.4,
               "workers": [321_100, 321_013], "t": T0 + 1100}, point=second.name,
              stage="generate+rivet")
    view.feed({"k": "xsec", "value_pb": 17900.0, "err_pb": 60.0, "final": False, "t": T0 + 1100},
              point=second.name)
    for _ in range(2):
        view.feed({"k": "log", "level": "warn", "source": "pythia",
                   "msg": "SpaceShower::pT2nearThreshold: stuck in loop", "t": T0 + 660},
                  point=second.name)
    view.feed({"k": "log", "level": "warn", "source": "rivet",
               "msg": "photo_eic: jet outside |eta| acceptance after boost", "t": T0 + 1020},
              point=second.name)
    second.stages["generate+rivet"].started = T0 + 552
    if finished:
        view.finish_point(second, state=model.DONE, exit_code=0, when=T0 + 1300)
        view.finish(0, T0 + 1300)
    return view


@pytest.fixture
def frozen_clock(monkeypatch):
    """Freeze `time.time` so elapsed values are stable in snapshots."""
    monkeypatch.setattr(time, "time", lambda: T0 + 1122)
    return T0 + 1122


# ── the dashboard, by snapshot ───────────────────────────────────────────────

def test_the_dashboard_matches_06_section_1(frozen_clock):
    frame = render_once(a_run(), width=100)
    lines = [line.rstrip() for line in frame.splitlines()]

    assert lines[0] == "hep run eic.toml --study pdf  PhotoProduction · 0a10209+dirty"
    assert lines[1] == "  points █████░░░░░░░░░░░░░░░  1/4      elapsed 18m42s      eta ≈ 27m36s"
    # The name column is as wide as the longest name in the run, plus two spaces, so a long point
    # name never runs into its own numbers.
    assert lines[2] == ("  ✔ 1  eic_5x41_em_MSTW              1.00 M ev   "
                        "σ = 1.832e+04 pb ± 0.3 %   9m12s   0 warnings")
    assert lines[3] == "  ▶ 2  eic_5x41_em_NNLO"
    assert lines[4] == ("       generate+rivet  ██████████████░░░░░░░░  642 113 / 1 000 000  64 %  "
                        "1.18 k ev/s  eta 5m03s")
    assert lines[5] == "       σ(running) 1.790e+04 pb ± 0.3 % · warnings 3 (pythia 2 · rivet 1)"
    assert lines[6] == "  · 3  eic_5x41_em_NNNLO             queued"
    assert "log (curated)" in lines[8]
    assert "SpaceShower::pT2nearThreshold: stuck in loop" in lines[9] and lines[9].endswith("×2")
    assert lines[-1] == ("  Ctrl-C: stop at the next checkpoint (partial outputs kept) · "
                         "Ctrl-C ×2: abort")


def test_a_finished_run_ends_with_its_tally(frozen_clock):
    frame = render_once(a_run(finished=True), width=100)
    assert frame.splitlines()[-1].strip().startswith("2 done")


def test_a_failed_point_shows_its_exit_code(frozen_clock):
    view = a_run()
    point = view.point("eic_5x41_em_NNNLO")
    view.start_point(point, T0 + 900)
    view.finish_point(point, state=model.FAILED, exit_code=3, reason="Pythia failed to initialise",
                      when=T0 + 910)
    frame = render_once(view, width=100)
    assert "✖ 3  eic_5x41_em_NNNLO" in frame
    assert "exit 3 · Pythia failed to initialise" in frame


def test_a_skipped_point_says_why(frozen_clock):
    view = a_run()
    point = view.point("eic_5x41_em_LHC21")
    view.finish_point(point, state=model.SKIPPED, reason="name, hash and result all match",
                      when=T0 + 900)
    assert "↷ 4  eic_5x41_em_LHC21" in render_once(view, width=100)


def test_a_stage_with_no_event_count_shows_a_phase_and_elapsed(frozen_clock):
    """Prepare stages (integration, `Herwig read`) give no count; they must still show something."""
    view = model.RunView(started=T0)
    point = view.add_point("sherpa_point")
    view.start_point(point, T0)
    view.feed({"k": "phase", "phase": "integrating", "t": T0}, point=point.name, stage="prepare")
    point.stages["prepare"].started = T0
    frame = render_once(view, width=100)
    assert "prepare" in frame and "integrating" in frame and "18m42s" in frame


def test_the_curated_log_keeps_only_the_tail(frozen_clock):
    view = a_run()
    for index in range(20):
        view.feed({"k": "log", "level": "warn", "source": "pythia", "msg": f"warning {index}",
                   "t": T0 + 1000 + index}, point="eic_5x41_em_NNLO")
    view.log_tail = 3
    frame = render_once(view, width=110)
    assert "warning 19" in frame and "warning 15" not in frame


def test_info_messages_never_reach_the_curated_pane(frozen_clock):
    view = a_run()
    view.feed({"k": "log", "level": "info", "source": "rivet", "msg": "loaded photo_eic",
               "t": T0 + 900}, point="eic_5x41_em_NNLO")
    assert "loaded photo_eic" not in render_once(view, width=100)


# ── plain mode ───────────────────────────────────────────────────────────────

def test_plain_lines_stand_alone(frozen_clock):
    lines = render_lines(a_run(finished=True))
    assert lines[0].endswith("start  hep run eic.toml --study pdf · PhotoProduction · 0a10209+dirty")
    assert any("[2/4 eic_5x41_em_NNLO] generate+rivet  start (20 threads, serial)" in line
               for line in lines)
    assert any("642113/1000000  64 %  1.18 k ev/s  eta 5m03s" in line for line in lines)
    assert any("WARN pythia SpaceShower::pT2nearThreshold: stuck in loop  ×2" in line
               for line in lines)
    assert any("done" in line and "1.00 M ev" in line for line in lines)
    assert lines[-1].endswith("end    2 done  21m40s")
    for line in lines:
        assert line[2] == ":" and line[5] == ":", f"every line starts with a clock: {line!r}"


def test_a_progress_line_is_rate_limited_by_the_totals(frozen_clock):
    """The legacy bar-interval defect: the interval was fixed before the totals were known."""
    import io

    view = a_run()
    stream = io.StringIO()
    renderer = PlainRenderer(view=view, stream=stream, plain_every=30.0)
    point = view.point("eic_5x41_em_NNLO")
    renderer.progress(point, "generate+rivet")                    # the first one always prints
    renderer.progress(point, "generate+rivet")                    # too soon: dropped
    assert len(stream.getvalue().splitlines()) == 1

    # 1 000 000 events at 1180/s is about 14 minutes, so ~20 lines means one every ~42 s, clamped
    # to the 30 s ceiling.
    assert theme.progress_interval(1_000_000, 1180.4) == 30.0
    # A two-minute run gets a line every 6 s instead of one line in total.
    assert theme.progress_interval(10_000, 84.0) == pytest.approx(5.95, abs=0.01)
    # And nothing is known yet → the ceiling, never zero.
    assert theme.progress_interval(0, 0) == 30.0


def test_a_repeated_warning_is_printed_once_then_counted(frozen_clock):
    import io

    view = model.RunView(started=T0)
    point = view.add_point("p")
    view.start_point(point, T0)
    stream = io.StringIO()
    renderer = PlainRenderer(view=view, stream=stream)
    for _ in range(3):
        view.feed({"k": "log", "level": "warn", "source": "pythia", "msg": "stuck in loop",
                   "t": T0}, point="p")
        renderer.refresh()
    lines = [line for line in stream.getvalue().splitlines() if "stuck in loop" in line]
    assert len(lines) == 3 and lines[-1].endswith("×3"), lines


# ── the journal ──────────────────────────────────────────────────────────────

def test_a_journal_round_trips_through_the_view(tmp_path: Path):
    """What the supervisor writes is what `hep watch` reads: one format, two ends."""
    with journal.Journal(tmp_path) as book:
        book.header(cli="hep run eic.toml --study pdf", project="PhotoProduction", git="0a10209",
                    study="pdf", points=["a", "b"])
        book.point("a", model.RUNNING)
        book.raw('{"t": 1.0, "k": "init", "threads": 2, "mode": "serial", "sinks": ["rivet"]}',
                 point="a", stage="hep-run")
        book.raw('{"t": 2.0, "k": "progress", "done": 50, "total": 100, "rate": 25.0,'
                 ' "workers": [25, 25]}', point="a", stage="hep-run")
        book.raw('{"t": 2.5, "k": "log", "level": "warn", "source": "pythia", "msg": "hmm"}',
                 point="a")
        book.raw("this is not json at all", point="a")
        book.point("a", model.DONE, exit_code=0, outputs=["analysis.yoda"])
        book.done(0)

    assert (tmp_path / journal.NAME).is_file()
    view = model.from_journal(journal.read(tmp_path / journal.NAME))
    assert [point.name for point in view.points] == ["a", "b"]
    assert view.command == "hep run eic.toml --study pdf" and view.project == "PhotoProduction"
    first = view.point("a")
    assert first.state == model.DONE and first.outputs == ["analysis.yoda"]
    assert first.stages["hep-run"].done == 50 and first.stages["hep-run"].total == 100
    assert first.warnings == {"pythia": 1}
    assert view.finished and view.exit_code == 0


def test_an_unparseable_line_is_kept_verbatim(tmp_path: Path):
    """The one time a journal matters is when something went wrong; do not drop evidence."""
    with journal.Journal(tmp_path) as book:
        book.raw("Segmentation fault (core dumped)", point="a")
    payload = json.loads(journal.read(tmp_path / journal.NAME)[0])
    assert payload["k"] == "garbled" and payload["raw"] == "Segmentation fault (core dumped)"


def test_the_pid_file_says_whether_a_run_is_alive(tmp_path: Path):
    book = journal.Journal(tmp_path)
    assert journal.running_pid(tmp_path) == os.getpid()
    book.close()
    assert journal.running_pid(tmp_path) is None, "closing removes it"

    (tmp_path / journal.PID).write_text("999999999\n", encoding="utf-8")
    assert journal.running_pid(tmp_path) is None, "a stale pid is not a running run"


def test_a_journal_with_nowhere_to_write_is_not_an_error():
    book = journal.Journal(None)
    book.header(cli="hep run")
    book.point("a", model.RUNNING)
    book.close()                                    # nothing raised, nothing written


# ── the terminal is always given back ────────────────────────────────────────

def test_the_terminal_is_restored_after_an_exception_mid_render():
    """Verification row 'Terminal restored': a crash inside the Live block must not leave the user
    without a cursor or without echo."""
    script = (
        "import sys; sys.path.insert(0, %r)\n"
        "from hekit.term.dashboard import Dashboard\n"
        "from hekit.term.model import RunView\n"
        "view = RunView(command='hep run')\n"
        "view.add_point('p')\n"
        "try:\n"
        "    with Dashboard(view=view):\n"
        "        raise RuntimeError('boom')\n"
        "except RuntimeError:\n"
        "    pass\n"
    ) % str(Path(__file__).resolve().parents[3] / "utils" / "python")

    primary, secondary = pty.openpty()
    before = termios.tcgetattr(secondary)
    done = subprocess.run([sys.executable, "-c", script], stdin=secondary, stdout=secondary,
                          stderr=secondary, close_fds=True, timeout=120)
    output = b""
    os.close(secondary)
    while True:
        try:
            chunk = os.read(primary, 65536)
        except OSError:
            break
        if not chunk:
            break
        output += chunk
    after = termios.tcgetattr(primary)
    os.close(primary)

    assert done.returncode == 0
    text = output.decode("utf-8", errors="replace")
    assert "\x1b[?25h" in text, "the cursor is shown again"
    assert text.rindex("\x1b[?25h") > text.rindex("\x1b[?25l"), "and shown *after* it was hidden"
    assert after[3] & termios.ECHO, "echo is still on"


def test_stopping_twice_is_harmless():
    view = model.RunView()
    view.add_point("p")
    dashboard = Dashboard(view=view)
    dashboard.stop()
    dashboard.stop()


# ── a C locale must not kill a run's log ─────────────────────────────────────

def test_output_degrades_to_ascii_when_the_locale_cannot_hold_it(monkeypatch):
    """A batch job or a CI runner with LANG unset encodes stdout as ASCII, where a single "σ" raises
    UnicodeEncodeError. A progress bar must never be the reason a log dies."""
    import io

    class AsciiStream(io.StringIO):
        encoding = "ANSI_X3.4-1968"

    try:
        assert theme.autodetect(AsciiStream()) is True
        assert theme.sigma(18320.0, 55.0) == "sigma = 1.832e+04 pb +- 0.3 %"
        assert theme.glyph("done") == "ok" and theme.glyph("running") == ">"
        assert theme.bar(1, 2, 4) == "##.."
        assert theme.duration(None) == "-"
        line = theme.t("  points · eta ≈ 5m · ×2")
        line.encode("ascii")                              # the point: it encodes
        assert line == "  points - eta ~ 5m - x2"
    finally:
        theme.set_ascii(False)

    assert theme.autodetect(io.StringIO()) is False, "a stream with no encoding is assumed UTF-8"


def test_plain_lines_survive_an_ascii_stream():
    import io

    class AsciiStream(io.StringIO):
        encoding = "ascii"

        def write(self, text):                            # what a real ASCII stream would do
            text.encode("ascii")
            return super().write(text)

    view = a_run(finished=True)
    stream = AsciiStream()
    theme.autodetect(stream)
    try:
        renderer = PlainRenderer(view=view, stream=stream)
        renderer.run_started()
        for point in view.points:
            if point.state != model.QUEUED:
                renderer.point_finished(point)
        assert "sigma = " in stream.getvalue()
    finally:
        theme.set_ascii(False)


# ── numbers read the way 06 writes them ──────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (None, "—"), (0, "0"), (999, "999"), (1_000, "1.00 k"), (642_113, "642.11 k"),
    (1_000_000, "1.00 M"), (2_500_000_000, "2.50 G")])
def test_counts(value, expected):
    assert theme.count(value) == expected


@pytest.mark.parametrize("value,expected", [
    (None, "—"), (0, "0s"), (9, "9s"), (552, "9m12s"), (3600, "1h00m"), (3720, "1h02m"),
    (float("nan"), "—"), (float("inf"), "—"), (-1, "—")])
def test_durations(value, expected):
    assert theme.duration(value) == expected


def test_sigma_reads_as_a_relative_error():
    assert theme.sigma(18320.0, 55.0) == "σ = 1.832e+04 pb ± 0.3 %"
    assert theme.sigma(18320.0, 55.0, running=True).startswith("σ(running) ")
    assert theme.sigma(12.5, None) == "σ = 12.5 pb"
    assert theme.sigma(None) == "—"


def test_eta_says_nothing_rather_than_something_wrong():
    assert theme.eta(10, 100, 0) is None, "no rate yet"
    assert theme.eta(10, 0, 5) is None, "no total yet"
    assert theme.eta(100, 100, 5) == 0.0
    assert theme.eta(50, 100, 5) == 10.0
