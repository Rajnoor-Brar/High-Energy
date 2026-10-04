# Audit 2 — the manual, rebuilt


**Status (2026-10-04): done.** M0 a029c21, M1 V90–V91, M2 (docs/next/), M3 V92: the new pages in place, 130 of 130 inventory rows map to a section that exists. 01–06 are 4,659 lines (the target was about 3,000: the figures, the generated tables and the bulleted structure added more than the de-duplication removed).

## Context

The user asked to "update/rebuild the docs/manual/reference" and chose **rebuild from scratch**: a new layout chosen for today's framework, keeping the knowledge of the old text but not its wording. Two further decisions:
- the docs describe the code as it is now; later audit-2 steps update the rows they change;
- `07_Record.md` is left as it is, apart from links and new glossary terms.

**Today:** pages 01–06 are 3,656 lines.
- `test_docs` keeps the keys and links honest, but much of the content has drifted. The figures work (V80–V89) is missing from 02, 03, 05 and 06. So are Paint's markers and heat maps, the mpl backend, `hep reproduce`/`migrate`/`status --stack`, and the results API.
- 04 restates every schema key by hand, so its tables drift from `utils/Env/schema/run.toml`; §11.2 is one 2,900-character table cell.
- 02 (Architecture) and 06 (Developer Guide §3) overlap.
- 05 mixes the standard tools with developer material (Paint internals, `Module.hh`, `Status.hh`).
- The commands sit inside the config reference (04 §14).

**Aim:** a manual that cannot drift where it doesn't have to.
- What the code can state, it states: the keys, the style keys and the commands are generated from the schema, `base.toml` and the CLI parser, and checked current by a test.
- What only prose can say is written fresh, once, in the page where its reader looks.

## The new layout (seven pages; the record keeps its number)

| Page | For | Holds | From (old) |
|---|---|---|---|
| `01_Overview.md` | everyone | what it is; the model in one picture; the vocabulary (run, configuration, point, quantity, tool, group, **object, page, figure**); the principles, each with what it buys and costs; what is refused; where it came from | 01 whole, 02 §1–2 |
| `02_User_Guide.md` | users | set up and build; a first run; anatomy of a run TOML; the pipelines as recipes (today's 4.1–4.21, re-checked and regrouped: one point and sweeps, generators and chains, your own programs, scale and seeds); watching, subsets and reruns; when something fails; reproduce, status, clean and migrate in use; reading results from Python; a new project | 03 whole, 04 §14 prose |
| `03_Plots.md` | users | the plot stage as a user sees it: objects → figures → pages; `[plot]` in practice; data and ratios; the style layers; **one section per figure class** (defined, overlay, merged, compare, derived, scan, sheet) with a full example, its pages and its limits; types (Hist1D, Scatter2D, HeatMap); the backends and what each draws; `hep overlay` | 03 §5, 04 §11–12 prose, 02 §13 user parts, 05 §14 |
| `04_Config_Reference.md` | users | **every key**, as generated tables: master, run, configuration, prelim, static, quantity, tool, plot, data, figure, style. Prose only where a table can't say it: files and which wins, paths, inheritance and `"default"`, selectors, consumers and built-in quantities, placeholders, the validation rules C1–C14, the files the runner writes | 04 §1–13, 15 |
| `05_Commands_and_Tools.md` | users, developers | **every command and option**, generated from `cli.parser()`, with the prose each needs; the environment and `make`; each standard tool folder, as now (its options, cards and rules); App_Pythia and App_yd2rt as users run them; Paint's command line | 04 §14, 05 §1–16 |
| `06_Internals.md` | developers | the components and the rank table; the data model; a run from command to pages, in code; connections, sharding, scopes; identity, seeds and skip; the prepare cache; status, events and watch; failures and exit codes; provenance; the plot stage inside (pages, figures, stamps, backends); where files go. Then: the build, the tool-folder contract, adding a tool, backend or figure class, Paint inside, `Module.hh`, `Status.hh` and the status protocol, `filters.toml`, tests, conventions, changing things safely | 02 §3–14, 06 whole, 05 §17–20 |
| `07_Record.md` | everyone | unchanged; links updated; glossary gains object, page, figure, class, type | 07 |

- **Target:** at most about 3,000 lines for 01–06, with no fact lost (the inventory below holds us to it).
- **Writing style:** today's plain sentences: short, active, no hedging; sections numbered so the code can cite them (`04 §9.4`).

## What gets generated (the bold part)

**Sources:**
- `utils/Env/schema/run.toml` gains an optional **`notes`** field per key. The long explanations now in 04's "Notes" column move there, so `hep explain KEY` shows them too: one source for the editor, the CLI and the manual. `doc` stays the one-liner.
- `utils/Apps/Paint/base.toml`'s inline comments are already the style keys' meanings, and are read as they are.
- The CLI's help strings come from `runner/cli.py`'s `parser()`.

**Generator:**
- A new `runner/docs.py` (rank 5, standard library only) renders:
  - `keys(table)`: Key | Type | Default | Meaning;
  - `style()`: the dotted base.toml keys, value and comment;
  - `commands()`: each subcommand's usage and options.
- `make docs` rewrites each block between `<!-- generated: keys plot -->` and `<!-- /generated -->` in place.
- A test, `test_the_generated_sections_are_current`, works as `test_the_editor_schema_is_current` does: the blocks must equal what `docs.py` renders now ("run `make docs`").

**Not generated:**
- the tool folders' options in 05: `tool.toml` `[options]` carry no doc yet. They stay hand-written, held by the existing test.

## Phases (each step a local commit with its tests; V-rows V90 onwards)

- **M0, the plan:**
  - This page.
  - Include the **inventory**: every heading of today's 01–06 (about 150), each with its new page and section, or "dropped: <why>" (e.g. a fact now generated). Commit it; nothing else changes.
- **M1, the generator:**
  - **S1:** `notes` in `schema/run.toml`, moved from 04's tables row by row (a script, with the diff reviewed by hand). `schema.py` accepts the field and `hep explain` prints it. `make schema` regenerates the JSON (`notes` goes into its `description`).
  - **S2:** `runner/docs.py`, the `make docs` target and the currency test. Add it to `RANKS` (`runner/__init__.py`) and `test_imports`.
- **M2, the pages:**
  - Write them into `docs/next/`, so that the old manual and `test_docs` stay green until the switch. One commit each:
    - **S1:** `01_Overview` and `06_Internals`, checked against the code at HEAD module by module (every named function, path and behaviour opened and confirmed).
    - **S2:** `02_User_Guide` and `03_Plots`. Every TOML example is a real one: each complete example loads (the existing test does this), and each figure example comes from `tests/integration/test_plot_stage.py`'s fixtures.
    - **S3:** `04_Config_Reference` and `05_Commands_and_Tools`, with the generated blocks filled by `make docs`.
- **M3, the switch:**
  - **S1:**
    - `git mv` `docs/next/*` over `docs/` (old 01–06 removed).
    - Remap the code's citations with the inventory's old §→new § table: a script over `utils/`, `tests/`, `Makefile` and `hep`, about 35 short citations and about 70 `docs/0N_*.md` names. The same for `bots/BOT.md`, `docs/README.md`, the links in 07, and the `utils/Env/schema/run.toml` header.
    - Adapt `test_docs.py`:
      - the page names;
      - `reference()` becomes 04 + 05 (+ 03 for its figure examples);
      - the rank-table test reads `06 §…`;
      - the tool-section test reads `05`.
  - **S2:** the inventory check (every old heading is mapped and its new section exists), README and memory updated, and the audit_1/audit_2 docs' links into the manual left as history but made to resolve, through a line at the top of each saying the manual was rebuilt at V9x.

## The new pages, section by section

The numbers are what the code cites. Old 04 §1–13 and old 02 §4–14 keep their numbers (as 04 and
06), so most citations need only the page name changed.

**01_Overview:** 1 What it is · 2 The model in one picture · 3 Vocabulary · 4 Principles (4.1–4.12,
as old 01 §2.1–2.12) · 5 What is refused · 6 Where it came from.

**02_User_Guide:** 1 Set up and build · 2 A first run · 3 Anatomy of a run TOML · 4 Sweeps and points
(4.1 One point · 4.2 A sweep · 4.3 A grid, split into pages · 4.4 Quantities that move together ·
4.5 A configuration's own fixed values · 4.6 A quantity Pythia does not know by name · 4.7 Analysis
options · 4.8 Every configuration, one run after another) · 5 Generators and chains (5.1 A file
chain · 5.2 Other generators · 5.3 The same study with several generators · 5.4 Something every
point needs, made once) · 6 Your own programs (6.1 An analysis program · 6.2 An integrated program ·
6.3 A custom tool, and a Python one) · 7 Scale and statistics (7.1 More Rivets · 7.2 Several points
at once · 7.3 Replicas, merged · 7.4 Seeds, and repeating a run) · 8 Watching, subsets and reruns ·
9 When something fails · 10 Housekeeping: check, status, clean, migrate, reproduce · 11 Reading
results from Python · 12 A new project.

**03_Plots:** 1 Objects, figures and pages · 2 The plot stage · 3 `[plot]` in practice · 4 Reference
data and ratios · 5 Curves: labels, looks and bands · 6 The style · 7 Figures (7.1 Declaring a
figure · 7.2 defined · 7.3 overlay · 7.4 merged · 7.5 compare · 7.6 derived · 7.7 scan · 7.8 sheet)
· 8 Types: Hist1D, Scatter2D, HeatMap · 9 Backends · 10 Any files, overlaid: `hep overlay`.

**04_Config_Reference:** 1 Files, and which wins · 2 Paths · 3 `[master]` · 4 `[run]` (4.1
`sweep_runs`) · 5 `[run.<configuration>]` (5.1–5.5 as now) · 6 `[prelim]` · 7 `[static]` and
selectors · 8 `[quantities.<q>]` (8.1–8.3) · 9 `[tools.<tag>]` (9.1–9.4) · 10 Placeholders · 11
`[plot]` (11.1 `[plot.data]` · 11.2 `[plot.figures.<figure>]`) · 12 The style · 13 Validation rules ·
14 Files the runner writes.

**05_Commands_and_Tools:** 1 Commands (1.1 `hep run` · 1.2 `hep plot` and `hep overlay` · 1.3 `hep
ls`, `explain`, `status`, `clean` · 1.4 `hep check` · 1.5 `hep watch` · 1.6 `hep migrate` · 1.7 `hep
reproduce`) · 2 The environment, `hep build` and `make` · 3 The standard tools at a glance · 4
`pythia` · 5 `rivet` (5.1 sharded) · 6 `yd2rt` · 7 `merge` · 8 `plotmerge` · 9 `custom` · 10 `module`
· 11 `delphes` · 12 `herwig` · 13 `sherpa` · 14 `whizard` · 15 `madgraph` · 16 App_Pythia · 17
App_yd2rt · 18 Paint's command line.

**06_Internals:** 1 Repository layout · 2 Components (2.1 The runner · 2.2 The C++) · 3 The data
model · 4 Tool categories · 5 A run, from command to pages (5.1 One point · 5.2 Several runs, points
at once, combine) · 6 Connections (6.1 Sharding) · 7 Scopes · 8 Identity, seeds and skip · 9 The
prepare cache · 10 Status, events and watch · 11 Failures and exit codes · 12 Provenance and
manifests · 13 The plot stage inside · 14 Where files go · 15 The build (15.1–15.3) · 16 The
tool-folder contract (16.1–16.3) · 17 Adding a standard tool · 18 Adding a plot backend · 19 Adding a
figure class · 20 Paint inside · 21 `Module.hh` · 22 `Status.hh` and the status protocol · 23
`filters.toml` · 24 Writing C++ · 25 Tests · 26 Conventions · 27 Changing things safely.

## The inventory: every old section and its new home

M3 remaps the code's citations from this table, and checks that every row's new section exists.
Old 04 §14's unnumbered subsections go to 05 §1.1–1.7 and §2, and "Reading results from Python" goes
to 02 §11.

| Old | Heading | New | Also |
|---|---|---|---|
| 01 §1 | What it is | 01 §1 |  |
| 01 §2 | Principles | 01 §4 |  |
| 01 §2.1 | Every tool is a process, and the runner only decides | 01 §4.1 |  |
| 01 §2.2 | Physics lives in the native card | 01 §4.2 |  |
| 01 §2.3 | Resolved means resolved | 01 §4.3 |  |
| 01 §2.4 | Say it once, where it belongs | 01 §4.4 |  |
| 01 §2.5 | Require the explicit statement; refuse the convenient inference | 01 §4.5 |  |
| 01 §2.6 | Refuse early, and say what to do | 01 §4.6 |  |
| 01 §2.7 | A partial result has a different name | 01 §4.7 |  |
| 01 §2.8 | Identity decides; location is only location | 01 §4.8 |  |
| 01 §2.9 | Knowledge outlives code | 01 §4.9 |  |
| 01 §2.10 | Measure it, and say the number when it is bad | 01 §4.10 |  |
| 01 §2.11 | Enforce the rules you can | 01 §4.11 |  |
| 01 §2.12 | Small by surface area | 01 §4.12 |  |
| 01 §3 | What is refused | 01 §5 |  |
| 01 §4 | Where it came from | 01 §6 |  |
| 02 §1 | The model in one picture | 01 §2 |  |
| 02 §2 | Vocabulary | 01 §3 |  |
| 02 §3 | Components | 06 §2 |  |
| 02 §3.1 | The runner | 06 §2.1 |  |
| 02 §3.2 | The C++ | 06 §2.2 |  |
| 02 §4 | Tool categories and what the runner does with each | 06 §4 |  |
| 02 §5 | A run, from command to pages | 06 §5 |  |
| 02 §5.1 | One point | 06 §5.1 |  |
| 02 §6 | Connections | 06 §6 |  |
| 02 §6.1 | Sharding: one tool as K processes | 06 §6.1 |  |
| 02 §7 | Scopes | 06 §7 |  |
| 02 §8 | Identity, seeds and skip | 06 §8 |  |
| 02 §9 | The prepare cache | 06 §9 |  |
| 02 §10 | Status, the event stream and the watch view | 06 §10 |  |
| 02 §11 | Failure handling and exit codes | 06 §11 |  |
| 02 §12 | Provenance and manifests | 06 §12 |  |
| 02 §13 | The plot stage | 06 §13 | the user's view → 03 §2 |
| 02 §14 | Where files go | 06 §14 |  |
| 03 §1 | Set up and build | 02 §1 |  |
| 03 §2 | A first run | 02 §2 |  |
| 03 §3 | Anatomy of a run TOML | 02 §3 |  |
| 03 §4 | Pipelines | 02 §4 |  |
| 03 §4.1 | One point | 02 §4.1 |  |
| 03 §4.2 | A sweep: one quantity, one page | 02 §4.2 |  |
| 03 §4.3 | A grid, split into pages | 02 §4.3 |  |
| 03 §4.4 | Quantities that move together | 02 §4.4 |  |
| 03 §4.5 | A configuration's own fixed values | 02 §4.5 |  |
| 03 §4.6 | A quantity Pythia does not know by name | 02 §4.6 |  |
| 03 §4.7 | Analysis options | 02 §4.7 |  |
| 03 §4.8 | Comparing to data | 03 §4 |  |
| 03 §4.9 | Replicas, merged | 02 §7.3 |  |
| 03 §4.10 | A file chain: generator → Delphes → your analysis | 02 §5.1 |  |
| 03 §4.11 | Other generators | 02 §5.2 |  |
| 03 §4.12 | The same study with several generators | 02 §5.3 |  |
| 03 §4.13 | Your own analysis program | 02 §6.1 |  |
| 03 §4.14 | An integrated program | 02 §6.2 |  |
| 03 §4.15 | A custom tool, and a Python one | 02 §6.3 |  |
| 03 §4.16 | Something every point needs, made once | 02 §5.4 |  |
| 03 §4.17 | Faster points: more Rivets | 02 §7.1 |  |
| 03 §4.18 | Many points: several at once | 02 §7.2 |  |
| 03 §4.19 | Any files, overlaid | 03 §10 |  |
| 03 §4.20 | Every configuration, one run after another | 02 §4.8 |  |
| 03 §4.21 | Exact seeds, random seeds, and repeating a run | 02 §7.4 |  |
| 03 §5 | Plots | 03 §3 | and 03 §6 (the style) |
| 03 §6 | Watching, subsets and reruns | 02 §8 |  |
| 03 §7 | When something fails | 02 §9 |  |
| 03 §8 | A new project | 02 §12 |  |
| 04 §1 | Files, and which wins | 04 §1 |  |
| 04 §2 | Paths | 04 §2 |  |
| 04 §3 | `[master]` and the master TOML | 04 §3 |  |
| 04 §4 | `[run]` | 04 §4 |  |
| 04 §4.1 | `sweep_runs`: every configuration, one run after another | 04 §4.1 |  |
| 04 §5 | `[run.<configuration>]` | 04 §5 |  |
| 04 §5.1 | `sweeps` | 04 §5.1 |  |
| 04 §5.2 | `plot_points` | 04 §5.2 |  |
| 04 §5.3 | `tools` | 04 §5.3 |  |
| 04 §5.4 | `pre` and `post` | 04 §5.4 |  |
| 04 §5.5 | `combine` | 04 §5.5 |  |
| 04 §6 | `[prelim]` | 04 §6 |  |
| 04 §7 | `[static]` and selectors | 04 §7 |  |
| 04 §8 | `[quantities.<q>]` | 04 §8 |  |
| 04 §8.1 | Who consumes a quantity | 04 §8.1 |  |
| 04 §8.2 | Replicas | 04 §8.2 |  |
| 04 §8.3 | Built-in quantities | 04 §8.3 |  |
| 04 §9 | `[tools.<tag>]` | 04 §9 |  |
| 04 §9.1 | Keys every tool table takes | 04 §9.1 |  |
| 04 §9.2 | Custom tools | 04 §9.2 |  |
| 04 §9.3 | Module tools | 04 §9.3 |  |
| 04 §9.4 | Standard configurations (exports) | 04 §9.4 |  |
| 04 §10 | Placeholders | 04 §10 |  |
| 04 §11 | `[plot]` | 04 §11 | keys generated; prose → 03 §3 |
| 04 §11.1 | `[plot.data]` | 04 §11.1 |  |
| 04 §11.2 | Figures: `[plot.figures.<figure>]` | 04 §11.2 | keys generated; one section per class → 03 §7 |
| 04 §12 | The style | 04 §12 | keys generated; the layers → 03 §6 |
| 04 §13 | Validation rules | 04 §13 |  |
| 04 §14 | Commands | 05 §1 |  |
| 04 §15 | Files the runner writes | 04 §14 |  |
| 05 §1 | The standard tools at a glance | 05 §3 |  |
| 05 §2 | `pythia` — App_Pythia | 05 §4 |  |
| 05 §3 | `rivet` | 05 §5 |  |
| 05 §3.1 | Sharded Rivet: `shards = K` | 05 §5.1 |  |
| 05 §4 | `yd2rt` — YODA → ROOT | 05 §6 |  |
| 05 §5 | `merge` — rivet-merge, in `post` | 05 §7 |  |
| 05 §6 | `plotmerge` — the sweep in one file, in `post` | 05 §8 |  |
| 05 §7 | `custom` | 05 §9 |  |
| 05 §8 | `module` — a Module.hh program | 05 §10 |  |
| 05 §9 | `delphes` — DelphesHepMC3 | 05 §11 |  |
| 05 §10 | `herwig` — Herwig 7 | 05 §12 |  |
| 05 §11 | `sherpa` — Sherpa 3 | 05 §13 |  |
| 05 §12 | `whizard` — Whizard 3 | 05 §14 |  |
| 05 §13 | `madgraph` — MadGraph5_aMC@NLO | 05 §15 |  |
| 05 §14 | Plot backends | 03 §9 |  |
| 05 §15 | App_Pythia — `utils/App_Pythia.cc` | 05 §16 |  |
| 05 §16 | App_yd2rt — `utils/App_yd2rt.cc` | 05 §17 |  |
| 05 §17 | Paint | 05 §18 | inside (pages, modes) → 06 §20 |
| 05 §18 | `Module.hh` | 06 §21 |  |
| 05 §19 | `Status.hh` and the status protocol | 06 §22 |  |
| 05 §20 | `filters.toml` | 06 §23 |  |
| 06 §1 | Repository layout | 06 §1 |  |
| 06 §2 | The build | 06 §15 |  |
| 06 §2.1 | The rules | 06 §15.1 |  |
| 06 §2.2 | `// requires:` | 06 §15.2 |  |
| 06 §2.3 | The flag cache | 06 §15.3 |  |
| 06 §3 | The runner, inside | 06 §3 | the flows → 06 §5 |
| 06 §4 | The tool-folder contract | 06 §16 |  |
| 06 §4.1 | `tool.toml` | 06 §16.1 |  |
| 06 §4.2 | `render.py` | 06 §16.2 |  |
| 06 §4.3 | How the runner uses a folder, per point | 06 §16.3 |  |
| 06 §5 | Adding a standard tool | 06 §17 |  |
| 06 §6 | Adding a plot backend | 06 §18 |  |
| 06 §7 | Writing C++ | 06 §24 |  |
| 06 §8 | Tests | 06 §25 |  |
| 06 §9 | Conventions | 06 §26 |  |
| 06 §10 | Changing things safely | 06 §27 |  |

## Verification

- `source ~/HEP/setup.sh` first; one pytest session at a time.
- Each step:
  - `python3 -m pytest -q tests/runner/test_docs.py` and `make test` pass;
  - `make docs` is a no-op straight after (the currency test).
- M1 S1: `hep explain plot.band` and `hep explain figure.class` print the moved notes. `diff` of `run.schema.json` shows only the descriptions.
- M2: every complete TOML block loads; every figure example matches a fixture the slow suite draws (`tests/integration/test_plot_stage.py`).
- M3: `test_every_cited_section_exists` passes over the remapped code; `grep -rn '0[1-6]_' utils tests bots` finds no old page name; the inventory has no unmapped heading.
- Commits stay local, never pushed, with the Co-Authored-By line. `configs/` and the user's files are untouched; no rebuilds.
