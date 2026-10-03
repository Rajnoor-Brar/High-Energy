# 06 — The plan

This is a phased plan built on audit 1 (01–05, `utils/`) and on the framework-wide findings in [07_Consistency.md](07_Consistency.md). It was written on 2026-10-03 and folds in the user's decisions of that day.

**Nothing here is ordered yet.** Each phase, and each step, starts only on the user's word (BOT.md).

## The decisions this plan rests on

| Topic | Decision (the user, 2026-10-03) |
|---|---|
| Where the plan lives | Here; `bots/current_plan.md` keeps a pointer and progress lines |
| Configs whose keys change shape | **Break and migrate.** The old form is refused with a hint. `configs/` is migrated by a script (`utils/Env/migrate.py <change>`) only on the user's order; the test fixtures are migrated with the code |
| `"default"` in any TOML setting | **"Keep it as it is."** In a child it inherits the parent's value. At the top level it sets nothing: no card line, no flag, no page key, and the tool uses its own default or fails. A key left out at the top level takes the runner's default from the schema. Retires V37's meaning |
| Runtime state | **Off disk by default.** Watch states, the status journal and tool logs are written only with `--journal` / `--logs`. Records stay on disk: provenance, `points.json`, cards, `.complete` and products |
| B3 (event stream) and B5 (one label language) | Committed |
| B4c (replace mkhtml) and B8 (scheduler) | A design discussion first: the exact mechanics and the expected results |
| B6 (named beams) | Rejected as cumbersome. Keep "first value beam A, second beam B", and let each card's order follow its tool. Options A and B in 04 §B6, to be discussed |
| Detail | Every phase, in 2–3 steps |

**How work lands.**
- Each step is one or more local commits, never pushed.
- Each commit includes its tests and its docs rows in 02–06, and adds a V-entry to the record.
- Code and the manual cite the V-entry, never an audit ID (K12).
- `make test` stays green. Once P0 S1 is in, green means against the fixtures, not the user's configs.

---

## P0 — Ground truth and hygiene

The goal: tests that measure the code, a manual that matches it, and the quick correctness fixes.

### P0 S1 — Test isolation (K13)

- **Shared helpers.** Move `hep_run`, `plans`, `plans_of`, `REPO` and `HEP` into `tests/helpers.py`, and import them from the 9 integration files and 3 runner files that define their own.
- **Frozen configs.** Copy the configs the tests load into `tests/fixtures/configs/PhotoProduction/`: `eic`, `zeus_validation`, `sherpa`, `herwig`, `madgraph`, `whizard`, `InProcEIC` and `InProcZeus`, with their cards, taken from **the last commit that has them** (decided). The generator tests then live on, independent of the `xx/` stash. Tests load them as `./tests/fixtures/configs/…`. `point_counts.toml` follows the fixtures.
- **`conftest.py`:**
  - set `HEKIT_*` unconditionally;
  - make the basetemp absolute (in `conftest`, not `pytest.ini`);
  - extend the guard to `modules/` and `tests/reference/`.

  The guard compares content hashes, not modification times, so it fires on a real change and not on a touch.
- **Done when:** `make test` and `make test-slow` pass regardless of what the user has in `configs/`, and the failures listed in 07 §K13 are gone.

### P0 S2 — The manual, the record and `bots/` (K11, K12, K14)

- **One rank table.** `runner/__init__.py` holds it as data (`RANKS = {…}`). `test_imports.py` reads it, and 02 §3.1 is generated from it, or checked against it by `test_docs.py`.
- **02:**
  - "C1–C14";
  - points can run in parallel;
  - the run order includes the combined stage.
- **05:** Sherpa's status is `"none"` (or a `filters.toml` is added); the `merge` titles cover shards and `combine` too.
- **06:**
  - the data model;
  - the test list;
  - the Makefile claims (or the Makefile is fixed in S3);
  - where C14 is checked.
- **The record:**
  - mark V43 as superseded by V45/V46;
  - correct V20;
  - write the ID rule into 06 §8;
  - give `bots/intent.md` its own prefix, `I`.
- **`bots/`:**
  - move every finished section of `current_plan.md` (the v1 plan, P0 notes, done tasks) into `bots/archive.md`, keeping the current work only;
  - remove P0 history from `BOT.md`.

### P0 S3 — Quick correctness fixes

- **From the audit:**
  - **C4a:** the inline Rivet option beats `[tools.x].options`;
  - **C8:** no PATH fallback (`executable = "path:foo"` makes it explicit); `ROOTS` completed;
  - **C12:** `[card] seed_range` per tool;
  - **C11:** `[plot]` validated before planning;
  - **C15:** `hep make`, `plot` in `hep_help`, `parse_intermixed_args`;
  - **L10:** a hash cache; plan once under `sweep_runs`;
  - **L13:** dead code;
  - **L14a:** combined cards without comments or blank lines.
- **From 07:**
  - **K3:** InprocJets's exit code 5, `sigma_from`, and fastjet in its requires line;
  - **K10:** the Makefile builds `modules/<P>/**` (not just one level), Rivet plugins honour a `requires` line, and the unused `-DHEKIT_WITH_HEPMC` is dropped;
  - **K7:** Lamriv's labels under `SET`, and its option comment;
  - **K8:** photo_eic's η axes follow `ETAMAX`/`CHETAMAX`, and its comment drops the v1 vocabulary.
- **K4:** `Cuts::reserved_protons` defaults to 2 (what runs today), and `Lambda.cc` and `Lamriv.cc` take it from `Cuts{}` rather than repeating the literal. Lambda is reference-only, so this is cleanliness, with no change in results.

---

## P1 — The config foundation

The goal: one schema, one resolver, configs that can share, and runs that explain themselves.

### P1 S1 — The schema (B1, C2, C5, C11; F6)

- **`utils/Env/schema/run.toml`.** Every key gets:
  - `type`;
  - `default`: the runner's value when the key is absent;
  - `unset`: what a top-level `"default"` does for its consumer (no card line, no flag, no page key);
  - `inherit` / `levels`;
  - `merge` (deep or replace);
  - `choices`, `min` and `doc`.

  `[plot]` is first, then `[run]`, the configurations, `[quantities]` and `[tools]`.
- **Validation:** with `jsonschema` (already in the venv) behind a wrapper that keeps `HepError(where, hint, did-you-mean)`.
- **Removed:**
  - `config.py`'s key dicts and `_check`;
  - `plot.py`'s key tuples and type checks;
  - `Page.hh`'s defaults: the runner writes every page key it sets, and a key left out is ROOT's own choice.
- **Generated from it:**
  - `run.schema.json`, for the editor (F6);
  - docs/04's key tables, with `test_docs.py` checking that they are current.
- **Breaking:**
  - V37's "default overrides the parent" ends;
  - gutters lose `0` as "unset";
  - a top-level `"default"` for a key the runner owns is refused.
- **Migrate:** `migrate.py default` rewrites the affected `[plot]` keys.

### P1 S2 — Layers: the resolver, defaults, `extends`, `include` (L1, F1, F2, B9, C3, C4, F1b)

- **One `resolve(key, layers, schema)`** for:
  - `[run]` → configuration (with `[run.defaults]` and `extends`);
  - `[static]`;
  - `[prelim]`, which deep-merges instead of replacing (C4);
  - `[plot]` → object → overlay. With several globs, the most specific wins, and ties go by file order;
  - the style layers;
  - the master overlay;
  - the Rivet options.
- **`[master].include = ["common.toml"]`:** shared quantities, tools, the data map and `[plot]` defaults per project (F2).
- **`--show-config`:** every resolved value with its origin (B9).
- **Renames (C3):**
  - `Configuration.label` / `.folder`;
  - `swept` → `sweep_runs = ["a", "b"]`, a list that also gives the order;
  - the CLI also accepts a configuration's label.
- **Sweeping `events`** as a quantity (F1b).
- **Migrate:** `migrate.py layers` turns `swept` into the `sweep_runs` list. On the user's order, it also lifts the shared tables of `configs/PhotoProduction/` into `common.toml` (K9).

### P1 S3 — Identity explained, configs checked (F3, F4)

- **`identity.json`** beside `.complete`: the parts `record.identity` hashes. `--plan --why` prints a diff by part and key.
- **`hep check [CONFIG…]`:** loads, validates, plans connections and consumers for every configuration, without hashing binaries or probing versions. It exits 0 or 2, and runs over all of `configs/` and the fixtures in `make test`.

---

## P2 — The card and quantity contract

The goal: one rule for how values reach native cards, checked by the tools themselves.

### P2 S1 — The quantity vocabulary (L15)

- **`utils/Env/quantities.toml`:** names, shapes, units and docs.
- **`utils/Env/<tool>/quantities.toml`:** how each tool consumes them. `master.toml` is retired; a project overlay remains as `configs/<P>/quantities.toml`.
- **Values checked against their shapes at plan time**, e.g. `energies` is two numbers in GeV.
- **Migrate:** none in configs, unless a project master exists (`migrate.py vocabulary`).

### P2 S2 — Cards (L14b, C6, L15's precedence)

- **`[card] style = "merge"`** with a grammar per folder:
  - Pythia: parse, merge with overridden keys moved to the end, repeatable commands kept verbatim, `cards/<tag>.json` with origins;
  - Sherpa's `render.py` becomes the YAML instance;
  - Herwig and Delphes stay `append` (made clean by L14a), with a warning on a duplicate.
- **`[card] owned`** for every tool. A base card that sets an owned key is refused, with a hint.
- **`[tools.<tag>.settings]`:** native settings passed straight through.
- **One precedence:** base < settings < quantities < runner-owned. Two sources in one layer is an error.
- **`App_Pythia --check`** (in L16's kit), run at plan time for each distinct card and cached by the card's hash. Herwig's `read` is its check.
- **Migrate (needs the user's order):** remove the owned lines from `photo_ep.cmnd` and `photo_zs.cmnd` (`Main:numberOfEvents`, `Random:*`, and `Beams:*` if option A is chosen in S3).

### P2 S3 — Beam order (C7, B6): a discussion first

- Present options A and B (04 §B6) with a worked example per tool: Pythia, Herwig, Sherpa, Whizard, MadGraph.
- After the user decides, build:
  - **A:** `beams` and `energies` owned and aligned; `[card] beam_slots` for Herwig;
  - **or B:** a plan-time check of the card's `Beams:idA` against a declared order.

---

## P3 — Core purity

The goal: the rule "the core never names a tool" holds, and is tested.

### P3 S1 — Files and providers (L4, B2, L6)

- **`runner/hepfiles.py`:** YODA through its bindings (`.gz` transparent), `.info` as YAML, `.plot` blocks, `rivet_dirs()` called once, and the event count. It replaces three regex readers and three `rivet-config` calls.
- **`utils/Env/lhapdf/provider.py`:** LHAPDF set checks, and the Pythia `pSet` check against `PDFSelection.xml` (pending since V40).
- **Folder data and hooks instead of core `if`s:**
  - `config_file` and `accepts_exports` (custom, module);
  - Rivet's `render.py` hooks (analyses, the `.info` check, identity files);
  - `cores`;
  - `[combine]`;
  - option bools.
- **A test** greps the core for tool names and fails on any match.

### P3 S2 — Templates, tables and twins (L5, L2, L3, C14)

- **One `Template`** (on `string.Formatter`) for argv, env, cwd, footers, seeds, prelim commands and card lines. `[card].line` also compiles to its own parser.
- **Data files:** `latex.toml`, `yoda/backend.toml`, `[render.lpp]`, and `BUILTIN` with its mappings.
- **Merged twins:**
  - `yoda_of` and `_yoda_product`;
  - `base_of` and `_base`;
  - `_sha` and `sha256_file`;
  - the two plugin loaders;
  - the page builder;
  - the headings.
- **`status`/`filters` as two keys,** and `[defaults]` removed from `filters.toml`.

### P3 S3 — Stages, Step, and the Pythia kit (L7, L11, L16)

- **One `Stage`** for point, pre, combined and post, with `plan_stage` and `run_stage`. `cli.run_one` becomes a loop.
- **`Step` split** into Step, IO, Card, Prepare and a typed Identity, with the `_flags` hack removed.
- **`utils/PythiaRun.hh`:**
  - σ combination, `Stamper`, card setup with the L4 check and thread resolution, and the chunked run;
  - `App_Pythia` and `Inproc` both use it, which fixes K1 and K2;
  - `test_modules_p4.py`'s equivalence check confirms the result.

---

## P4 — Plotting

The goal: one page document, fewer processes, one label language, and the plot features most wanted.

### P4 S1 — Paint batch mode, and Paint reads YODA (B4a, B4b)

- **`Paint.exe PAGE.toml…`:** many pages per ROOT process, with `<page>.ranges.json` written beside each, which replaces `--dump-ranges`.
- **`[[curve]]` may name a `.yoda` file:**
  - raw entries come from the Histo1D itself, so the merged ROOT file and `__entries` leave the plotting path;
  - `plot.convert` and `plot.merge` go;
  - the sweep ROOT file stays a product (`plotmerge`).

### P4 S2 — One label language, and the first plot features (B5, F7)

- **LaTeX `$…$` everywhere:**
  - `tlatex()` is the only converter, driven by `latex.toml`;
  - the yoda backend passes labels straight through;
  - a label with `#` outside math is refused with the converted form as a hint (break and migrate).
- **Migrate (needs the user's order):** `migrate.py labels` over `configs/`.
- **F7, first items:**
  - styles per value: `[quantities.pdf].style`, or `[plot.curves."<tag>"]`;
  - `normalise`;
  - placeholders (`{cell}`, `{q:energies}`, `{opt:ETMIN}`), which fix photo_eic's hard-coded legends (K8);
  - `band = ["<quantity>"]` envelopes;
  - an index page for the ROOT pages.

### P4 S3 — B4c: a design discussion

A note, `docs/audit_1/notes/B4c.md`:
- **Mechanics:** a matplotlib renderer of the page TOML, the merged `base.toml` and `ranges.json`, and what happens to `index.html`.
- **Expected results:** side-by-side pages, Paint vs mkhtml vs the prototype, on the plot-stage test pages and one real zeus cell, with a list of the differences.
- **The evidence:** how many changes since V47 touched `yoda/backend.py`.

The user decides. Building it, if chosen, is a step of its own.

---

## P5 — Execution and UX

The goal: one event stream, runtime state off disk, and the housekeeping a daily user needs.

### P5 S1 — The event stream (B3, C16, and the off-disk decision)

- **`execute` emits versioned events** onto an in-memory bus. One reducer turns them into state, and the live and plain views render it on their own thread.
- **`hep watch`** attaches through `watch.sock`, served while the run lives, with the current state first and then the live events. It also carries a `sweep_runs` sequence.
- **`--journal`** writes `status.jsonl` (for replay, `hep watch --file`, and test fixtures).
- **`--logs`** keeps every tool's full log. By default, tool output is read from pipes, and only a failed tool's last ~200 lines are written (open question 5).
- **Removed:** the sink plumbing, `_PointSink`, the second heading builder, and the journal-offset scanning.

### P5 S2 — CLI, housekeeping, and the C++ kit (L12, F5, L8, L9, C13)

- **Commands:**
  - `hep plot CONFIG` and `hep overlay FILE…`, each with its own options;
  - `hep status`, `hep clean [--dry-run]`, `hep ls`, `hep explain <key>` (from the schema), `hep make`.
- **`utils/Kit.hh`:** `Exit`, `Args`, `Json`. It is used by `Module.hh`, `App_Pythia`, `App_yd2rt` and Paint, so there is one exit-code table (C13).
- **One sidecar format,** JSON with the kit's reader (L9 option A), unless the user prefers TOML.
- **`utils/Env/kit.py`:** the Python twin for custom tools (arguments, status, exit codes, report), with `delphes_jets.py` as its first user (K6).

### P5 S3 — B8: a design discussion, then the rest

- **A note, `docs/audit_1/notes/B8.md`:**
  - **Mechanics:** DAG nodes and edges, how a FIFO group starts atomically, the core budget, `parallelism` as a cap, and how failure attribution and the stop ladder (V32) carry over.
  - **Expected results:** a simulated schedule, then a measured wall time on a zeus sweep, before and after.

  The user decides.
- **Then:**
  - **F8:** `--more N` adds a replica and runs its combine;
  - **F10:**
    - `parallelism = "auto"`;
    - `notify`;
    - typed mappings;
    - `hep reproduce`;
    - a results API;
  - **B7:** `stack.toml`, with `hep status` showing versions.

---

## Later

- **F9:** a Slurm/HTCondor executor, after P5 S1. Jobs run with `--journal` on a shared filesystem.
- **K15:** a `HEKIT_*` rename, if wanted.

---

## Open questions for the user

| # | Question | Needed by |
|---|---|---|
| 1 | ~~`reserved_protons`: 20 or 2?~~ **Answered:** Lambda is reference-only, so 2, the value that actually runs, with one default (K4) | P0 S3 |
| 2 | ~~The test fixtures' source?~~ **Answered:** the configs and cards from the last commit that has them | P0 S1 |
| 3 | ~~`configs/PhotoProduction/xx/`?~~ **Answered:** a deliberate stash, kept for reference and not used. No action; the tests no longer depend on it (fixtures) | P0 S1 |
| 4 | When to run each `configs/` migration (`default`, `layers`, `owned`, `labels`, and `beams` if A) | each step that adds one |
| 5 | Is a failed tool's log tail kept by default, or does that need `--logs` too? | P5 S1 |
| 6 | Beam order: option A or B? | P2 S3 |
| 7 | B4c and B8, after their notes | P4 S3, P5 S3 |
| 8 | Rename `HEKIT_*`? | Later |
| 9 | Sidecars: JSON with a reader, or TOML? | P5 S2 |

---

## Deferred to the final phase (the user, 2026-10-03: `configs/PhotoProduction/` untouched until then)

Changes that would make the user's current PhotoProduction configs fail, and the migrations of their files,
wait for the last steps of the last phase; meanwhile the code accepts what those configs use.

| Item | What changes in `configs/PhotoProduction/` |
|---|---|
| C8 (V54) | `eic.toml` `[tools.jets].executable = "python3"` → `"path:python3"` (only its unused delphes chain needs it) |
| C3 | `swept = false` → a `[run].sweep_runs = ["a", "b"]` list (the rename itself waits, so `zeus_validation.toml` keeps working) |
| C6 / L14b | owned lines out of `photo_ep.cmnd` / `photo_zs.cmnd` (`Main:numberOfEvents`, `Random:*`, `Beams:*` if beam option A) |
| F1, F2 (V56) | on the user's word: `zeus_validation.toml`'s seven configurations as `extends`, shared tables lifted into `common.toml` |
| B5 | labels from TLatex to LaTeX (`migrate.py labels`) |
| held C++ / Rivet (P0 S3) | K3, K4 (Lamriv), K7, K8, K10's define, yd2rt's dead parameter: rebuilt binaries change the user's points' identities |

## Progress

| Phase | Steps | State |
|---|---|---|
| P0 | S1 S2 S3 | done: S1 (V52), S2 (V53), S3 (V54; its held C++ and Rivet items landed with V63, the reruns accepted) |
| P1 | S1 S2 S3 | done: S1 (V55 schema, "default"), S2 (V56 layers, include, --show-config), S3 (V57 --why, hep check) |
| P2 | S1 S2 S3 | done: S1 (V58), S2 (V59), S3 (V62: option A, the run's beam order into each card's slots) |
| P3 | S1 S2 S3 | done: S1 (V60), S2 (V61: tables as data, one plugin loader, twins merged, filters key), S3 (V63: PythiaRun.hh, one stage runner, Step.flags) |
| P4 | S1 S2 S3 | S1 (V64: batch mode; B4b dropped, see V64) done; S2: B5 (V65), F7 placeholders (V66), per-value styles (V67), normalise (V68), bands (V69), index page (V70) done: S2 complete; S3: the B4c note (notes/B4c.md); decided B, "mpl", matching mkhtml until verified; S4: built (V71), pixel-identical to mkhtml, ~18× faster; awaiting the user's verification |
| P5 | S1 S2 S3 | S1 (V72: one event stream, watch socket, --journal, --logs) done |
