# P2-S03 — Core and Status namespaces

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P2 — C++ core, CMake, hep-run v1 |
| Depends on | [P2-S01](P2-S01_cmake-skeleton.md), [P1-S01](P1-S01_package-skeleton.md) |
| Blocks | [P2-S04](P2-S04_source-run-loop.md), [P3-S02](P3-S02_supervisor.md), [P8-S02](P8-S02_phys.md) |
| Effort | 1 d |
| Findings / decisions | F4; 06 §3; legacy utils reuse |
| Updated | 2026-09-18 |

## Goal

`Core` (spec reader, errors/exit codes, signals, clocks, sha256, paths, provenance record) and `Status` (fd-3 JSON lines, heartbeat, plain fallback) exist with tests; a minimal Python status reader round-trips.

## Context

- 13 §2; 06 §3.1–3.3; house style (facade + submodules).
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Utility/Sha256.hh` + FIPS vectors `legacy/tests/test_utils_hardening.cc` (~129–153) | code + vectors | copy; add regular-file check |
| `legacy/utils/Utility/Signals.hh:22-57` | stop flag | adapt to `sigaction`, second signal escalates |
| `legacy/utils/Utility/{Time,Paths}.hh` | clock aliases, root discovery | adapt |
| `legacy/utils/Monitor/Threading.hh:121-136,212-213,256-265`, `Monitor/Timer.hh` | deadline loop, coalescing, timers | adapt/copy |
| `legacy/utils/Record/Meta.hh:25-110,243-299` | provenance fields | idea |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `utils/Core.hh` + `Core/{Types,Spec,Errors,Signals,Clock,Sha256,Paths,Provenance}.hh`
- `utils/Status.hh` (with `#ifdef Status` guard) + `Status/{Types,Writer,Heartbeat,Plain,Timer}.hh`
- `hekit/run/status.py` reader
- ctest + pytest

**Out (non-goals)**

- Source/Analyzer/Run (S04+)

## Design notes

- Spec: structural validation only, against `spec_v2.json` field list.
- Status writer: atomic counters read by a heartbeat thread; the event loop never formats JSON.

## Tasks

- [x] Implement Core
- [x] Implement Status
- [x] Python reader
- [x] Tests

## Outputs

- `utils/Core*`, `utils/Status*`
- `tests/cpp/{core_*,status_*}`
- `utils/python/hekit/run/status.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Spec errors | `ctest -R core_spec` | missing key → exit 1 with key name |
| SHA-256 | `ctest -R core_sha256` | FIPS vectors pass |
| Signals | `ctest -R core_signals` | first SIGINT sets flag; second escalates |
| Round trip | `ctest -R status_roundtrip` (+ pytest reader) | all kinds parsed; unknown kinds ignored |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-18 — **done.** 1299 lines of header-only C++ across the two namespaces.
  - **`Core`** (`utils/Core.hh` + 8 submodules):
    - `Errors` — the exit codes of 06 §3.3 as an enum with names, and one `Core::Error` carrying code,
      message and hint, so `main` never has to guess a code from a message.
    - `Sha256` — ported from `legacy/utils/Utility/Sha256.hh` with two changes: `sha256File` refuses
      anything that is not a regular file (a directory used to hash as `""`, a FIFO would block), and
      **finalising is now idempotent**. The legacy version documented "reset() before reuse", which
      held until a test macro evaluated its argument twice — which happened here, so the rule became a
      cached digest instead of a comment.
    - `Clock` — `Wall` for timestamps and `Steady` for durations, kept separate on purpose; plus
      `durationText` and an ISO-8601 UTC stamp.
    - `Signals` — `sigaction` with `SA_RESTART` (the legacy code used `std::signal`), a sticky atomic
      flag, and the second signal restoring the default so an impatient Ctrl-C still kills the process.
    - `Paths` — the same root-finding rule as `hekit.env.paths`, so both halves agree (00/B18).
    - `Spec` — the resolved-spec reader (toml++), **structure only**. It enforces the two invariants
      `hep-run` refuses to trust: the seed-list length must equal the thread count (P2-S02 found Pythia
      indexes it unchecked) and every seed must be inside 1…900000000, plus the point seed being the
      base of its block.
    - `Provenance`, `Types` — the build description, host, run record, and the `Beams`/`Counts` types
      other namespaces need (`Counts` separates attempted from accepted, per P0-S04).
  - **`Status`** (`utils/Status.hh` + 5 submodules):
    - `Writer` — JSON lines on fd 3, plain lines on stderr when fd 3 is not open. fd 3 is set
      **non-blocking** and a short write counts as dropped: status is disposable, events are not. The
      JSON is hand-written (nine message shapes, nothing harder to escape than a tool's warning).
    - `Heartbeat` — one thread, deadlines **advanced past now in a loop** so a stall cannot produce a
      burst of catch-up messages, and a `wait_until` with a predicate so a stop is immediate rather
      than "after the next tick" (both ideas from `legacy/utils/Monitor/Threading.hh:121-136,212-213`).
      The event loop only calls `update()`, which stores two atomics.
    - `Plain`, `Types`, `Timer` (scope timers ported from `Monitor/Timer.hh`).
    - **The X11 guard** is a `#error` naming `Xlib.h`'s `#define Status int` and what to do about it,
      rather than a cascade of unrelated errors (13 §3). Verified by compiling a file that defines
      `Status` first.
  - **`hekit.run.status`** reads the stream: an unknown message kind is **kept and flagged** (a newer
    `hep-run` can talk to an older `hep`), while a line that is not JSON is reported as garbled rather
    than dropped. `StatusReader` folds a run into the state a dashboard needs (P3-S04).
  - **Verification:**
    | Check | Result |
    |---|---|
    | `core_sha256` | FIPS 180-4 vectors (empty, "abc", the 56-byte example, 55/56/64-byte padding edges, 10⁶ 'a'), incremental == single, idempotent digest, file and non-file behaviour — 18 checks |
    | `core_spec` | a good spec parses; 15 rejections including both seed-length mismatches, out-of-range seeds, a point seed that is not its block base, wrong types, missing tables, a non-sha256 hash, and `threads = 0` with no seed list |
    | `core_signals` | SIGINT and SIGTERM request a stop without killing the process; the flag is sticky; exit codes and the hint text |
    | `status_roundtrip` | structured and plain modes, escaping, rate limiting, the plain progress line, heartbeat start/stop under 1 s and idempotent, scope timers |
    | Cross-language | the C++ writer emits one message of every kind on fd 3 and the Python reader parses all nine, including a message containing a quote, a backslash and a newline |
    | Suite | `ctest` 8 tests (7 cxx + Python) green; `pytest` **334 passed** |
  - **Deviation:** the step listed `Status/{Types,Writer,Heartbeat,Plain}`; `Timer` is included too (it
    was in the porting map), and the Python reader lives at `hekit/run/status.py` as planned.
