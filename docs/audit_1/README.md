# Audit 1 — `utils/`

An audit of everything under `utils/`, done on 2026-10-03 at `6f2bfaa` (branch `rework`).

**Read:**
- the Python runner, `utils/Env/runner/*`: about 3,950 lines;
- the tool folders, `utils/Env/<tool>/`: `tool.toml`, `filters.toml` and `render.py`;
- `master.toml`, the yoda backend, `hep`, `hep_env.sh` and `flags.sh`;
- the C++ headers and apps: `Status.hh`, `Module.hh`, `App_Pythia.cc`, `App_yd2rt.cc` and Paint, about 2,400 lines;
- the parts of the Makefile and `tests/` that touch them.

**Not read:** `modules/` and `configs/`, except where a config shows a problem in `utils/`.

The brief asked for four things, each with bold proposals welcome:
- design and code patterns that conflict, especially in configs;
- features one would expect that are missing;
- ways to make the code leaner: reorganise it, move lookups into data files (as `master.toml` and `base.toml` already do), merge repeated code, and use standard parsing;
- bold proposals.

## The documents

| File | What it holds |
|---|---|
| [01_Conflicts.md](01_Conflicts.md) | Patterns that contradict each other or the manual's own rules, config first |
| [02_Missing_Features.md](02_Missing_Features.md) | What a user of this framework would expect and not find |
| [03_Lean_Code.md](03_Lean_Code.md) | Repetition, hard-coded lookups that belong in data files, and hand-rolled parsing |
| [04_Bold_Proposals.md](04_Bold_Proposals.md) | Large and risky restructurings, each with its case and its cost |
| [05_Backlog.md](05_Backlog.md) | Every item scored (impact, risk, effort) and ranked, with its phase in 06 |
| [06_Plan.md](06_Plan.md) | **The plan:** phases P0–P5, 2–3 steps each, the user's decisions of 2026-10-03, and the open questions |
| [07_Consistency.md](07_Consistency.md) | The framework beyond `utils/`: `modules/`, `configs/`, the Makefile, `docs/`, `tests/` and `bots/` (K1–K15) |

Every finding is tagged with an ID: `C` (conflict), `F` (feature), `L` (lean), `B` (bold), `K` (framework consistency, 07). The backlog ranks all of them on one scale. Where a finding names code, it gives `file:line` at the audited commit.

**The ID rule (K12).** These IDs overlap the record's own C-rules, F-findings and L-ledger rows. So, outside this folder and `bots/`, an audit item is cited as "audit C6". Code and the manual never cite audit IDs: they cite the V-entry made when the item lands.

## The state of things, in brief

The framework is in good shape for its age. Errors are precise, and plan-time checks are thorough. The tool-folder contract (`tool.toml`) is a real abstraction, and `base.toml` shows a pattern worth copying elsewhere: one data file, read by both languages. The problems are typical of a codebase that grew one V-entry at a time:

1. **The schema of the run TOML exists in five places at once.** It is spread over:
   - Python dicts in `config.py`;
   - more dicts and default values in `plot.py`;
   - default values again in `Page.hh`;
   - the choices again in `Style.hh`;
   - the reference tables in docs/04, which `test_docs.py` checks.

   Each new key (V39, V42, V44, V51) touched three or four of these. **One schema file** (`B1`) would remove most of that work. It would also give editor autocompletion and generated docs.
2. **Parent→child inheritance is written seven times, with four different merge rules.** The seven:
   - `[run]` → `[run.<cfg>]`;
   - `[static]`;
   - `[prelim]`;
   - `[plot]` → object → overlay;
   - the style layers;
   - `master.toml` → the project master;
   - the analysis options.

   Some merge key by key, some replace a whole table, some deep-merge, and one updates in order of matching globs (`C4`). A single resolver with one rule would make them predictable (`L1`).
3. **"The runner core never names a tool" (BOT.md, 02 §3) is not true in practice.** `custom`, `module`, `rivet` (its analyses, `.info` files, `build/Rivet`), `pythia_cmnd`, `merge`, LHAPDF, YODA, `App_yd2rt` and `rivet-config` are all named in core modules (`C1`). Each one is a place where a new tool means editing the core.
4. **The plotting layer translates its text three ways and patches generated code.** Labels move between three converters (LaTeX → TLatex, TLatex → mathtext, and escapes), and the yoda backend regex-patches the Python that rivet-mkhtml writes (`C9`, `B4`). This is the most fragile code in `utils/`, and the most expensive to extend: V47–V51 each needed a fix in both backends.
5. **Configs are verbose because nothing can be shared.** `zeus_validation.toml` has seven configurations that differ only in their label and event count. `eic.toml` and `zeus_validation.toml` declare the same `energies` quantity separately. Configuration inheritance (`F1`) and a shared quantity library (`F2`) are the most-wanted features.

## Top ten

Ranked by the backlog's score. The order of work is set in [06_Plan.md](06_Plan.md), which also sequences by dependency: P0 hygiene, then the schema and the resolver, then the rest.

| # | ID | Item | Score |
|---|---|---|---|
| 1 | K4 | `reserved_protons` 20 vs 2; Lambda's defaults in one place (the user decides the value) | 30 |
| 2 | F1 | Configuration inheritance: `[run.defaults]`, `extends` | 28 |
| 3 | C6 | `[card] owned` for every tool, with L14b and the precedence rule; owned lines leave the user's cards on order | 28 |
| 4 | K13 | Test isolation: shared helpers, frozen fixture configs, `conftest` sets `HEKIT_*` itself | 28 |
| 5 | C4a | Rivet option precedence: inline `name:K=V` must beat `[tools.x].options` | 25 |
| 6 | C8 | Path rules: no PATH fallback for `executable`; complete `ROOTS`; document `hep plot`'s shell paths | 25 |
| 7 | C12 | Seed range per tool (`[card] seed_range`), defined once | 25 |
| 8 | B1 | One schema file for the run TOML; `jsonschema` validator; Page defaults from it | 24 |
| 9 | L1 | One layered resolver, one merge rule (fixes C4's `[prelim]` replacement) | 24 |
| 10 | F2 | `[master].include`: a shared quantity and tool library per project | 24 |

## Method

- Every module was read in full. Findings were checked against the code: for example, `[defaults] last_line` in every `filters.toml` was confirmed unread by grep, and `hep make` was confirmed missing from the case statement.
- Scores follow the tech-debt framework: Priority = (Impact + Risk) × (6 − Effort). Each axis runs 1–5, and Risk means the risk of *not* fixing the item.
- 07 comes from two read-only surveys (`modules/` and `configs/`; docs, tests and `bots/`), spot-checked against the tree.
- No code was changed by this audit.
