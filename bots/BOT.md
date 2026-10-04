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

The layout is described in [docs/06_Internals.md §1](../docs/06_Internals.md#1-repository-layout); the manual's index is [docs/README.md](../docs/README.md).

| Path         | Purpose                                                                      |
| ------------ | ---------------------------------------------------------------------------- |
| `aux/`       | VSCode extensions and tooling for HEP UX (not framework)                     |
| `bots/`      | Bot configuration and plans (`current_plan.md`)                              |
| `build/`     | Everything compiled (`make`/`hep build`); `build/Rivet/` holds the Rivet plugins |
| `configs/`   | Run TOMLs and native cards per project (`configs/<Project>/`)                |
| `datasets/`  | Your own reference data (YODA), gitignored; Rivet's are `rivet:<Analysis>` in `[plot.data]` |
| `docs/`      | the manual: `01_Overview` … `07_Record` (the record holds the decisions, the ledger and the findings the code cites) |
| `modules/`   | Project sources: `<Name>.cc` programs, headers, Rivet plugins in `Rivet/` or `Rivet_*.cc`; `_`-prefixed folders are parked (not built) |
| `output/`    | Technical files per project (cards, logs, FIFOs, status), and `output/tests/` for tests |
| `results/`   | Products per project (YODA, ROOT, plots, provenance)                         |
| `tests/`     | `runner/`, `cxx/`, `integration/`, `fixtures/configs/` (frozen configs the tests load) and `reference/` (data the gates compare against) |
| `utils/`     | `Status.hh`, `Module.hh`, `App_*.cc`, `Apps/<Name>/`, and `Env/` (shell, the Python runner, tool folders) |

- v1 is at the git tag `rework/v1-final`: consult it with `git show rework/v1-final:<path>`,
  and never restore it wholesale.
- `BOT.md` contains directives for bots and agents (BOTs).
- Additional rules given explicitly by the user may be appended to their dedicated file.

## Code Design

- C++ in `utils/` is a few headers and apps. There are no library namespaces: rework v2 decision V7.
  A header holds one PascalCase namespace, checked against the installed toolchain (X11 defines
  `Status`), with `camelCase` functions and no `using namespace` of external libraries at
  namespace scope.
- A source declares what it links in a `// requires: …` line near the top.
- The Python runner is one flat package, `utils/Env/runner/`. A module imports only from lower
  ranks (docs/06_Internals.md §2.1), and `tests/runner/test_imports.py` enforces it.
- Everything the runner knows about a tool lives in `utils/Env/<tool>/`. The runner core never
  names a tool.
- Before writing code for a tool, read its rows in the knowledge ledger
  (docs/07_Record.md §3).

## Testing

- Tests and dry runs never write into `results/` or `configs/`. Use `output/tests/`, with
  `HEKIT_RESULTS`/`HEKIT_OUTPUT` pointing there.
- The gates compare against `tests/reference/`: the legacy pipeline's cards, base card and YODAs,
  and `point_counts.toml`. Never regenerate them.
- A fake in a test has the real type (ledger L26).
- If a test run is interrupted or fails, do not restore paths automatically. Report the state to
  the user and wait for instruction.
- Do not modify source or output paths permanently without user confirmation.
- Never rely on the locale default encoding: reading a YODA file resets `LC_ALL` to `C` (L17), so
  name `encoding="utf-8"` on every text read and write.
