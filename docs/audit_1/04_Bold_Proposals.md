# 04 — Bold proposals

These are larger restructurings. Each one removes a class of problem, not just an instance of it. Each gives the case, a sketch, what it deletes, the risks, and a way to migrate without a flag day. They are ordered by how much else they unlock. B1 is the foundation most of the others assume.

---

## B1 — One schema for the run TOML, read by everything

**Case.** C2, C5, C11 and L2. A key's facts are written five times, and every V-entry pays for that.

**Sketch.** `utils/Env/schema/run.toml`, in the spirit of `base.toml`:

```toml
[run.threads]
type     = "int"
min      = 0
default  = 1
inherit  = ["configuration"]          # [run] → [run.<cfg>] → extends …
zero     = "every core"
doc      = "Threads per generator; 0 = every core."

[configuration.prelim]
type     = "table"
merge    = "deep"                     # C4: no more silent replacement

[plot.y_gutter]
type     = ["float", "default"]
min      = 0
default  = 0.5                        # the runner's choice when the key is absent
unset    = "page key omitted"         # what an explicit top-level "default" does: Paint/ROOT decides
levels   = ["plot", "object", "overlay"]
doc      = "The top of the y axis at (1 + g) × the largest value."

[plot.formats]
type     = "list"
items    = { choices = ["pdf", "png", "svg", "eps"] }
default  = ["pdf"]
```

**Uses:**
- **Validation.** Convert the TOML schema to JSON Schema and validate with `jsonschema` (4.26, already in the venv: no new dependency). A thin wrapper turns each JSON-pointer error into the framework's `HepError(where=…, hint=did_you_mean(…))`, so messages stay as good as today's.
- **Resolution.** L1's resolver reads `inherit`, `merge`, `levels`, `default` and `unset` from the schema. `"default"` means "keep it as it is" (C5): in a child it inherits, and at the top level it sets nothing.
- **Paint.** The runner writes every `[page]` key explicitly, from the schema, so `Page.hh` keeps no defaults. Paint refuses an unknown or missing page key, as `Style.hh` already does for the style.
- **Docs.** docs/04's key tables are generated from `doc` (a `make docs` target), and `test_docs.py` checks that the generated tables are current.
- **Editor.** `run.schema.json` is the same file F6 needs.
- **CLI.** `hep explain <key>` (F5).

**Deletes.**
- `RUN_KEYS` … `PLOT_KEYS`, `_check` and `_type_name` in `config.py`;
- `OBJECT_KEYS`, `OBJECT_TYPES`, `TITLE_KEYS`, `DATA_KEYS`, `STYLE_CHOICES`, `check_gutter` and most of `validate` in `plot.py`;
- the defaults in `Page.hh`.

About 250 lines.

**Risks.**
- Error messages could get worse: the wrapper must be good, and the tests that pin messages will need updating.
- A schema DSL could grow into a language of its own. Keep it to the fields above.

**Migration.**
1. Write the schema for `[plot]` first, the most duplicated part, and validate with both the old code and the schema until they agree on the test configs.
2. Move `[run]` and the configurations next.
3. Delete the dicts.

---

## B2 — Providers and tool hooks: make "the core never names a tool" true

**Case.** C1 and L6. The user's original brief puts *providers* (LHAPDF, FeynRules, SARAH) first among the ten tool categories, but there is no place for them. Their checks live in `quantities.py`.

**Sketch.**
- `utils/Env/lhapdf/provider.toml` and `provider.py` expose `check(value, form, where)` and `installed()`. `master.toml` says `check = "lhapdf:bare"` or `check = "lhapdf:pythia"`. This is also where the pending check of Pythia's internal `pSet` numbers against `PDFSelection.xml` belongs.
- The rivet folder's `render.py` gets hooks: `analyses(rendered, options) → (argv, identity, config_data)`, `check(analyses)` (the `.info` option check), and `identity_files(analyses)`.
- The `custom` and `module` folders declare `config_file = true` and `accepts_exports = true`.
- The `combine` merge is a `master.toml` entry.
- A test greps `runner/*.py` for tool names and fails on any match: the rule becomes a gate, not a hope.

**Deletes.** About 150 lines of tool-specific code from `tools.py`, `quantities.py`, `post.py` and `execute.py`. It also makes the next tool (Geant4, a CMSSW-style application, a second analysis framework) a folder, not a core change.

**Risks.**
- The hook API must be designed once and kept stable.
- Over-abstracting: keep hooks to the four that exist today.

---

## B3 — Event-stream-first execution, with runtime state off disk by default (committed)

**Case.** C16. The views are fed two ways: by direct calls during `hep run`, and by `status.jsonl` during `hep watch`. V32 taught that a view must never block the run. The user has also decided (2026-10-03) that **runtime state (the watch states, the status journal, tool logs) is not stored on disk by default**, only with a flag.

**Sketch:**
- `execute` emits versioned events (`{"v": 1, "k": …}`) onto an in-memory bus: `point.started`, `tool.started`, `progress`, `tool.exit`, `point.finished`, `note`. It never calls a view.
- One reducer turns events into state. `LiveView` and `PlainView` render that state on their own thread.
- **`hep watch`** attaches through a Unix socket that the run serves in its output folder (`watch.sock`) while it runs. The socket sends the reducer's current state, then the live events. Under `sweep_runs` the same socket carries every configuration's run, which replaces the journal's `"next"` link.
- **`--journal`** also writes `status.jsonl`. Only then can a finished run be replayed, or followed with `hep watch --file`.
- **Tool output** is read from pipes, not by tailing log files, and filters match on it as it streams. By default, only the last ~200 lines of a *failed* tool are written to its point folder, which is enough to diagnose the failure. **`--logs`** keeps every tool's full log, as today.
- **On disk stay the records,** not runtime state: provenance, `points.json`, the cards, `.complete` and the products.

**Gains:**
- `hep run` and `hep watch` are identical by construction.
- `NullSink`, `_PointSink`, `for_point`, the `hasattr` probes, the second heading builder and the journal-offset scanning (`_latest_run`, `_run_since`) go.
- The run can't block on a terminal.
- Recorded journals (`--journal`) become test fixtures.
- F9 (cluster jobs) uses `--journal` on a shared filesystem.

**Deletes.** About 200 lines of `watch.py`, plus the sink plumbing in `execute.py`.

**Risks:**
- A crashed run leaves no journal unless `--journal` was given. The failed tools' log tails and the provenance remain.
- The socket path must be short: Unix sockets allow about 108 bytes. Put it in `$XDG_RUNTIME_DIR` with a link from the output folder if needed.
- The event format becomes an API: keep it versioned.
- **Open question:** whether even the failed-tool log tail should need `--logs`.

---

## B4 — The plot stack: one page document, two honest renderers, no patched scripts

**Case.** C9 and the yoda backend. It:
- regex-patches the Python that rivet-mkhtml generates, to fix ratio ticks, apply "best" legends and add titles (`backend.py:198-261`);
- runs mkhtml, then re-runs every patched script;
- copies overlay outputs out of throwaway folders;
- must refuse every style key mkhtml can't follow (`HONOURED`).

Every plot feature since V47 has cost two implementations.

**Sketch, in three steps of rising boldness:**

1. **Paint batch mode** (low risk).
   - `Paint.exe PAGE.toml…` draws many pages in one ROOT process, and writes `<page>.ranges.json` beside each one. This replaces the second `--dump-ranges` call.
   - ROOT starts once per cell instead of twice per page: tens of seconds saved on a 19-object × 4-cell sweep.
2. **Paint reads YODA directly** (medium risk).
   - Paint links YODA (already probed by `flags.sh`), and a `[[curve]]` may name a `.yoda` file and path.
   - Raw entries come from the `Histo1D` itself, so the `__entries` side histograms and the `--keep-raw` merged ROOT file are no longer needed to plot.
   - `plot.merge`, `plot.convert` and their sha stamps leave the plotting path (about 70 lines). The sweep ROOT file stays a product (the `plotmerge` tool) for whoever wants it.
3. **Replace mkhtml with a matplotlib renderer of the same page document** (high risk, high gain). **Needs a design discussion first** (the user, 2026-10-03): the exact mechanics, and a side-by-side comparison with mkhtml's output, before any decision.
   - `utils/Env/mpl/backend.py` (about 300 lines) reads the page TOML and the merged `base.toml`, which already describes mkhtml's look, and draws with matplotlib, which is what mkhtml uses underneath.
   - Ranges, voids, ratio windows, titles and legend placement come from Paint's ranges JSON, or are computed by the same rules.
   - `HONOURED` disappears: every style key is honoured by both renderers, so the backends finally agree on the look (01_Philosophy's aim of one source per fact).

**Deletes.** `yoda/backend.py`'s script surgery (`ratio_ticks`, `best_legend`, `titles`, `_finish`, the overlay folder copying, `LEGEND`, `HONOURED`), about 250 lines.

**Risks.**
- Losing mkhtml's exact output and its `index.html`. The index is F7's, and is needed by the root backend anyway.
- The matplotlib renderer must be kept in step with Paint's arithmetic. The `ranges.json` contract keeps that small.

---

## B5 — One label language (committed)

**Case.** C9. Users write TLatex (`#sqrt{s}`), Rivet writes LaTeX (`$\sqrt{s}$`), and three converters and four tables translate between them.

**Sketch.**
- **Canonical: LaTeX math in `$…$`**, the language of Rivet's `.plot` files, of matplotlib and of physicists. Every user-facing label (quantity `labels`, `title`, `legend_header`, `x_label`, overlay `labels`) is written in it.
- ROOT gets TLatex through the existing `tlatex()`, the only converter left, driven by `utils/Env/latex.toml` (`[commands]`, `[macros]`, `[upright]`).
- matplotlib reads the canonical form directly, so `latex()` and `_MATH` go.

**Migration.**
- A one-off script converts the labels in `configs/` from TLatex to LaTeX (`latex()` already does this for the common subset). It needs the user's order, since it edits `configs/`.
- For one release, a label with `#` outside math is accepted with a warning naming the converted form.

**Risk.** Every config's labels change, and the escapes (`\_`, V41) need care. That is mitigated by the script and the warning.

---

## B6 — Beam order: a positional convention the runner enforces

**Case.** C7. Energy lists are positional, and their meaning depends on each card's beam order.

Named beams (`{proton = 275, lepton = 18}`) were judged too cumbersome (the user, 2026-10-03). **The convention stays positional:** the first value is beam A and the second is beam B, and each tool's final card puts them where that tool expects them. To be decided between two options:

**Option A (recommended): the runner owns the beam pair.**
- `beams` (`[id_A, id_B]`) and `energies` (`[E_A, E_B]`) are one aligned pair, always written by the runner, and never taken from a base card.
- `Beams:idA/idB/eA/eB`, and their equivalents in other tools, become owned keys (C6).
- A folder whose card needs a fixed slot (Herwig's `EPCollider.in` puts the lepton on A) declares it, e.g. `[card] beam_slots = "lepton-first"`. Its mapping then swaps the id and the energy **together**.
- The order is consistent by construction, and no base card's beam order matters.
- **Cost:** every config must give `beams` (or a static default); base cards lose their `Beams:*` lines.

**Option B (minimal): check the convention.**
- Today's values and mappings stay.
- L14b's parser reads the base card's `Beams:idA`, and the quantity declares `order = ["proton", "lepton"]`. A mismatch is refused at plan time.
- **Cost:** small. But each tool's beam order stays a fact of its base card, and a tool with no parseable beam ids (MadGraph's proc card) stays unchecked.

---

## B7 — One registry for the software stack

**Case.** L2. The list of installed packages, and how to probe each one, is written in four places:
- `hep_env.sh` (`_HEP_PACKAGES` and per-tool version probes);
- `flags.sh` (`TOOLS` and probes);
- the Makefile (`KNOWN`);
- each `tool.toml` (`[identity] version`).

**Sketch.** `utils/Env/stack.toml`:

```toml
[pythia8]
install = "pythia8"                       # $HEP_INSTALL/<install>
flags   = ["pythia8-config", "--cxxflags", "--ldflags"]
version = ["pythia8-config", "--version"]
python  = "lib"                           # extra PYTHONPATH entry

[delphes]
install = "delphes"
flags   = { dir = "Delphes" }             # no *-config: include/lib under the install
version = { file = "bin/DelphesHepMC3" }
```

**Consumers:**
- `flags.sh` loops over it, through a five-line `python3 -c` reader or a generated `stack.sh`;
- `hep_env.sh` builds PATH and friends from it;
- the Makefile's `KNOWN` comes from `flags.mk`;
- `hep status` replaces the bash `hep_status`, printing versions from the same entries;
- `tool.toml` says `version = "stack:pythia8"`.

**Risks.** `hep_env.sh` runs at shell start-up, so it must stay fast and bash-only. Generate `stack.sh` at `hep build` time rather than parsing TOML on every login. Changes to `~/HEP` itself are not needed: only the repository files that describe it change.

---

## B8 — One scheduler for the whole run

**Status: needs a design discussion** (the user, 2026-10-03): the exact mechanics (DAG nodes, atomic FIFO groups, the core budget, how failures and stops carry over), and the expected results (wall time on a zeus sweep, before and after).

**Case.** Execution today is three nested mechanisms:
- groups within a point;
- `parallelism` across points;
- a hard-coded stage order (`pre` → points → combined → post, `cli.run_one`).

A combined group waits for every point, even when its own points finished long ago. Parallelism is a number the user computes against the core count.

**Sketch.**
- Every step of every stage is a node in one DAG. The edges are the existing ones: files between groups, FIFOs within a group (which pins the group to start together), and a stage's upstream points.
- Each node declares its cores (L6's `cores`).
- The scheduler runs any ready node while the core budget allows (`[run] cores = "all" | N`).
- `parallelism` becomes a cap, or goes away. Combined groups and post run the moment their inputs are complete.

**Deletes.** `run_points`' thread pool, the stage branching in `run_one` and `post.run_*`: about 150 lines, replaced by about 120 lines of a scheduler.

**Risks.**
- The highest of any proposal. FIFO groups must start atomically, and the failure attribution and stop ladder (L8, V32) must carry over unchanged.
- Do it only after B3 (journal-first), so the views don't care about the order, and after L7 (stages unified).

---

## B9 — Configs as layered documents: `include`, `extends`, `defaults`

This is F1 and F2 stated as one design, since together they change what a run TOML *is*.

- A run TOML is a stack of layers: `master.toml` → project `common.toml` (`[master].include`) → the file → `[run.defaults]` → the configuration's `extends` chain → the configuration → `--set`.
- L1's resolver walks the stack, and B1's schema says how each key merges.
- `--plan` gains `--show-config`, which prints the fully resolved configuration with each value's origin: `threads = 6   (from [run])`.

**Effect.** `zeus_validation.toml` shrinks by about 60%. `eic.toml` and `zeus_validation.toml` share their beams, PDFs and tool tables, and a value's provenance is never a mystery.

**Risks.** Layer order must be learnable: keep it to the list above, and print it in `--show-config`.
