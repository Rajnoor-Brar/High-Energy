# P3-S02 — Process supervisor, FIFO transport and stall detection

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P3 — Supervision, results layout, terminal |
| Depends on | [P2-S03](P2-S03_core-status.md) |
| Blocks | [P3-S04](P3-S04_terminal.md), [P3-S05](P3-S05_hep-run-command.md) |
| Effort | 1 d |
| Findings / decisions | 00/B19, B20; F4; 06 §4 |
| Updated | 2026-09-18 |

## Goal

`hekit.run` spawns stages as data, wires FIFOs in a per-run private directory, polls all stages, escalates signals, attributes the first real failure, detects stalls, and always cleans up.

## Context

- 06 §3.3 exit codes, §4 supervision.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `tools/rivpyth` `supervise`, `terminate`, `run_with_fifo` (117–222) | control flow | port + fix B20 |
| `legacy/utils/Monitor/Threading.hh:97-116` | stall predicates (monotonic idle ≥ threshold; fatal at ×N) | port |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `hekit/run/{supervisor,transport,signals,parsers}.py`
- per-stage log files; `pass_fds` for status
- SIGINT → grace → SIGTERM → SIGKILL
- stall: no status and no log growth for `stall_after`

**Out (non-goals)**

- Rendering (S04)

## Design notes

- Fake stages for tests are small Python scripts under `tests/python/run/fakes/`.

## Tasks

- [x] Implement
- [x] Fake-stage test suite (each test ≤ 10 s)

## Outputs

- `utils/python/hekit/run/*`
- `tests/python/run/*`

## Verification

| Check | Command | Expected |
|---|---|---|
| Early exit | pytest fake: generator exits 1 before opening FIFO | reader stopped; exit 1 attributed |
| Hang | pytest fake: silent hang | exit 7 after stall_kill |
| Flood | pytest fake: 1 GB stderr | bounded memory; log file only |
| Ignores SIGINT | pytest fake | SIGTERM after grace |
| Reader dies | pytest fake | exit 4 |
| Cleanup | all tests | FIFO dir removed |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — implemented `hekit/run/{signals,transport,parsers,supervisor}.py` (≈700 lines) with
  seven fake stages under `tests/python/run/fakes/` and 27 tests (11.6 s, slowest single test 4.65 s).

  **Verification, every row measured**

  | Row | Result |
  |---|---|
  | Early exit (generator exits 1 before opening the FIFO) | exit 1 attributed to the generator; the reader, still blocked in `open()`, is stopped; under 10 s where the old `supervise` would have waited for ever |
  | Hang (silent) | `stall_after` marks it stalled, `stall_kill` stops it, **exit 7** |
  | Flood (1 GiB to stderr) | 1 073 741 824 bytes in the log file, **RSS +0 MiB** (limit in the test: 64 MiB) |
  | Ignores SIGINT | SIGINT → grace → **SIGTERM**, and SIGKILL never sent; a stage that also ignores SIGTERM gets SIGKILL |
  | Reader dies | **exit 4** — the writer's SIGPIPE is not reported as the cause, but the data path breaking is (06 §3.3) |
  | Cleanup | the private FIFO directory is gone after every test, including the failing ones |

  **Design notes worth keeping**

  1. **Attribution is ranked, not first-come** (00/B20): a status we caused carries no information; a
     real exit code beats a signal death; consumers are considered before producers because a consumer
     that exits early is what closes the pipe on the producer. `test_a_readers_own_error_wins_over_the_writers_sigpipe`
     is the case the old tool got wrong.
  2. **"Reader dies → exit 4" needed a reading.** A dead consumer is a *sink* crash by role, which
     would be 5. 06 §3.3 defines code 4 as "source I/O (**FIFO closed early**)", which is exactly this
     situation seen from the writer's side, so the exit code follows the doc — and the attribution
     message still names the crash (`rivet was killed by SIGSEGV, so generator wrote into a closed
     pipe`), because that is the part a user must act on.
  3. **Memory is bounded by construction, not by a limit.** Output is moved into the log file in 64 KiB
     chunks and only the last line is kept; a gigabyte of stderr costs a gigabyte of disk and nothing
     measurable in RSS.
  4. **The status descriptor number cannot be agreed in advance.** `pass_fds` keeps whatever number the
     pipe got, so the supervisor allocates it and calls `on_status_fd(stage, fd)` before spawning;
     P3-S05 uses that hook to write `[status].fd` into the spec. This replaces the "fd 3 by
     convention" assumption noted in P2-S03's test.
  5. **Every stage gets its own session** (`start_new_session=True`), so one signal reaches a tool's
     own children and a Ctrl-C in the user's terminal does not race the supervisor to them.
  6. Stall detection counts **status messages as activity**, not just log growth: `hep-run` in a quiet
     phase is working, and a chatty tool that stopped reporting may not be.

  **Deviations**

  1. The stall decision is remembered at the moment it is acted on. The first implementation asked "is
     anything idle now?" *after* stopping the stages, when nothing is running and therefore nothing is
     idle — a stalled run was reported as merely stopped. Caught by the fake-stage test.
  2. The fake generator sets `SIGPIPE` back to `SIG_DFL`. Python ignores SIGPIPE and raises
     `BrokenPipeError` instead, so the first version of the fake exited 1 and hid the very case the
     test exists for — the fakes have to die the way Pythia and Rivet die.
  3. `parsers.py` ships 06 §4's regex table for Sherpa, Whizard, Herwig, MadGraph and Delphes, but the
     doc says to calibrate them against real logs; that happens in each generator's own step (P7-S03…
     S06). Until then the fallback (spinner, elapsed time, last log line) is what those tools get, and
     a parser that stops matching costs a progress bar and never a result.
  4. `hep run`'s own Ctrl-C handling (first → SIGINT, second → SIGTERM, third → SIGKILL from the
     *user's* keyboard) belongs to the command in P3-S05; this module implements the escalation policy
     and the stopping, not the key handling.
