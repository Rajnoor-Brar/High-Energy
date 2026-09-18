# P3-S04 — Live dashboard, plain mode and watch/runs/show

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P3-S02](P3-S02_supervisor.md) |
| Blocks | [P3-S05](P3-S05_hep-run-command.md) |
| Effort | 1 d |
| Findings / decisions | R5; F12; utils defect: progress interval before totals |
| Updated | 2026-09-18 |

## Goal

A `rich` inline dashboard and a plain line mode render any status stream; `hep watch`, `hep runs`, `hep show` work from files.

## Context

- 06 §1–2, §5–6.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Monitor/Methods.hh:17-26` | ETA extrapolation | idea |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/term/{dashboard,plain,theme}.py`
- `status.jsonl` writer (supervisor side)
- `hep watch/runs/show`
- curated log pane with dedupe counts

**Out (non-goals)**

- Event tables (P5-S03)

## Design notes

- Progress interval computed from totals after the `init` message (fixes the legacy bar-interval defect).

## Tasks

- [x] Implement
- [x] Snapshot tests

## Outputs

- `utils/python/hekit/term/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Snapshots | pytest `Console(record=True)` on recorded `status.jsonl` | stable output |
| Plain on pipe | `hep watch latest \| cat` | plain lines |
| Terminal restored | pty test with an exception mid-render | cursor/echo restored |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/term/{theme,model,plain,dashboard,cli}.py`,
  `hekit/run/journal.py` and `hekit/results/cli.py` (≈1060 lines) with 52 tests (0.6 s).
  Suite: 484 Python, 11/11 ctest.

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Snapshots | the frame is asserted line by line against the mock-up in 06 §1 — header, points bar, the ✔/▶/·/✖/↷ rows, the stage bar (`642 113 / 1 000 000  64 %  1.18 k ev/s  eta 5m03s`), the running σ, the curated log with `×2`, and the footer |
  | Plain on pipe | `hep watch <dir>` through a **real** subprocess pipe: no bars, no escapes, one clock-stamped line per event of interest |
  | Terminal restored | a pty test raising inside the `Live` block: `\x1b[?25h` is emitted after the last `\x1b[?25l`, and `termios` still has `ECHO` set |

  **Shape**

  - **One view model** (`term/model.py`) feeds all three renderers. `hep watch` is not a second
    implementation of the dashboard: it rebuilds the same `RunView` from `status.jsonl` and draws it
    with the same code, which is what makes "watch it from another terminal" free.
  - **`hekit/run/journal.py`** writes that file (and `run.pid`) on the supervisor's side: the status
    protocol of 06 §3.2 with `point` and `stage` added, plus `run`, `point` and `done` records. A line
    that cannot be parsed is kept verbatim as `k: "garbled"` — the one time a journal matters is when
    something went wrong, so evidence is not dropped.
  - **`hep runs`** lists live runs (by a pid that is actually alive), studies with their serials and
    labels, and points with σ and wall time; `--json` for scripts. **`hep show`** explains one point
    from its own files, including the Pythia settings **parsed from the log** rather than copied into
    provenance, so the two cannot disagree (06 §5).

  **Deviations and notes**

  1. **The progress interval is computed from the totals** (`theme.progress_interval`), which is the
     legacy defect this step names: `Monitor` fixed its interval before it knew the run length, so a
     short run printed one line and a long one printed thousands. Now: about 20 lines over the run,
     floored at 1 s and capped at `plain_every` (30 s). A 1 M-event run at 1.18 k ev/s gets the 30 s
     cap; a 10 k-event run at 84 ev/s gets a line every 6 s.
  2. **`term/model.py` is an addition** to the step's `{dashboard,plain,theme}.py`. Two renderers plus
     `hep watch` need one state machine; putting it in `dashboard.py` would have made the plain
     renderer import the dashboard.
  3. **A C locale must not kill a log.** The first ctest run failed with
     `decoding with 'ANSI_X3.4-1968' codec failed`: ctest runs without `LANG`, and a single `σ` is
     enough. `theme.autodetect(stream)` now asks the stream what it can encode and degrades the whole
     vocabulary to ASCII (`σ` → `sigma`, `±` → `+-`, `█` → `#`, `✔` → `ok`) when it cannot. Python's
     own PEP 538 coercion usually prevents this, but `PYTHONIOENCODING=ascii` or a coercion-disabled
     environment does not.
  4. The dashboard renders **inline** (`transient=False`, no alternate screen), so the final frame
     stays in the scrollback — the reason 06 §1 rejected a full TUI.
  5. A message that is not about a process no longer conjures a stage row: an `xsec` or a `log` with no
     stage named used to create an empty `hep-run` line on screen.
  6. `hep events` is declared in `term/cli.py` as a placeholder pointing at P5-S03, so the command tree
     stays honest.
