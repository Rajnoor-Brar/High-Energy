# 05 — Backlog: scored, ranked, phased

**Scoring.** Priority = (Impact + Risk) × (6 − Effort).
- **Impact:** how much the item slows work today, 1–5.
- **Risk:** what happens if it is *not* fixed (wrong physics, silent failures, drift), 1–5.
- **Effort:** 1 = under an hour; 3 = a session; 5 = several sessions with a migration.

| Rank | ID | Item | I | R | E | Score | Plan phase (06) |
|---|---|---|---|---|---|---|---|
| 1 | K4 | `reserved_protons` 20 vs 2; Lambda's defaults in one place (the user decides the value) | 2 | 4 | 1 | **30** | P0 |
| 2 | F1 | Configuration inheritance: `[run.defaults]`, `extends` | 5 | 2 | 2 | **28** | P1 |
| 3 | C6 | `[card] owned` for every tool, with L14b and the precedence rule; owned lines leave the user's cards on order | 3 | 4 | 2 | **28** | P2 |
| 4 | K13 | Test isolation: shared helpers, frozen fixture configs, `conftest` sets `HEKIT_*` itself | 4 | 3 | 2 | **28** | P0 |
| 5 | C4a | Rivet option precedence: inline `name:K=V` must beat `[tools.x].options` | 2 | 3 | 1 | **25** | P0 |
| 6 | C8 | Path rules: no PATH fallback for `executable`; complete `ROOTS`; document `hep plot`'s shell paths | 2 | 3 | 1 | **25** | P0 |
| 7 | C12 | Seed range per tool (`[card] seed_range`), defined once | 2 | 3 | 1 | **25** | P0 |
| 8 | B1 | One schema file for the run TOML; `jsonschema` validator; Page defaults from it | 5 | 3 | 3 | **24** | P1 |
| 9 | L1 | One layered resolver, one merge rule (fixes C4's `[prelim]` replacement) | 4 | 4 | 3 | **24** | P1 |
| 10 | F2 | `[master].include`: a shared quantity and tool library per project | 4 | 2 | 2 | **24** | P1 |
| 11 | F3 | `--why`: store identity parts, diff them in `--plan` | 4 | 2 | 2 | **24** | P1 |
| 12 | L4 | One YODA/Rivet access layer (bindings, `.info` as YAML, `rivet_dirs` once) | 3 | 3 | 2 | **24** | P3 |
| 13 | L6 | Tool facts as folder data: `config_file`, `cores`, `[combine]`, bools | 4 | 3 | 3 | **21** | P3 |
| 14 | L14b | Pythia point cards parsed and merged (each key once, `cards/pythia.json` with origins); Sherpa onto the same `merge` style | 3 | 4 | 3 | **21** | P2 |
| 15 | B6 | Beam order: the positional convention, option A (the runner owns the beam pair) or B (a plan-time check) | 3 | 4 | 3 | **21** | P2 |
| 16 | L15 | Quantity vocabulary, mappings per tool, validation by the tool (`App_Pythia --check`), `[tools.x.settings]` | 4 | 3 | 3 | **21** | P2 |
| 17 | L16 | `utils/PythiaRun.hh`: σ combination, stamping, setup, shared by App_Pythia and Inproc (K1, K2) | 3 | 4 | 3 | **21** | P3 |
| 18 | C11 | Validate `[plot]` at load time, before planning | 2 | 2 | 1 | **20** | P0 |
| 19 | C15 | `hep make`, `hep_help` with plot, `parse_intermixed_args` | 2 | 2 | 1 | **20** | P0 |
| 20 | L2 | `latex.toml`, `yoda/backend.toml`, `[render.lpp]`, `BUILTIN` into the master | 3 | 2 | 2 | **20** | P3 |
| 21 | L5 | One templater (`string.Formatter`); card parsing from `[card].line` | 2 | 3 | 2 | **20** | P3 |
| 22 | B9 | `--show-config`: every resolved value with its origin | 3 | 1 | 1 | **20** | P1 |
| 23 | F4 | `hep check`: lint every configuration without hashing | 3 | 2 | 2 | **20** | P1 |
| 24 | F5 | `hep status`, `hep clean`, `hep ls`, `hep explain` | 3 | 2 | 2 | **20** | P5 |
| 25 | F6 | JSON Schema for editors (from B1) | 3 | 1 | 1 | **20** | P1 |
| 26 | K10 | The Makefile matches 06: `modules/**`, Rivet `requires`, no unused define | 2 | 2 | 1 | **20** | P0 |
| 27 | K7/K8 | Rivet plugins: Lamriv's `SET` labels; photo_eic's η axes follow `ETAMAX`; v1 comments | 2 | 3 | 2 | **20** | P0 |
| 28 | B2 | Providers (`lhapdf/provider.py`) and rivet hooks; a "no tool names in core" test | 3 | 3 | 3 | **18** | P3 |
| 29 | L3 | Merge the twins (`yoda_of`, `base_of`, `_sha`, loaders, page builder, headings) | 2 | 2 | 2 | **16** | P3 |
| 30 | L8 | C++ kit: `Exit`, `Args`, `Json` (fixes C13) | 2 | 2 | 2 | **16** | P5 |
| 31 | L12 | `hep plot CONFIG` / `hep overlay FILE…` split; shared options | 2 | 2 | 2 | **16** | P5 |
| 32 | C3 | Naming: `Configuration.label`, `in_sweep_runs`, labels on the CLI | 2 | 2 | 2 | **16** | P1 |
| 33 | B4a | Paint batch mode, ranges written beside pages | 3 | 1 | 2 | **16** | P4 |
| 34 | F1b | Sweep `events` (and `threads`) as quantities | 3 | 1 | 2 | **16** | P1 |
| 35 | K11/K12/K14 | Manual, record and `bots/` drift: one rank table, C14, V43/V20, the ID rule, archive v1 out of `current_plan.md` | 2 | 2 | 2 | **16** | P0 |
| 36 | L7 | Stages unified: point, pre, combined, post | 3 | 2 | 3 | **15** | P3 |
| 37 | L10 | Planning cost: hash cache, plan once, shard per configuration | 2 | 1 | 1 | **15** | P0 |
| 38 | L14a | Clean append: combined cards without comments and blank lines (Pythia, Herwig, Delphes) | 2 | 1 | 1 | **15** | P0 |
| 39 | C14 | One plugin loader; `status` and `filters` as two keys; drop `[defaults]` | 1 | 2 | 1 | **15** | P3 |
| 40 | B4b | Paint reads YODA directly; no `__entries`, no merged ROOT file needed to plot | 3 | 2 | 3 | **15** | P4 |
| 41 | B7 | `stack.toml`: one registry for the software stack; `hep status` | 3 | 2 | 3 | **15** | P5 |
| 42 | F7 | Plot features: per-value styles, normalise, placeholders, bands, index, ratio reference | 4 | 1 | 3 | **15** | P4 |
| 43 | K3 | InprocJets: exit 5, `sigma_from`, fastjet in its requires line | 1 | 2 | 1 | **15** | P0 |
| 44 | B5 | One label language (LaTeX), `latex.toml`, migration script for configs | 4 | 3 | 4 | **14** | P4 |
| 45 | B3 | Journal-first execution: one event stream, one reducer | 3 | 3 | 4 | **12** | P5 |
| 46 | L9 | One sidecar/report format (JSON with a reader, or TOML) | 2 | 2 | 3 | **12** | P5 |
| 47 | L11 | Split `Step` into Step, IO, Card, Prepare and Identity | 2 | 2 | 3 | **12** | P3 |
| 48 | F8 | `--more N`: add a replica and combine | 3 | 1 | 3 | **12** | P5 |
| 49 | F10 | Small features: `parallelism = "auto"`, notify, typed mappings, `hep reproduce`, results API | 2 | 1 | 2 | **12** | P5 |
| 50 | L13 | Dead and stale code | 1 | 1 | 1 | **10** | P0 |
| 51 | K6 | `utils/Env/kit.py` for custom Python tools | 1 | 1 | 2 | **8** | P5 |
| 52 | K15 | Rename `HEKIT_*` (if wanted) | 1 | 1 | 2 | **8** | later |
| 53 | B4c | A matplotlib renderer of the page document in place of mkhtml | 4 | 3 | 5 | **7** | P4 (discuss) |
| 54 | B8 | One scheduler (a DAG with a core budget) | 3 | 2 | 5 | **5** | P5 (discuss) |
| 55 | F9 | Slurm / HTCondor executor | 3 | 1 | 5 | **4** | later |

Low scores on B4c, B8 and F9 reflect cost, not value. They are the strategic items, and each becomes cheaper once the items before it in its phase have landed.

---

## Phased plan

The phases, their steps and the open questions are in **[06_Plan.md](06_Plan.md)**, which supersedes the phase sketch first written here. The last column above gives each item's phase there. "discuss" marks the items that wait on a design note and the user's decision (B4c, B8), and the beam option (B6) is chosen at the start of P2 S3.

---

## Business justification, item by item, for the top of the list

- **F1, F2, B9.** Configs are the user's daily interface, and today they grow by copy-paste: seven nearly identical blocks in one file, and one quantity in two files. Every copy is a place to forget an edit. These turn a 190-line file into about 80 lines, with no loss of meaning.
- **C6, C12, C4a.** These are correctness items. Today a setting in a card can be silently ignored, an option can be silently overridden, and a seed rule fits one generator but applies to all. Each is the "silent failure" class the framework was built to refuse (01_Philosophy).
- **B1, L1.** The cost driver of every recent V-entry. V51 alone touched seven files for one idea. The schema pays for itself after about two new keys, and it brings editor support (F6) and generated docs for free.
- **F3.** Hours lost to "why is this point to run again?" are hours of the user's time, not the machine's. Storing the identity's parts costs one small file per point.
- **L4, L6, B2.** Each new tool currently costs core edits. These make a new tool a folder, as 02 §3 promised.
