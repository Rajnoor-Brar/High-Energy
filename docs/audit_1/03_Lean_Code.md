# 03 — Leaner code: merge repeated code, move lookups into data files, standardise parsing

Each item says what to merge or move, where it goes, and roughly how many lines it saves. The savings are estimates from reading the code, not measurements.

The rule throughout is the one `master.toml` and `base.toml` already follow:

- **A fact the user or a tool author might change lives in a data file.**
- **Code that follows from such facts reads them, and never repeats them.**

---

## L1 — One layered resolver

**Repeated today:**
- `config.py:405-421` spells out `table.get(k, run.get(k, default))` by hand for `serial`, `name`, `seed_type`, `manual_seed`, `threads`, `parallelism`, `static` and `prelim`;
- `plot.py:595-604` has `pick()` / `plot_only()` with `ours` and `native` defaults;
- `plot.py:214` has `merge_style()`;
- `quantities.py:62-64` overlays the master;
- `tools.py:757-762` merges analysis options.

That is five implementations with four rules (C4).

**One function:**

```python
def resolve(key, layers, *, schema):
    """The value of `key` through `layers` (most specific first): the first layer that sets it wins;
    tables deep-merge. "default" in a child is the parent's value (as if the key were absent); at the
    top level it is UNSET: nothing is written, and the tool decides (C5, the user's rule)."""
```

`schema` (B1) says, for each key, whether it inherits, whether it deep-merges or replaces, its runner default when absent, and what "unset" means for its consumer (no card line, no flag, no page key). Then:
- `Configuration` is built as `{k: resolve(k, [cfg, *extends, run.defaults, run]) for k in schema.configuration}`;
- `page_settings` becomes `resolve(k, [overlay_or_object, plot])`;
- the style layers, the master overlay and the analysis options become calls to the same function.

**Saves** about 80 lines, and makes F1 (`extends`) and F2 (`include`) free: they are just more layers.

---

## L2 — Hard-coded tables that belong in data files

| Table in code | Where | Move to |
|---|---|---|
| `RUN_KEYS`, `CONFIGURATION_KEYS`, `PRELIM_KEYS`, `QUANTITY_KEYS`, `TOOL_COMMON`, `PLOT_KEYS` | `config.py:21-47` | `utils/Env/schema/run.toml` (B1) |
| `TITLE_KEYS`, `OBJECT_KEYS`, `OBJECT_TYPES`, `OVERLAY_KEYS`, `DATA_KEYS`, `LEGENDS`, `FORMATS`, `STYLE_CHOICES` | `plot.py:39-60` | `schema/run.toml` (plot section) and `base.toml` (choices beside each key) |
| The page defaults (`y_gutter` 0.5, `auto_range` true, `ratio_label` "Ratio"/"MC/Data") | `plot.py:606-623`, `Page.hh:139-144` | `schema/run.toml` defaults, written into every page TOML, so `Page.hh` keeps no defaults of its own |
| `_COMMANDS`, `_MACROS`, `_PLAIN` (LaTeX → TLatex, YODA macros) | `plot.py:252, 282, 286` | `utils/Env/latex.toml` |
| `_MATH` (TLatex → mathtext) | `yoda/backend.py:42` | `latex.toml` |
| `LEGEND` (corner → mkhtml keys), `FORMATS` (→ `-f` flags), `HONOURED` | `yoda/backend.py:37-43` | `utils/Env/yoda/backend.toml`, the backend's own folder file |
| `OWNED` keys | `sherpa/render.py:78`, `whizard/render.py:162` | `[card] owned` in each `tool.toml` (and new for Pythia, Herwig and Delphes: C6) |
| `LPP` (PDG → MadGraph lpp) | `madgraph/render.py:22` | `[render.lpp]` in `madgraph/tool.toml` |
| `SEED_RANGE` | `record.py:40`, `config.py:183`, `App_Pythia.cc:269` | `[card] seed_range` per `tool.toml` (C12) |
| `/RAW/`, `/TMP/`, `/_XSEC`, `/_EVTCOUNT` | `plot.py:61, 384, 393, 715, 791`, `App_yd2rt.cc:168` | One constant in the YODA layer (L4); yd2rt takes the list as an argument or reads `latex.toml`'s sibling `yoda.toml` |
| Package list, `*-config` probes, version probes | `hep_env.sh:17, 78-90`, `flags.sh:14, 247-259`, `Makefile:44` (`KNOWN`) | `utils/Env/stack.toml` (B7) |
| Colour names (`kBlue` → 600) | `Draw.hh:78-81` | Keep: ROOT's own constants, and stable |
| `BUILTIN = ("events", "threads")` | `quantities.py:26` | `master.toml` (`[builtin] events = …`), next to their mappings |

**Saves** about 150 lines of Python and C++. More importantly, a style choice, a format, a legend corner, a macro or an owned key becomes a one-line data edit, as a `base.toml` key already is.

---

## L3 — Functions written twice

| Twins | Keep |
|---|---|
| `plot.yoda_of` (`plot.py:466`) · `post._yoda_product` (`post.py:102`) | One `plan.product(suffix=".yoda")` method on `PointPlan` |
| `plot.base_of` (`plot.py:375`) · `yoda/backend._base` (`backend.py:79`) | `plot.base_of`, imported |
| `plot._sha` (whole file in memory) · `tools.sha256_file` (streamed) | `sha256_file`, cached (L10) |
| `plot.objects_of` · `plot._gz_objects` (`plot.py:382, 789`) | One reader that opens `.gz` transparently (L4) |
| `plot.convert` · `plot.merge` (`plot.py:402, 443`): both run `App_yd2rt`, check `build/App_yd2rt.exe` and stamp a sha | One `yd2rt(argv, target, stamp_inputs)` |
| `tools.Folder.plugin` · `plot.backend` (two `importlib` loaders) | `plugins.load(folder, "render" \| "backend")` |
| `rivet-config --datadir`: `plot.py:338`, `plot.py:426`, `tools.py:845-853` (via `_VERSIONS`) | `rivet.data_dirs()`, cached once |
| Page document: the object loop (`plot.py:522-547`) and the overlay loop (`plot.py:558-577`) build the same `{"file", "object", "raw", "label"}` curve dict and write the same TOML | `_curve(plan, full, label)` and `_write_page(rel, document, …)`: about 35 lines saved |
| Headings: `PlainView.heading` (`watch.py:215`) · `follow()` (`watch.py:519-523`) | One `heading(point, stage, index, total)` (or B3) |
| `post.plan_pre` / `plan` / `plan_combined` and `run_pre` / `run` / `run_combined` | L7 |
| JSON by hand: `jsonList`, `jsonNumbers`, `perOutput` (`App_Pythia.cc:206-224`), `Module::finish` report (`Module.hh:408-414`), `Status::summary` callers | A 40-line `Json::Object` builder in the C++ kit (L8) |
| Argument parsing: `App_Pythia` (`--k v`), `Module::Job` (`--k=v` or `--k v`), `App_yd2rt`, `Paint` | One `Args` helper in the kit (L8) |
| `_check()` type check (`config.py:155`) · `_check_options()` (`tools.py:315`) · `plot.validate` `OBJECT_TYPES` loop · `check_style` (`plot.py:181`) | One validator over the schema (B1) |
| `Tool(...)` constructor (`config.py:352-359`) repeats `TOOL_COMMON` field by field | `Tool(**normalised(table))`, with fields generated from the schema, or at least from `dataclasses.fields(Tool)` |

---

## L4 — One access layer for YODA and Rivet

A rank-0 module, `runner/hepfiles.py` (the name is open):

```python
def yoda_objects(path) -> dict[str, Obj]       # yoda bindings; .gz transparent; cached by (path, mtime)
def pages_of(path) -> list[str]                # 1D, not /RAW or /TMP, not counters, nominal weight only
def raw_twins(path) -> set[str]
def event_count(path, obj="/RAW/_EVTCOUNT")    # replaces execute.read_count's regex
def rivet_dirs() -> list[Path]                 # build/Rivet + rivet-config --datadir, once
def analysis_info(name) -> dict                # the .info as YAML (PyYAML is already a dependency)
def plot_keys(yoda_path) -> dict               # the .plot blocks, as labels_of does now
```

**Replaces:**
- three regex readers of YODA text;
- the hand-scanned `.info` (`tools.py:857-884`);
- the `.plot` parser;
- the three `rivet-config` calls;
- `yoda/backend.py`'s direct `yoda.read` calls.

**Prerequisite.** The `yoda` Python module must be importable wherever the runner runs. `load_hep` already guarantees that, and the yoda backend depends on it today. Keep the regex readers only as a fallback, or drop them.

**Note on C++.** `App_yd2rt` stays: ROOT output needs C++. But the `root_name` mangling rule should be stated once, in `yoda.toml` (`[names] replace = {":" = "__", "=" = "-", " " = "_"}`). The Python side reads it, and the C++ side reads it via toml++, or takes it as an argument.

---

## L5 — One templater, and a parser derived from the card line

`tools.expand` (`tools.py:125-155`) is a hand-written scanner. It sits beside three `.replace()` templaters:
- `tools.py:678`: the card line;
- `tools.py:1038, 1042`: `{seed}` and `{prepared}` substituted after the fact;
- `yoda/backend.py`: f-strings into generated Python.

**One `Template` class** on `string.Formatter`:
- `parse()` already splits `{name:arg}` into a field and a format spec, which carries the `{partial:output}` namespace;
- override `get_field` for the namespaces, and `format` for list splicing;
- use it for argv, env, cwd, footer, seed lines, `[prelim].commands` and the card line.

**Deferred placeholders** (`{seed}`, `{prepared}`) become a second context applied by `finalise`, rather than a string replacement over rendered lines.

**The inverse of `[card].line`.** Compile `line = "set {key} {value}"` into a regex, `^\s*set\s+(?P<key>\S+)\s+(?P<value>.*)$`. With it:
- `_base_values` (`tools.py:818`) works for Herwig and Delphes too, which C10 shows it doesn't today;
- `_prepare_key`'s ignore pattern (`tools.py:792`) stops hard-coding `(?:set\s+)?`;
- C6's owned-key check uses the same parser.

**Saves** about 40 lines, and gives one behaviour everywhere.

---

## L6 — Tool facts the core hard-codes, as data

Each row is a core `if` (C1) and the folder key that replaces it:

| Core code today | Folder key instead |
|---|---|
| `tool.tool in ("custom", "module")` → write a config file, accept export requests, map unknown quantities to config keys (4 places) | `[tool] config_file = true` (custom, module), plus `accepts_exports = true` |
| `"analyses" in tool.extra` → render `name:K=V`, check `.info`, hash `Rivet_<a>.so` (`tools.py:754-776, 857-884`) | `[options] analyses = { kind = "analyses" }`, with a `render.py` hook `analyses(rendered, options) -> argv, identity` in the rivet folder |
| `gives = ["plugin_path"]` → `build/Rivet` (`tools.py:943`) | `[exports.analyses] values = { plugin_path = "{repo}/build/Rivet" }`: a template, not a keyword |
| `"pythia_cmnd" in data["standard"]` → threads + `rivet_threads` (`execute.py:150`) | `[tool] cores = "{threads}"` (generators), and for custom/module a `cores` key in their table, defaulting to 1 |
| `tool="merge"` and `.yoda` for `combine` (`post.py:515`) | `[combine] tool = "merge"`, `product = "yoda"` in `master.toml`, or in the folder whose products combine merges |
| LHAPDF and `pythia_pdf` checks (`quantities.py:181-221`) | `utils/Env/lhapdf/provider.py` (B2); master entries say `check = "lhapdf:bare"` / `"lhapdf:pythia"` |
| Analysis options' `"1"/"0"` bools (`tools.py:697, 755`) | `[options] bools = ["1", "0"]` in the rivet folder |

After this, `grep -nE '"(rivet|pythia|merge|custom|module|lhapdf)' runner/*.py` should return nothing. Make that a test, beside `test_imports.py`.

---

## L7 — Stages: point, pre, post and combined are one thing

`post.py` has three planners and three runners. They differ only in:

| | Name | Inputs | Upstream | Runs when |
|---|---|---|---|---|
| point | the tags | quantities | `pre` | always (unless complete) |
| pre | `pre` | none | none | before the points |
| combined | the kept tags | the group's products | the group | its points are complete |
| post | `post` | every point's products | every point | every point is complete |

A `Stage(kind, name, tools, inputs, upstream, ready)` and two generic functions, `plan_stage()` and `run_stage()`, cover all four. `cli.run_one`'s orchestration (about 80 lines of branching on `args.only`) then becomes a loop over `[pre, *points, *combined, post]`, each with a `ready()` predicate.

**Saves** about 120 lines across `post.py` and `cli.py`. It also makes a fifth stage (F8's replica top-up, or a fit) cheap.

---

## L8 — A small C++ kit shared by every app

Add `utils/Kit.hh`, or grow `Status.hh` (one namespace each, per V7):

- `Exit`: one enum used by `Module`, `App_Pythia`, `App_yd2rt` and `Paint` (C13);
- `Args`: `--key value`, `--key=value`, flags and positionals, with usage text. It replaces four hand-written loops;
- `Json::Object`: `.add("written", n).add("outputs", list)`, used by the sidecar, the module report and `Status::summary` callers;
- `Json::read(path)`: a flat-object reader. Or, better, L9;
- `kSeedMax`, if the seed range stays in C++ at all (C12 moves it to `tool.toml`, and the app then takes `--seed-max`).

**Saves** about 120 lines of C++.

---

## L9 — One format for sidecars and reports

`App_Pythia` writes a JSON sidecar. `Module.hh` reads it back with `std::string::find` (`Module.hh:440`). `Module` writes `<output>.json` by hand, and Python reads both with `json`.

**Option A.** Keep JSON, and add the 40-line reader to the kit (L8).

**Option B (bolder).** Write sidecars and reports as **TOML**. toml++ (already linked by every kit program) reads and writes it, Python's `tomllib` reads it, and it is the framework's language everywhere else. The cost is migrating `execute._settle`, `read_count`'s `json:` reader kind (it would become `toml:`) and the tests that read sidecars.

---

## L10 — Planning cost

| Cost | Where | Fix |
|---|---|---|
| `sha256_file(step.exe)` for every step of every point, and of every base card and `Rivet_*.so` | `tools.py:658, 744, 775` | Cache by `(path, st_size, st_mtime_ns)` for the process |
| Under `sweep_runs`, every configuration is planned twice: once up front, once at its turn | `cli.py:186-188, 233` | Keep the up-front plan; re-plan at its turn only if the TOML's mtime changed |
| `cmd_run` loads the TOML, then `build_plans` loads it again | `cli.py:177, 76` | Pass the loaded `RunConfig` |
| `_shard` rewrites `run` and `configuration` per point | `tools.py:395-463` | Per configuration (the rewrite doesn't depend on the point), then cached |
| One `Paint.exe` process per page, and a second per page for `--dump-ranges` when yoda is also drawn | `plot.py:667, 676, 781` | B4: batch mode |

---

## L11 — `Step` and `PointPlan` are carrying too much

`Step` has 30 fields (`tools.py:241-272`) covering five concerns: process, I/O, card, prepare and identity. `identity_parts` is an untyped dict with a private key (`"_flags"`) that is set at `tools.py:776` and popped at `tools.py:981`.

**Split:**
- `Step` (`tag`, `tool`, `folder`, `group`, `exe`, `argv`, `env`, `cwd`, `log`, `status`);
- `IO` (`inputs`, `outputs`, `products`, `sidecar`, `count_check`);
- `Card` (`base`, `lines`, `point`, `combined`, `key_lines`);
- `Prepare` (`dir`, `argv`, `card`, `needed`);
- a typed `Identity`.

This makes the shard rewrite, the prepare cache and the identity independently testable, and makes it obvious what the seed basis hashes (`record.py:96-97` filters `identity_parts` by key name today).

---

## L12 — The CLI

- Use `parse_intermixed_args` (C15): one line.
- Split `hep plot` into `hep plot CONFIG [CFG]` and `hep overlay FILE…` (or `hep plot --files`), each with the options that apply to it. The shared options (`--formats`, `--style`, `--ratio`) then work in both, through `--set plot.formats=…` in config mode.
- Add `make` to `hep`'s case (a one-line `exec make -C "$root" "$@"`), or drop it from the usage.
- Add `plot` to `hep_help`.
- Remove `--only plot`, now that `hep plot` exists, or keep it as an alias and document it as one.

---

## L13 — Dead and stale code

| Item | Where |
|---|---|
| `[defaults] last_line = true`, never read | all six `filters.toml` |
| `status_client` in the rank table (no such module); `post` missing from it | `runner/__init__.py:6` |
| `"prepend"` card style, accepted and then refused | `tools.py:46, 748` |
| The `isEstimate` parameter | `App_yd2rt.cc:125, 142` |
| The `if run.tools[tag].tool not in folders(): folder_of(...)` guard, which only raises | `tools.py:494-496` |
| `_VERSIONS` used as a general cache | `tools.py:848` |
| The `--seeds` flag of `App_Pythia`, unused by the runner (seeds go in the card) | `App_Pythia.cc:127`; keep it if documented for manual use, else drop it |

---

## L14 — Point cards: written clean, and for flat formats merged rather than appended

**Today** (`tools.finalise`, `tools.py:1057`), the combined card of an `append`-style tool (Pythia, Herwig, Delphes) is the base cards' raw text with the point card concatenated after it:
- every comment and blank line of the base is kept;
- every key the plan sets appears twice. `photo_zs.cmnd`'s `Main:numberOfEvents = 200000` sits above the runner's real value, and only the order says which one wins.

`cards/<tag>.cmnd` is meant to be the card that ran, but it is hard to read as one. There are two steps, both asked for by the user (2026-10-03).

### L14a — A clean append, for every `append` tool

When the combined card is written:
- drop full-line comments and blank lines from the base cards;
- drop trailing comments where the format has them;
- keep the settings in order, followed by the point card's own lines.

| Folder | Full-line comment | Trailing comment | Note |
|---|---|---|---|
| Pythia | lines not starting with a letter or digit (Pythia itself ignores them): `!`, `#`, `*`, … | ` ! …` after the value | Every line in `photo_zs.cmnd` has this form |
| Herwig | `#` | none: `#` may appear inside a value | Strip only lines starting with `#` |
| Delphes (Tcl) | `#` at the start of a command | `;#` | Only lines starting with `#`; never strip inside `{ … }` text |

- **Folder keys.** The rule comes from `[card]`. `comment = "!"` is already there; add `full_line = "^[^A-Za-z0-9]"` (Pythia) or `"^\s*#"` (Herwig, Delphes), and `trailing = "\s+!.*$"` (Pythia only).
- **Headers.** One header line is kept: `! point card for [tools.pythia], point X, written by hep run`, plus one `! from <base file>` line before each base's settings. That way the card still says where its lines came from.
- **Unchanged.** The base files on disk stay as they are, and the identity is unchanged. Comments are already left out of `card_lines` for the seed basis, and the base files' hashes are taken from the files themselves.
- **Effort.** About 20 lines in `finalise`, plus a test per folder: a card with comments and blank lines gives a combined card without them, and the same events.

### L14b — Pythia: parse and merge, and write the card from scratch

For a flat `Key = value` format, the point card is built as data rather than text:

1. **Parse** each base card into an ordered dict (`{"PDF:pSet": {"value": "13", "from": "photo_zs.cmnd:34"}}`).
   - Keys are normalised the way Pythia does: case-insensitive, whitespace removed.
   - Booleans are compared as booleans (`on` = `true` = `1`).
2. **Merge** the plan's values: quantities, built-ins and seeds. A key the plan sets is **moved to the end**, not replaced in place. A `Tune:pp` line resets other settings when it is read, so a value placed before it would be lost. Moving overridden keys to the end keeps today's "the plan wins" semantics, without the duplicate.
3. **Write** `cards/pythia.cmnd` with each key once, and `cards/pythia.json` with each key's value and origin (base file and line, or `[quantities.pdf] = NNPDF23lo`, or `built-in events`, or `seed`).

**What it gives:**
- **C6 for free.** A key the plan owns is a dict lookup, refused or reported by name. `[card] owned` stays the list, and `_base_values` (`tools.py:818`) goes.
- **A better identity.** The identity hashes the merged dict, not the card text, so a comment or a reordering in a base card no longer reruns every point.
- **`--why` (F3) per key.** For example, `PDF:pSet: 13 → LHAPDF6:NNPDF23_lo_as_0130_qed`.
- **`--show-config` (B9) for cards.** The JSON is the "every value with its origin" view.
- **One card mechanism.** Pythia moves onto the path Sherpa already takes (`sherpa/render.py`: parse the base, merge, write the card whole). The style becomes `[card] style = "merge"` with a parser per folder (`merge.py`: `parse(text) → entries`, `write(entries) → text`), and Sherpa's `render.py` becomes its YAML instance.

**What the parser must respect:**
- **Repeatable commands are kept verbatim and in order, never merged by key:** particle-data `id:onIfAny`, `onIfAll`, `onIfMatch`, `offIfAny`, `addChannel`, `oneChannel`, `all`, `new`. Several `23:onIfMatch` lines all apply, so a dict would keep only the last. This list lives in `pythia/tool.toml` (`[card] repeatable = [...]`).
- **`Main:subrun`** starts a block of its own. Refuse it, or keep the card as `append`.
- **Unknown keys** are not the parser's to judge. Pythia rejects them at `init`.

**Sturdier option.** `App_Pythia --resolve CARDS…` reads the base cards with Pythia itself and prints its changed settings as JSON (Pythia's `Settings::writeFile` writes exactly the changed ones). Case, booleans, tunes and typos are then Pythia's own rules, and the Python parser is only the fallback when the binary isn't built. Whether particle-data changes can be exported the same way needs checking before relying on it. Until then, the repeatable lines above are carried as text.

**Where it doesn't fit.**
- **Herwig:** a ThePEG script (`cd`, `create`, `insert`, `read`, `set` with relative paths, `saverun` last). Only absolute `set` lines could be merged.
- **Delphes:** nested Tcl (`module X { … }`).
- **Whizard and MadGraph:** already rendered from scratch, in their own way.

These stay `append`, made clean by L14a. For them, the line-template parser (L5) can still warn when an override duplicates a base-card line with a different value.

---

## L15 — Quantities: a central vocabulary, per-tool mappings, and validation by the tool

`master.toml` mixes two jobs: it names quantities, and it maps them into every tool. Nothing says what a quantity's value must look like, and nothing checks a native key except the tool at start-up. Split the jobs into layers, each answering one question:

| Question | Answered by | Where |
|---|---|---|
| What does `energies` mean (shape, unit, order)? | A central **vocabulary** | `utils/Env/quantities.toml` |
| How does a tool consume it? | The **tool's folder** | `utils/Env/<tool>/quantities.toml` (or `[consumes]` in `tool.toml`) |
| Is `Key = value` a line, and is it the same key as another? | The folder's **card grammar**, by syntax alone | `[card] line`, `[card] repeatable`, key normalisation (L14b) |
| Is the key real? Does PID 1000822080 exist? | **The tool itself** | `[checks] card = ["{exe}", "--check", "{card}"]`, run at plan time and cached by the card's hash |
| Which config key may write a native setting, and which wins? | One **precedence rule** | Below |

```toml
# utils/Env/quantities.toml: meanings, shared by every tool
[energies]
shape = ["float", "float"]          # beam A, beam B (the convention of B6)
unit  = "GeV"
doc   = "Beam energies"

[beams]
shape = ["pdg", "pdg"]

# utils/Env/pythia/quantities.toml: how Pythia consumes them
energies = { keys = ["Beams:eA", "Beams:eB"] }
beams    = { keys = ["Beams:idA", "Beams:idB"], check = "pdg" }
pdf      = { key = "PDF:pSet", check = "lhapdf:pythia" }
```

**No hand-written lists of supported keys.** Pythia alone has thousands of settings, and a card can define particles of its own. A heavy-ion beam `1000822080` depends on Pythia's particle table, and a nucleus missing from it needs an `id:new` line earlier in the card. Only a reader that processes the card in order gets this right, and Pythia's own reader does. `App_Pythia` already reports rejected settings (`readFile` returns false, `App_Pythia.cc:245`). A `--check` mode reads the card without `init()` and prints the rejected lines. The runner maps each one back to its source, a base file and line or a quantity, using L14b's origins.

**Other tools:**
- Herwig's `read` step checks its own card;
- tools with no checker fail at start-up, as they do today.

**Generated key lists** (Pythia ships XML docs listing every setting, which can be compiled into `build/keys/pythia.json` at build time) are for editor completion and did-you-mean hints, never a gate.

**Precedence for native settings** (later wins):

| Order | Source |
|---|---|
| 1 | base card(s) |
| 2 | `[tools.<tag>.settings]` (**new**: fixed native settings with no base card needed, e.g. `"HeavyIon:mode" = 1`) |
| 3 | quantities: static, then swept |
| 4 | keys the runner owns (seeds, events, threads, outputs): refused from layers 1–3 (C6) |

**Rules:**
- Two sources in the *same* layer setting one key is an error, as `claim()` already does for quantities.
- A value of `"default"` in layers 2–3 writes nothing (C5).
- `cards/<tag>.json` (L14b) records each value and its origin.

---

## L16 — A Pythia kit in `utils/`, shared by `App_Pythia` and the integrated programs

K1 and K2 (07): `modules/PhotoProduction/Inproc/` copies `App_Pythia`'s σ combination (L1), its event stamping (L2), its card setup, `processAsync`, its chunking (L6) and its converter per instance, and it has already drifted. It lacks the L4 seed check and resolves the thread count differently.

**Move them into `utils/PythiaRun.hh`:** one namespace (V7), with `requires: pythia8 hepmc3`. It holds:
- `Xsec combine(instances)`;
- `class Stamper` (numbering, run info, re-stamp, held events);
- `Setup readCards(pythia, cards, threads, events, seeds)`, with the L4 check and the thread resolution;
- `run(pythia, requested, onEvent, stop)`, with the L6 chunking.

`App_Pythia.cc` becomes its output handling (sinks, deal groups, sidecar) on top, and `Inproc/Engines.hh` its Rivet feeding on top.

**Saves** about 150 lines across the two programs. More importantly, the integrated program's events become identical to the chain's by construction, not by a claim. `tests/integration/test_modules_p4.py` checks that equivalence today.
