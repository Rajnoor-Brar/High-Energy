# 06 — Developer guide

How the framework is built inside, and how to extend it without breaking its shape: the layout, the
build, the runner's data model, the tool-folder contract, adding a tool or a plot backend, writing
C++, the tests, and the conventions. The design it serves is [02_Architecture.md](02_Architecture.md).

---

## 1. Repository layout

| Path | Holds | In git |
|---|---|---|
| `configs/<Project>/` | run TOMLs and native base cards; optionally a project `master.toml` and style files | yes |
| `modules/<Project>/` | programs (`<Name>.cc`), shared headers, Rivet plugins (`Rivet/<x>.{cc,info,plot,yoda}` or `Rivet_<x>.cc`); `_`-prefixed folders are parked | yes |
| `utils/Status.hh`, `utils/Module.hh` | the only C++ headers | yes |
| `utils/Env/patches/` | patches this repository needs in the `~/HEP` stack, applied by hand (each file says to which source; `fastjet-3.5.0-siscone-thread-local-ranlux.patch`: `cd ~/HEP/src/fastjet-3.5.0 && patch -p0 < …`, rebuild, `make install`) | yes |
| `utils/App_Pythia.cc`, `utils/App_yd2rt.cc` | single-file apps | yes |
| `utils/Apps/Paint/` | the multi-file Paint app, and `base.toml` (the style) | yes |
| `utils/Env/` | `hep`, `run`, `hep_env.sh`, `flags.sh`, `master.toml`, `runner/`, the tool folders | yes |
| `tests/` | `runner/` (unit), `integration/` (real processes), `cxx/`, `reference/` (data the gates compare against) | yes |
| `docs/` | this manual | yes |
| `bots/` | agent rules (`BOT.md`), the working plan, `intent.md` (ideas) | yes |
| `build/` | everything compiled: apps, `<Project>/`, `Rivet/`, `tests/`, `deps/`, `flags.mk`, `Herwig/` | no |
| `output/` | technical files per project, `output/tests/` | no |
| `results/` | products per project | no |
| `datasets/` | your own reference data | no |

The repository root is found by its markers (`configs/`, `modules/`, `utils/Env/`), or `$HEKIT_ROOT`
— never the working directory. `aux/`, `literature/` and the other non-framework folders are not
the framework's business.

---

## 2. The build

`Makefile` (160 lines), `utils/Env/flags.sh`, and `hep build` = `make all`. No CMake (V6).

### 2.1 The rules

The target is written the way the source is, and the output lands where the convention says:

| Source | Target | Output | Include path |
|---|---|---|---|
| `utils/App_<X>.cc` | `utils/App_<X>.exe` | `build/App_<X>.exe` | `-I utils` |
| `utils/Apps/<X>/main.cc` | `utils/Apps/<X>.exe` | `build/<X>.exe` | `-I utils -I utils/Apps/<X>/` |
| `modules/<P>/<X>.cc` | `modules/<P>/<X>.exe` | `build/<P>/<X>.exe` | `-I utils -I modules/<P>` |
| `modules/<P>/Rivet/<x>.cc`, `modules/<P>/Rivet_<x>.cc` | `….so`, or `rivet_<x>` | `build/Rivet/Rivet_<x>.so` + `<x>.info`, `.plot`, `.yoda` | `rivet-build … -I utils -I modules/<P> -DHEKIT_WITH_HEPMC=1` |
| `tests/cxx/<X>.cc` | `tests/cxx/<X>.exe` | `build/tests/<X>.exe` | `-I utils` |
| any other `<dir>/<X>.cc`, named | `<dir>/<X>.exe` or `.so` | `build/<dir>/<X>.exe` or `build/<dir>/lib<X>.so` | `-I utils` |

- The typed target is a phony alias of the real file in `build/`, so make's up-to-date check works
  on the real file.
- `-MMD -MP` header dependencies go to `build/deps/`: editing `Reconstruction.hh` rebuilds
  `Lambda.exe` and `Rivet_Lamriv.so`.
- A Rivet plugin's `.info`, `.plot` and `.yoda` copies are real targets: editing one re-copies it
  (00/B44). A `.info` saying `Requires: ONNX` adds the ONNX flags (00/B37, L20).
- `make all` builds every non-parked `modules/**` program and plugin, every app, and
  `build/Herwig/HerwigDefaults.rpo` (`Herwig init --repo=…`, when Herwig is on `PATH`; a failure
  warns and leaves no file, L15).
- Other targets: `tests` (the C++ tests), `test` (build and run them, then pytest without the slow
  tests), `test-slow`, `configure`, `list` (everything `all` builds), `clean`.
- Compiler: `CXX` (default `g++`), `CXXFLAGS` (default `-O2`), always `-std=c++17`.

### 2.2 `// requires:`

A source names its libraries in a comment near the top; a trailing `(…)` is a note:

```cpp
// requires: pythia8 hepmc3 fastjet   (the kit adds hepmc3 toml)
```

| Name | Flags from |
|---|---|
| `pythia8` | `pythia8-config --cxxflags --ldflags` |
| `hepmc3` | `HepMC3-config --cflags --libs` |
| `yoda` | `yoda-config --cppflags --libs` |
| `root` | `root-config --cflags --libs` |
| `fastjet` | `fastjet-config --cxxflags --libs --plugins=yes` |
| `lhapdf` | `lhapdf-config --cppflags --ldflags` |
| `rivet` | `rivet-config --cppflags --ldflags --libs` |
| `geant4` | `geant4-config --cflags --libs` |
| `toml`, `zstd`, `zlib` | `pkg-config tomlplusplus`, `libzstd`, `zlib` |
| `onnx`, `delphes` | `$ONNXRUNTIME_DIR`, `$HEP_INSTALL/delphes` |

`none` links nothing; **no line** links every library that was found (a quick manual compile keeps
working, just slower to link). `#include "Module.hh"` adds `hepmc3 toml`. An unknown name, or a
name whose `*-config` was not found, is a make error saying which.

### 2.3 The flag cache

`build/flags.mk` holds every library's flags and `FOUND`, written by `utils/Env/flags.sh`, which
runs each `*-config` once. It records a key: the resolved path of every `*-config` it used and the
two install directories. Make recomputes the key on every call and rewrites the cache when it
differs (L22: a cache keyed on less than it reads is a correctness bug). `hep build --configure`
forces it; `build/flags.log` records each probe.

---

## 3. The runner, inside

The package and its ranks are [02 §3.1](02_Architecture.md#31-the-runner). The data model:

| Type | Module | Holds |
|---|---|---|
| `RunConfig` | `config` | the parsed run TOML: `path`, `project`, `name`, `serial`, `default_configuration`, `configurations`, `prelim`, `static`, `tools`, `quantities`, `plot`, `master_toml`, `raw` |
| `Configuration` | `config` | one `[run.<cfg>]`: `key`, `name`, `serial`, `description`, `event_count`, `threads` (resolved), `sweeps`, `plot_points`, `tools`/`pre`/`post` (lists of groups), `static` (merged), `prelim` |
| `Tool`, `Quantity` | `config` | one table each; a tool's folder-specific keys and export requests are in `Tool.extra` |
| `Point` | `sweep` | `index` (1-based; −1 pre, 0 post), `name`, `choice` (quantity → value index), `page` |
| `Mapping` | `quantities` | how one quantity reaches one tool: `tag`, `form` (`key`, `keys`, `flag`, `option`, `config`, `seed`), `key`, `format`, `analysis`, `check` |
| `Override` | `quantities` | `(key, value, origin)`, a `NamedTuple`: what a `render.py` receives |
| `Folder` | `tools` | a tool folder: `name`, `dir`, `spec` (its `tool.toml`), `plugin` (`render.py`), `filters` |
| `Interface` | `tools` | `name`, `path`, `kind` (`fifo`, `file`, `product`, `pre`, `points`), `producer`, `readers`, `group`, for `points` the `paths` and `names` of every point, and `shard` (a shard's product: technical, not the point's) |
| `Step` | `tools` | one tool of one point: its folder, group, executable, argv, env, cwd, log, status mode, filters, inputs, outputs, products (final, partial), sidecar, count check, card lines and paths, config, prepare entry and argv, `identity_parts` |
| `PointPlan` | `tools` | one point (or stage): `values`, `out`, `res`, `groups` of steps, `rendered` (every step, export-only ones included), `interfaces`, `consumers`, `identity`, `seed`, `writes` (files to write), `context`, `upstream`, `deal` (a dealt interface → its group) |
| `ToolState`, `Journal`, `Reader` | `status` | what the views show per tool; `status.jsonl`; one process's pipe or log tail |
| `ToolResult`, `PointResult` | `execute` | exits, causes and messages |
| `Page` | `plot` | one page: its config path, output, cell, object, document, sources, variants, data, overrides, ranges, merged style |

**Sharding** (`tools._shard`, V31) rewrites a point's chain before anything else is planned: the
sharded table becomes `<tag>.1` … `<tag>.K` (copies of its `Tool` reading `<fifo>.s<i>.<ext>` and
writing under `output/…/shards/`), the producer's `output_file` gets the K members (rendered as a
`+` group by `_outputs_argument`), and a `<tag>.merge` step of the folder's `[shard] merge` tool is
inserted as the next group; `_retarget` points quantities aimed at the table (`target`, a
tag-keyed `key`) at every copy. The rest of planning sees an ordinary chain; the count check carries the
member's path as its key into the sidecar's `written_per_output`.

**Combine** (`post.plan_combined`, V35) plans one stage per group of points that differ only in
`combine`'s quantities, as `post.plan` plans the post stage: a `Tool` of the `merge` folder whose input
is the group's products (an interface named apart from the product, which the stage writes under its
own name), `upstream` = the members' identities, `Point.stage = "combined"` and the group's `choice`, so
`plot.pages` draws the groups as it draws points.

**The flow** (`cli.build_plans`, then `cmd_run`): `config.load` → `sweep.points` →
`post.plan_pre` → `tools.plan_point` per point → `record.identity` → `record.assign_seeds` →
`tools.finalise` (seed lines, the files to write) → `plot.validate` → `post.plan`; then
`post.run_pre` → `execute.run_point` per incomplete point → `points.json` → `post.run` →
`plot.draw`. Planning writes nothing; `execute.prepare` is the first write of a point.

**Where a check lives**: C1–C5 and C12 in `config`/`paths`; C7, C8, C10 in `quantities` and
`tools._render`; C6, C9, C13 in `tools`; C11 in `sweep`; the plot checks in `plot.validate`.
Everything raises `HepError(message, where=…, hint=…)`; nothing else prints error text.

---

## 4. The tool-folder contract

Everything the runner knows about a kind of tool is in `utils/Env/<tool>/`. The core never names a
tool: adding one is adding a folder.

```
utils/Env/<tool>/
  tool.toml       required   what the tool is and how to run it
  render.py       optional   the whole point card, for dialects [card] cannot write
  filters.toml    optional   stdout rules, for a tool without the status protocol (05 §20)
```

### 4.1 `tool.toml`

Every section and key is checked when the folders load: an unknown one is an error.

| Section | Key | Means |
|---|---|---|
| `[tool]` | `category` | one of the ten (02 §4), for reading |
| | `executable` | a command on `PATH`, or `{repo}/build/…` for our apps (must exist: "not built, run hep build") |
| | `streamable` | may read its input from a FIFO (default false) |
| | `status` | `standard`, `filters`, `none` (default none) |
| | `consumes_events` | its product's event count is checked against its input's producer sidecar |
| | `produces_events` | an event generator: its identity is the seed basis, and its `[outputs] sidecar` is its sidecar |
| `[card]` | `style` | `append` (base cards then the point card: last wins), `render` (`render.py` writes the whole card), `none` (no card; values become flags or options). `prepend` is reserved and refused (F12). |
| | `ext`, `comment` | the card's extension and comment marker (`cmnd`, `!`) |
| | `bools` | how true and false are written (default `["true", "false"]`; Pythia `["on", "off"]`) |
| | `line` | one value's line (default `"{key} = {value}"`; `"set {key} {value}"` for ThePEG and Tcl) |
| | `footer` | lines after the values (placeholders `{output_name}`, `{tag}`, `{input}`); a line whose placeholders are all empty is left out |
| | `seed`, `seed_parallel` | seed lines, after everything (`{seed}`; `{seeds}`, the block, only at threads > 1) |
| `[command]` | `argv` | the argv template (04 §10); default `["{exe}"]` |
| | `env` | extra environment (`RIVET_ANALYSIS_PATH = "{repo}/build/Rivet"`) |
| | `cwd` | where it runs (default the point's output directory; Whizard: `{prepared}`) |
| `[options]` | `<key> = { kind, required, flag, default }` | the tool-specific keys a table may carry; `kind` is `list`, `table`, `str`, `int`, `float`, `bool` or `flag` (`flag = "-e"`, `default`); every option is also a placeholder |
| `[outputs]` | `products` | the kinds it writes (for reading) |
| | `event_count` | how a count is read back: `yoda:<path>` (a counter's entries), `json:<key>` (the product's report), `root:<tree>` (a tree's entries) |
| | `sidecar` | where a producer's sidecar is (`"{output}.json"`) |
| | `written` | `"requested"`: it always makes what it is asked for or fails, so the runner writes the sidecar after exit 0 |
| | `deal` | `true`: its `{outputs}` may hold a deal group (`A+B+C`: each event to one member), so it can feed a sharded tool; its sidecar must then carry `written_per_output` |
| `[prepare]` | `argv` | the prepare step (`{repo}`, `{exe}`, `{card}`, `{prepare_card}`, `{prepared}`, `{out}`), run in the cache entry |
| | `marker` | a file the step must leave; the `.prepared` stamp is written only then |
| | `ignore` | card keys left out of the cache key (`EVENTS`, `n_events`, `seed`) |
| | `key` | `"card"` (default) or `"base"`: key on the base cards only |
| `[exports.<name>]` | `alias = "card"` | `<tool>_<name>` is `<tool>_card` |
| | `gives` | values handed over: `analyses`, `plugin_path` |
| | `path` | a path handed over (`{prepared}`, `{card}`) |
| | `needs_prepare` | asking for it runs the prepare step on demand |
| `[identity]` | `files` | files whose sha256 enters the identity (`{repo}`, `{exe}`, `{analysis}`) |
| | `version` | a command whose first line is the version, for provenance |
| `[shard]` | `merge` | the tool folder that joins K shards' products into the table's `output_file`; without it, `shards` is refused (rivet: `merge`, i.e. `rivet-merge -e`) |
| `[checks]` | `files` | files that must exist at plan time (C10) |
| | `info_dirs`, `info_dirs_command` | where analyses' `.info` files are, for C9 |

`<tool>_card` is exported automatically by every folder whose card style is not `none`.

### 4.2 `render.py`

For a card that is a tree, a script, or a launch file. Plain functions:

```python
from runner.errors import HepError        # errors, paths and quantities only (test_imports.py)

def card(bases: list[str], overrides: list, context: dict) -> str:
    """The whole point card, before seeds. `bases` are the base cards' texts in order; each override
    is the runner's Override(key, value, origin), in order; context has point, tag, output_name,
    output and base_paths. The runner adds a header comment, the [card] footer and the seed lines."""

def prepare_card(lines: list[str], bases: list[str], context: dict) -> str:   # optional
    """The card the prepare step reads ({prepare_card}), from the final point card's lines
    (seeds included); context has prepared, base_paths and tag."""
```

A value a `render.py` receives arrives through a plain `key` mapping (the master's or a quantity's);
the key means what the plugin says (a YAML path for Sherpa, a SINDARIN variable for Whizard). Refuse
a base card that sets what the plan owns (seeds, events, outputs, beams): it would silently win or
lose. Test it with the runner's own `Override` (L26).

### 4.3 How the runner uses a folder, per point

1. **Options**: the table's extra keys against `[options]` (C1), and `required` ones present.
2. **Card**: the built-in and quantity values that reach this tool (04 §8.1), each through its
   `Mapping`: `key`/`keys` become card lines (`[card] line`), `flag` becomes argv, `option` an
   analysis option, `config` a config key, `seed` a replica. Then the header, the lines, the footer;
   for `render`, `card()`. The seed lines are added at `finalise`, after the identity.
3. **Prepare key and argv**, if `[prepare]`.
4. **argv**, `env` and `cwd` from `[command]`, with every placeholder (04 §10); a module or
   custom tool's config file.
5. **Count check**, if the tool consumes events and reads a count, and its input's producer has a
   sidecar.

---

## 5. Adding a standard tool

A worked outline, for a generator `gen` that reads a card and writes HepMC to a named file:

1. **Read the ledger** ([07 §3](07_Record.md#3-the-knowledge-ledger)) and v1's adapter if there was
   one (`git show rework/v1-final:utils/python/hekit/adapters/<tool>.py`).
2. **`utils/Env/gen/tool.toml`**:

   ```toml
   [tool]
   category        = "event-generator"
   executable      = "gen"
   status          = "filters"
   produces_events = true

   [card]
   style   = "append"
   ext     = "gen"
   comment = "#"
   seed    = ["seed = {seed}"]

   [command]
   argv = ["{exe}", "--card", "{card}", "--events", "{events}", "--out", "{output}"]

   [outputs]
   sidecar = "{output}.json"
   written = "requested"            # only if it truly always makes what it is asked for

   [identity]
   version = ["gen", "--version"]
   ```

3. **`filters.toml`**: a progress rule from a real log, an error rule; nothing that fails a run.
4. **The master**: `[quantities.gen.compatible_quantities]` for the quantities it takes by name
   (`energies`, `pdf`, `events`), in `utils/Env/master.toml`.
5. **A plan-time test** in `tests/runner/` (the card, the argv, a refusal), using `helpers.raw()`,
   `parse()` and `plan()`, and a **slow gate** in `tests/integration/` that runs a point and checks
   a number (σ against the tool's own, the count check).
6. **The docs**: its section in [05](05_Tools_Reference.md), its row in 05 §1 and in the master
   table of 04 §3. `tests/runner/test_docs.py` fails if a folder has no section.

Things that decide the design of a folder: can it read a FIFO (`streamable`); does it write σ into
its events (Whizard does not); does it write exactly what it is asked for (`written = "requested"`);
is part of its work card-dependent but seed-independent (`[prepare]`); does its output path need to
be relative (Sherpa prepends `./`).

---

## 6. Adding a plot backend

`utils/Env/<name>/backend.py`, no `tool.toml`, loaded by `plot.backend(name)`:

```python
def validate(settings: dict, beside_root: bool = False) -> None:
    """Refuse, at plan time, every [plot] key this backend cannot honour (raise HepError).
    beside_root: the root backend draws too, so Paint honours the style."""

def draw(cells: dict[str, list], settings: dict, say) -> int:
    """cells: plot_points cell → its Pages (plot.Page: config, output under plots/<name>/, object,
    document, sources, variants, data, overrides, style, and ranges from Paint --dump-ranges).
    Draw them, report with say(), return the number of pages that failed."""
```

Add the name to `plot.BACKENDS`. **A key the backend cannot honour is an error**, never ignored (v1's
`LegendXPos`). The yoda backend is the example (`utils/Env/yoda/backend.py`).

---

## 7. Writing C++

- **Two headers only.** A helper a second program needs goes into `utils/` as one more header; until
  then it lives in `modules/<P>/`. v1's libraries (`Phys`, `ML`, …) come back from git only when a
  program needs them, as a deliberate copy (V7).
- **A header holds one PascalCase namespace**, checked against the installed toolchain first: X11
  `#define`s `Status` (so `Status.hh` guards it), and Delphes declares a global `class Event`.
  Functions are `camelCase`; no `using namespace` of an external library at namespace scope.
- **Every source has a `// requires:` line.**
- **An app speaks the status protocol** (`Status.hh`) and uses the exit codes of 02 §11.
- **Outputs are written atomically**: to a partial name, renamed on success. A stopped program
  writes what it has, marked partial, and exits 6.
- **Threads**: catch exceptions at the thread boundary (L3); FastJet's SISCone is not thread-safe
  (L16).
- **A module program** follows 05 §18: fill raw, scale once; a density beside Rivet (L21).

---

## 8. Tests

```bash
make test           # the C++ tests, then pytest -m "not slow" (about 30 s)
make test-slow      # real generators and plots: the gates (about 6 min)
```

| Suite | Holds |
|---|---|
| `tests/runner/` | the runner, fast: one bad config per rule (`test_config.py`), plans and connections (`test_plan.py`), paths, sweeps and the point-count gate (`test_sweeps.py`), the import ranks (`test_imports.py`), status, plot checks and the style layers (`test_plot.py`), each tool folder's cards (`test_module.py`, `test_generators.py`, `test_process_generators.py`), and the manual (`test_docs.py`) |
| `tests/integration/` | real processes: App_Pythia, App_yd2rt, Paint, the plot stage, `hep plot`, post and pre, failure injection; `@pytest.mark.slow` for the physics gates |
| `tests/cxx/` | `Status.hh` and the module kit |
| `tests/reference/` | **data only**: `legacy_run/` (the legacy Pythia → FIFO → `rivet` pipeline's cards, frozen base card and YODAs, at one thread, seed 12345) and `point_counts.toml` (the legacy point and page counts). **Never regenerate them.** |

**Rules** (also in `bots/BOT.md`):

- **Tests never write into `results/` or `configs/`.** `tests/conftest.py` points `HEKIT_RESULTS`
  and `HEKIT_OUTPUT` into `output/tests/`, and a session guard fails the run if anything under
  `results/` or `configs/` changed. Use the `scratch` fixture for files.
- **Name `encoding="utf-8"`** on every text read and write, and on subprocess output: reading a YODA
  resets `LC_ALL` to `C` (L17), and `make` runs in an ASCII locale.
- **A fake has the real type** (L26): build configs with `helpers.raw(**changes)` (dotted keys as
  `__`), `helpers.parse(data, scratch)`, `helpers.plan(data, scratch)`; a `render.py` gets the
  runner's `Override`.
- **Keep the tests that prove a refusal still refuses** (a FIFO into Delphes, an undeclared option).
- A test that needs a tool skips cleanly when it is not on `PATH` (`load_hep`) or not built.

**The manual is tested.** `tests/runner/test_docs.py` checks that every relative link in `docs/`
resolves, that every TOML block parses, that every complete run TOML example loads through the
runner's own parser, that every key the loader accepts (`config.py`'s tables, `base.toml`'s keys,
every tool folder's options) appears in the reference, and that every tool folder has its section
in 05. Change a key, and the test says which page to update.

---

## 9. Conventions

- **Errors**: one type, `HepError(message, where=…, hint=…)`. `where` is a file and key, a point or a
  path; `hint` says what to do, with `did_you_mean` for names. A message that only restates the
  failure is not enough.
- **Refuse the convenient inference.** Anywhere a correspondence could be guessed (names, paths,
  which tool a quantity is for, a data map), require it to be stated, and make a wrong one loud
  (01 §2.5).
- **Keys a consumer cannot honour are errors**, in configs, styles and backends.
- **Citations**: code cites this manual by section (`04 §9.4`) and the record by id (`L18`, `V22`,
  `C7`, `00/B5`). A new lesson learned by running something becomes a ledger row; a new decision a
  V-row. Ids are never reused.
- **Docstrings carry the reasoning**: a module opens with what it owns and why its shape is what it
  is.
- **Python**: `from __future__ import annotations`, type hints, dataclasses for anything with more
  than two values; standard library in the runner (V1), plugins import only `errors`, `paths` and
  `quantities`.
- **Names**: projects PascalCase (`PhotoProduction`); configs, quantities and tool tags lowercase
  (`eic.toml`, `pt0ref`, `pythia`); tags short and filename-safe (`27x920`, `MSTW08lo`); a Rivet
  analysis's file, class and `.info` name are one string (`photo_eic`).
- **Commits**: local, one per step of work, with the co-author line; never pushed without the user.

---

## 10. Changing things safely

- **What reruns.** Anything in a point's identity (02 §8) reruns the points it touches the next time
  they are run: a tool folder's argv or card lines, a binary (rebuilt apps, plugins), the seed rule.
  That is correct, but it costs generations: say so in the commit when a change reruns every point.
- **What does not rerun.** Plot settings, styles and base.toml: `--only plot` redraws.
- **Seeds**: changing the seed basis moves every point's seeds; `test_sweeps.py` pins that `single`,
  `pdf`'s NNPDF23lo point and `inproc` share theirs.
- **The reference gates** compare against `tests/reference/`; a change that moves them is a physics
  change and needs the user.
- **Size**: the budget and where it stands are [07 §9](07_Record.md#9-budget). Growth over 1.5× a
  part's budget is recorded with its cause.
