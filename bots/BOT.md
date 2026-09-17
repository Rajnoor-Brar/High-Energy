# Bot Instructions

## Plan Approval

- During planning, do not solicit go-ahead or ask to proceed; transition to
  implementation only when the user explicitly triggers it (e.g. "Implement the plan").
- Save the plan progressively to `bots/current_plan.md` during planning, to
  avoid loss on context reset.
- Future roadmaps and intent notes go in `bots/intent.md`.
- Run `/compact` after a major implementation triggered by "Implement the plan".

## Context

### Directory Layout

| Path         | Purpose                                                                      |
| ------------ | ---------------------------------------------------------------------------- |
| `aux/`       | VSCode extensions and tooling for HEP UX                                     |
| `bots/`      | Bot configuration, plans (`current_plan.md`, `intent.md`), and `lessons.md`   |
| `configs/`   | User configs per project (`configs/<Project>/`)                              |
| `datasets/`  | Third-party datasets downloaded from the internet                            |
| `docs/`      | Documentation; `docs/rework/` holds the active design and step plan          |
| `env/`       | Versioned shell environment (`hep_env.sh`), sourced by the `~/HEP` stub      |
| `legacy/`    | Frozen pre-rework code, tests, configs and docs — never included from outside |
| `output/`    | Build artefacts and scratch (`output/scratch/` for tests and dry runs)       |
| `results/`   | Presentable outputs (YODA, images, HTML pages)                               |
| `sources/`   | Driver and Rivet-analysis sources per project (`sources/<Project>/`)         |
| `tests/`     | Tests; `tests/golden/` holds the legacy golden fixtures                      |
| `tools/`     | Versioned legacy tools (`rivpyth`, `ydplt`, `ydmrg`), retired in P4-S06      |
| `utils/`     | Core logic not tied to a specific project (being rebuilt by the rework)      |

- For any module or utility `Foo`, its submodules reside in `Foo/`.
- `legacy/` is reference only: copy or adapt from it, never `#include` or import it
  (see `legacy/PORTING.md`).
- `BOT.md` contains directives for bots and agents (BOTs).
- Additional rules given explicitly by the user may be appended to their dedicated file.
- Bots may record frequent issues, pitfalls, and observed code style conventions
  in `bots/lessons.md`. This file is consulted at lower priority than explicit
  instructions in `BOT.md` or user messages, only when context is otherwise
  insufficient.

## Code Design

Modules and utils are collectively called **Namespaces**. Each has a corresponding
submodule directory (e.g. `Foo/` for namespace `Foo`).

- `Namespace.hh` exposes only the primary functions that define the namespace's mission.
- Supporting logic is distributed to submodules, for example:
  - **Types** — type definitions
  - **Type Methods** — member/free functions on those types
  - **Type Interfacing** — initialisation, import/export
  - **Workers** — task-specific logic
  - **Helpers** — internal utilities
- Submodules should preferably:
  - build linearly on each other (minimise circular dependencies)
  - be self-sufficient with minimal includes, even of sibling submodules
  - expose a minimal interface to other namespaces — typically `Types.hh` is
    sufficient for cross-namespace communication
  - avoid sub-namespacing unless it meaningfully improves readability

## Testing

- Tests and dry runs never write into `results/` or `configs/`. Use the scratch root
  `output/scratch/` (gitignored), or `HEKIT_RESULTS` once the new stack exists.
  The legacy tools resolve paths relative to the CWD, so run them from a scratch CWD with
  symlinks for `configs`, `output`, `datasets` and `sources` and its own `results/`
  (see `output/scratch/legacy/`, built by `tests/golden/capture_legacy.py`).
- Golden fixtures of the legacy tools live in `tests/golden/` and are captured from frozen
  config copies in `tests/golden/inputs/`; recapture deliberately, and record every expected
  difference in `tests/golden/legacy_plan/EXPECTED_DELTAS.md`.
- If a test run is interrupted or fails, do not restore paths automatically —
  report the state to the user and wait for instruction.
- Do not modify source or output paths permanently without user confirmation.
- Never rely on the locale default encoding: reading a YODA file resets `LC_ALL` to `C`
  (00/B29), so name `encoding="utf-8"` on every text read and write.
