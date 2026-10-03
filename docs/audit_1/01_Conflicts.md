# 01 — Conflicting patterns

These are places where two parts of `utils/` do the same thing in different ways, or where the code contradicts a rule the manual states. Config-facing conflicts come first, since they are what the user meets. Paths are relative to `utils/Env/runner/` unless given in full.

---

## C1 — The core names tools, though the rule says it never does

**The rule.** BOT.md and 02 §3: *"Everything the runner knows about a tool lives in `utils/Env/<tool>/`. The runner core never names a tool."* `tools.py` repeats it in its docstring: *"This module never names one."*

**What the code does:**

| Where | Tool knowledge in the core |
|---|---|
| `tools.py:120, 318, 335, 951`, `quantities.py:120` | `tool.tool in ("custom", "module")`: these two get a config file, export requests, and config-key mappings |
| `tools.py:754-776` | `"analyses" in tool.extra`: Rivet's `name:OPT=V` syntax, built into card rendering |
| `tools.py:857-884` | Parses Rivet `.info` files for `Options:` |
| `tools.py:940-944` | `gives = ["plugin_path"]` hard-codes `build/Rivet` |
| `execute.py:150-151` | `"pythia_cmnd" in data["standard"]` and `rivet_threads`, to estimate cores |
| `post.py:102, 515` | `tool="merge"` and `.yoda` products for `combine` |
| `quantities.py:181-221` | LHAPDF and Pythia `pSet` checks (`check = "pythia_pdf"`) |
| `plot.py:334-356, 419-441` | `rivet-config --datadir` (twice), `.plot` files, `App_yd2rt.exe` |
| `record.py:40` | Pythia's seed range, applied to every generator (C12) |

**Why it matters.** Adding a tool like Geant4, or an analysis application other than Rivet, means editing core modules in several places. The rule is good. It just isn't enforced, so it has eroded one V-entry at a time.

**Fix.** L6 (the declarative contract) and B2 (provider plugins).

---

## C2 — The run TOML's schema lives in five places

A key's name, type, default and allowed values are written down separately in each of these:

| Fact | Where it is written |
|---|---|
| Run and configuration keys and their types | `config.py:24-47` (`RUN_KEYS`, `CONFIGURATION_KEYS`, `PLOT_KEYS`, …) |
| Plot child keys and types | `plot.py:44-50` (`TITLE_KEYS`, `OBJECT_KEYS`, `OBJECT_TYPES`, `OVERLAY_KEYS`, `DATA_KEYS`) |
| Plot defaults | `plot.py:606-623` (`y_gutter` 0.5, `auto_range` true, …) **and** `Paint/Page.hh:139-144` (the same values again) |
| `formats` default | `plot.py:55` `["pdf"]`, `Page.hh:141` `{"pdf"}`, `cli.py:52` `"pdf,png"` (file mode), and mkhtml writes pdf and png regardless |
| Allowed `formats` | `plot.py:39`, `Draw.hh:412`, `yoda/backend.py:37` |
| Legend positions | `plot.py:40`, `Style.hh:375`, `yoda/backend.py:38` |
| Style choices (`font`, `errors`) | `plot.py:59` (`STYLE_CHOICES`), `Style.hh:345, 359`, and the comments in `base.toml` |
| Tool option kinds | `tools.py:325` (its own type map), separate from `config.py:148` (`_type_name`) |
| The user-facing reference | docs/04's tables, held to `config.py` by `tests/runner/test_docs.py` |

**What it costs.** V51 (titles) touched `config.py`, `plot.py` (three tuples), `Page.hh`, `Draw.hh`, `yoda/backend.py`, `base.toml` and docs/04. Adding one key costs about seven edits, and each one is a chance for the copies to drift. The `formats` default has already drifted: `hep plot FILE` gives pdf and png, but `[plot]` gives pdf only.

**Fix.** B1 (one schema file, read by both languages, as `base.toml` already is for the style).

---

## C3 — Naming in `[run]`: one word, several jobs

| Key / field | What it actually is |
|---|---|
| `[run].name` | The run folder: `<project>/<name>/` |
| `[run.<cfg>].name` | Overrides the run folder for this configuration (V46). Same key, a different scope |
| `[run.<cfg>].label` | The configuration's folder, `NN_<label>`. Stored as **`Configuration.name`** (`config.py:406`) |
| `Configuration.run_name` | Holds `[run.<cfg>].name` |
| `[run.<cfg>].title` | The `run NN - <title> -` header |
| `Configuration.key` | The table key, which is what the CLI takes |
| `[run].configuration` | The default configuration |
| `[run].sweep_runs` / `[run.<cfg>].swept` | Run every configuration / opt this one out |
| `sweeps` | The quantities swept *within* a configuration |

So `name` in the file is not `name` in the model. "Swept" means two unrelated things (a configuration taking part in `sweep_runs`, and a quantity being swept), and the CLI addresses a configuration by its key while its folder shows the label.

**Fix.**
- Rename the model fields to match the file: `Configuration.label` and `Configuration.folder`.
- Rename `swept` → `in_sweep_runs`, or turn it around: `sweep_runs = ["a", "b"]` lists the members, which also fixes the order.
- Let the CLI accept a label as well as a key.

---

## C4 — Seven parent→child inheritances, four merge rules

| Inheritance | Rule today | Where |
|---|---|---|
| `[run]` → `[run.<cfg>]` scalars | Child wins, key by key, written out by hand for each key | `config.py:405-421` |
| `[static]` → `[run.<cfg>].static` | Merged key by key | `config.py:420` |
| `[prelim]` → `[run.<cfg>].prelim` | **Replaced whole**: the child drops every parent key | `config.py:421` |
| `[plot]` → `[plot.object."<glob>"]` | Every matching glob `update()`s in file order, so the last match wins, not the most specific | `plot.py:588-591` |
| `[plot]` → `[plot.overlay.<n>]` | Child wins; no globs | `plot.py:586-587` |
| style: base → `root_style` → `[plot.style]` → object style | Deep merge | `plot.py:214` |
| `master.toml` → project master | Shallow, per quantity entry | `quantities.py:62-64` |
| Rivet options: inline `photo_eic:R=0.4` → `[tools.x].options` → quantity | **The general table beats the specific inline option** | `tools.py:759-762` |

The last row is a real inversion (**C4a**). A tool-wide `options = { R = 1.0 }` silently overrides `analyses = ["photo_eic:R=0.4"]`, which goes against the "child overrides parent" principle the rest of the framework (V51) follows. The `[prelim]` row is a trap too: adding `prelim = { files = [...] }` to one configuration silently drops the file-level `fifo` list.

**Fix.** L1: one resolver, one rule. Deep-merge every layer, let the most specific layer win, and allow an explicit `"default"` to clear an inherited value.

---

## C5 — The `"default"` sentinel and its neighbours

- `"default"` is accepted only in `[plot]`, its children and the style (`config.py:437` exempts those values from type checks entirely).
- Gutters have two spellings for the same thing: `0` and `"default"` (`plot.py:102`, `Page.hh:151`).
- Threads use a third convention: `0` means every core (`config.py:249`).
- `"default"` means "the drawing tool decides" (V37) for some keys and "the runner's own default" for others. `page_settings` (`plot.py:599-604`) passes both an `ours` and a `native` value for each key, so a reader has to know which one a key uses.
- `use_data = "default"` is treated as true by `settings.get("use_data", True) is not False` (`plot.py:509`), by accident rather than by design.

**Fix.**
- One sentinel, with one meaning everywhere: **`"default"` = keep it as it is** (the user's decision, 2026-10-03).
  - **In a child** (`[run.<cfg>]`, `[plot.object]`, an overlay, a style layer, a configuration's `static`): inherit the parent's value, the same as leaving the key out.
  - **At the top level:** set nothing. No card line, no flag, no page key. The tool uses its own default, or fails if it needs the input.
- A key that is *left out* at the top level still takes the runner's default from the schema (B1), e.g. `y_gutter = 0.5`. Only an explicit `"default"` hands the decision to the tool.
- A key the runner owns (seed, events, outputs) refuses `"default"`.
- This retires V37's meaning, where `"default"` at any level overrode the parent with the tool's value.
- Drop `0` as a synonym for unset in gutters.

---

## C6 — Keys the plan owns: refused in some cards, overridden silently in others

| Tool | A base card that sets a key the plan owns (seed, events, beams, outputs) |
|---|---|
| Sherpa | **Refused** (`sherpa/render.py:78, 124-128`) |
| Whizard | **Refused** (`whizard/render.py:162, 199-204`) |
| MadGraph | `output` and `launch` refused (`madgraph/render.py:27-34`) |
| Pythia | **Silently overridden** (append, last wins). `photo_zs.cmnd` sets `Main:numberOfEvents = 200000`, `Random:seed = 0` and `Beams:eA/eB`; the plan overrides all of them. Only the seed line's own comment says so |
| Herwig, Delphes | Silently overridden (append) |

The V39 plan noted this for Pythia's `Random:seed` and left it.

The consequence: a user who writes `Beams:eCM = 318` into a `.cmnd` gets a different result from one who sets it through a quantity, and only Sherpa and Whizard users are told. The redundancy check `_base_values` (`tools.py:818`) half-sees the issue: it spots *equal* overrides, but only for `key = value` lines (C10).

**Fix.**
- A `[card] owned = ["Random:seed", "Main:numberOfEvents", …]` list in every `tool.toml`, checked by the core for every style. A base card that sets an owned key is refused, with a hint.
- Optionally, a key the base sets and a quantity also sets, to a different value, is reported in `--plan`.
- For Pythia, L14b (parse and merge the cards) makes this a dict lookup, and it removes the duplicate lines from the card that runs. For every `append` tool, L14a writes that card without comments and blank lines.

---

## C7 — Beam order: the same value means different things per tool

`[quantities.energies].values = [[275, 18], …]` is "beam A, beam B". Whether A is the proton depends on each tool's mapping and base card:

| Tool | Mapping | Meaning of `[x, y]` |
|---|---|---|
| Pythia | `keys = ["Beams:eA", "Beams:eB"]` | A = whatever `Beams:idA` is: the card's choice |
| Herwig | `keys = ["…BeamEMaxB", "…BeamEMaxA"]`, **reversed** | So that `[E_p, E_e]` works with `EPCollider.in`'s lepton on A |
| Sherpa | `BEAM_ENERGIES` | "The card puts the proton first" |
| Whizard | `beams_momentum` | "The card names the proton first" |
| MadGraph | `ebeam1, ebeam2` | "Beam 1 is the proc card's first incoming particle" |

So `[275, 18]` is correct only because every base card happens to put the proton where its mapping expects it. Change one card's beam order and the energies swap silently, which is the kind of failure the framework otherwise refuses (C7 in the record).

**Fix.** Name the beams in the quantity, e.g. `values = [{p = 275, e = 18}]` or `[{id = 2212, E = 275}, {id = 11, E = 18}]`. The mappings then name particles (`energies = { proton = "Beams:eA", lepton = "Beams:eB" }`), and the beam's PDG id can be checked against the card's `Beams:idA`. This is a breaking config change: see B6.

---

## C8 — The path rules are broken by the code that states them

`paths.py:1-12`: *"Every key that takes a path has exactly one convention root: there is no search path and no fallback."* V13: `./` is the repository root, never the working directory.

| Where | What it does |
|---|---|
| `tools.py:181-190` | A custom `executable` is looked up under `build/<project>/`, **then on PATH**: a fallback, the thing the rule forbids. A missing build silently runs a same-named system binary |
| `plot.py:228` | `hep plot --style FILE` resolves against the **working directory** |
| `plot.py:735, 746` | `hep plot FILE…` and `-o` resolve against the working directory |
| `tools.py:523, 591, 606` | `resolve(name, "prelim" / "output" / "input", root=…)` passes keys that aren't in `ROOTS`. This works only because `root` is given; the table is incomplete as documentation |
| `hep:12`, `hep_env.sh:12` | Find the repository root by `../..` from the script; `paths.py:84` finds it by marker directories. Two discovery rules that can disagree under a symlink |

**Fix.**
- Make the PATH lookup explicit (`executable = "path:foo"`, or a separate `command = "foo"` key), and refuse the fallback.
- Document `hep plot`'s file arguments as shell paths: they are CLI arguments, not config values. That is a fair exception, but it should be written down.
- Add `prelim`, `input` and `output` to `ROOTS` with a `point` root.

---

## C9 — Three label languages, three converters

| Text | Written in | Converted by |
|---|---|---|
| Rivet `.plot` `Title`/`XLabel`/… | LaTeX (`$\mathrm{d}\sigma$`) | `tlatex()` → TLatex for Paint (`plot.py:309-332`); `macros()` and `lines_of()` for mkhtml |
| `[plot]` `title`, `legend_header`, quantity `labels` | **TLatex** (`#sqrt{s}`, `#it{Q}^{2}`) | `root_text()` for Paint (`plot.py:262`); `latex()` → mathtext for mkhtml (`yoda/backend.py:66-76`) |
| `[plot.object].x_label` override | TLatex | as above |

**Effects:**
- A user writing a label must know which source it will be mixed with.
- The yoda backend compares a TLatex header against `tlatex(LaTeX)` to decide whether it was overridden (`backend.py:176`): a round-trip comparison.
- Conversion tables (`_COMMANDS`, `_MACROS`, `_PLAIN`, `_MATH`) are scattered across two files.
- V41, V47, V48, V50 and V51 were each a fix in this pipeline.

**Fix.** B5 (one canonical label language, plus `latex.toml`).

---

## C10 — Parsing done four ways

| What is parsed | How |
|---|---|
| Run TOML, tool folders, `base.toml`, master | `tomllib` (good) |
| YODA files | **Regex** over the text (`plot.py:382, 391, 789`, `execute.py:200`), **and** the `yoda` bindings (`yoda/backend.py`), **and** `App_yd2rt` (C++). Three readers for one format, and the regexes skip `.yoda.gz` raws (`plot.py:754`) |
| ROOT files | `uproot` (`execute.py:187`, `plot.py:698`) and ROOT itself (Paint) |
| Rivet `.plot` | Hand-written block regex (`plot.py:345-353`) |
| Rivet `.info` | Hand-written line scan for `Options:` (`tools.py:869-878`), though `.info` is YAML and PyYAML is already a dependency (Sherpa uses it) |
| Base cards (for redundancy) | `key = value` split (`tools.py:827-830`): wrong for Herwig and Delphes (`set k v`), whose redundant lines are never spotted |
| `[prepare].ignore` | A regex with `(?:set\s+)?` hard-coded (`tools.py:792`) instead of being derived from `[card].line` |
| App_Pythia sidecar in C++ | `std::string::find` over the JSON (`Module.hh:440-453`) |
| Point card lines | `line_format.replace("{key}", …)` (`tools.py:678`) rather than `expand()`, the templater used everywhere else |

**Fix.**
- L4 (one YODA/Rivet layer).
- L5: derive card parsing from `[card].line`, so the same template both writes and reads a line.
- L9: one sidecar format.

---

## C11 — Plot settings are validated late, in another layer

- `config.parse` checks every section strictly, but exempts the values of `[plot]` children (`config.py:437`).
- Their checks live in `plot.validate` (rank 4), which `cli.build_plans` calls **after** every point has been planned and hashed (`cli.py:91`). A typo in `[plot.object."d01*"]` is reported only after the whole plan is built.
- Under `sweep_runs`, the typo is reported once per configuration, each time after that configuration is planned.

**Fix.** Validate in `config` from the schema (B1). Rendering stays in `plot`.

---

## C12 — Pythia's seed range is applied to every generator

`record.SEED_RANGE = 900_000_000` (`record.py:40`), also written into `config.py:183` and `App_Pythia.cc:269`. It is Pythia's limit (ledger L4). Herwig, Sherpa and Whizard seeds are drawn from it too. That works, but it is wrong in principle, and it limits a future tool whose range is smaller (Geant4's engines take a `long`; some generators want two seeds).

**Fix.** `[card] seed_range = [1, 899_999_999]` per tool folder. The runner takes the intersection over the generators in the point. The constant then exists once per tool.

---

## C13 — Exit codes

| Program | 1 | 2 | 4 | 5 | 6 |
|---|---|---|---|---|---|
| runner (`cli.py:6`) | a point failed | **config error** (also "a sweep's run could not be planned", `cli.py:212`) | — | — | stopped |
| `Module.hh:218` | config | **usage** | input | output | stopped |
| `App_Pythia.cc:74` | card | usage | — | output | stopped |
| `App_yd2rt.cc:55` | — | usage | input | output | — |
| `Paint main.cc` | page config | usage | input | output | — (literal numbers, no enum) |

The table is consistent among the C++ apps, but it exists four times, and `Paint` uses bare literals.

**Fix.** One `utils/Exit.hh` (or a namespace in `Status.hh`), and a matching `errors.EXIT` in Python (L8).

---

## C14 — Three plugin mechanisms, two loaders

- `render.py` is loaded by path through `importlib` (`tools.py:66-75`).
- `backend.py` is loaded by path through `importlib`, with a second copy of the loader (`plot.py:82-91`).
- `filters.toml` is data, and it also has a `status = "filters:<file>"` mini-syntax inside a string (`tools.py:550-553`).
- The plugins import `runner.errors` only because `utils/Env/run` puts `utils/Env` on `sys.path`, so they can't be imported from tests or other entry points without the same trick.
- `filters.toml`'s `[defaults] last_line = true`, present in all six files, is **never read** (`Folder.filters` returns only `rule`).

**Fix.** One `plugins.load(folder, name)` helper. Make the plugin API explicit (a Protocol per hook), and give `status` and `filters` two keys (`status = "filters"`, `filters = "file.toml"`). Delete `[defaults]`, or implement it.

---

## C15 — The CLI surface disagrees with itself

- `hep`'s usage lists `make <path>/<X>.exe`, but the `case` has no `make` branch, so `hep make …` fails with "unknown command" (`hep:26` vs `hep:31-61`).
- `hep_help` lists `run | watch | build` and leaves out `plot` (`hep_env.sh:139`).
- `hep plot CONFIG` and `hep plot FILE…` share one parser:
  - `--ratio`, `--style`, `--labels`, `--objects`, `--formats` and `-o` work only for files, and are silently ignored for a config;
  - `--set` works only for a config.
- Positional and optional arguments can't be mixed: `hep run eic --plain pdf` fails (argparse's `parse_args`, not `parse_intermixed_args`).
- `--only plot` exists on `run`, while `hep plot` does the same thing.

**Fix.** L12 (CLI tidy-up) and F5 (new subcommands).

---

## C16 — Two paths into the views

- During `hep run`, the views are driven by direct calls (`sink.point_started`, `tool_finished`, …).
- During `hep watch`, they are driven by the journal (`watch.follow`).
- The headings are built twice (`watch.py:215-230` and `watch.py:519-523`), and they differ. In-process, points are numbered in the order they *start* (`self.number += 1`); in watch, by their *index*. With `parallelism > 1` the two terminals show different numbers for the same point.
- `execute.py` probes optional sink methods with `hasattr(sink, "note")` and `hasattr(sink, "for_point")`, because `NullSink` lacks them.

**Fix.** B3 (journal-first: one event stream, one reducer, two renderers).

---

## C17 — Smaller inconsistencies

| Item | Where |
|---|---|
| Analysis options render bools as `"1"/"0"` hard-coded, ignoring the folder's `bools` | `tools.py:697, 755` |
| `_VERSIONS` (the version cache) is reused to cache `rivet-config --datadir` output | `tools.py:848-853` |
| `_sha` reads the whole file into memory; `tools.sha256_file` streams it. Same job, two functions | `plot.py:398`, `tools.py:170` |
| `post._yoda_product` and `plot.yoda_of` are the same function; so are `yoda/backend._base` and `plot.base_of` | `post.py:102`, `plot.py:466`; `backend.py:79`, `plot.py:375` |
| The `root_name` path rule (`:` → `__`, `=` → `-`) is written in Python and C++ | `plot.py:370`, `App_yd2rt.cc:66` |
| `__init__.py` rank table lists `status_client` (no such module) and leaves out `post` | `__init__.py:6` |
| `CARD_STYLES` accepts `"prepend"`, which then raises "arrives with … (P4 S3)" | `tools.py:46, 748` |
| `from2D(…, bool isEstimate)` takes an unused parameter | `App_yd2rt.cc:125, 142` |
| `Page.hh` ignores unknown `[page]` keys, while `Style.hh` refuses unknown style keys | `Page.hh:163-210` |
| `yd2rt` takes GLOBs positionally in convert mode, but `--select GLOB` in merge mode | `App_yd2rt.cc:243-245` |
