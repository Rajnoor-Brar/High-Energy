# 03 — Layout, paths and build

Where everything lives, how a name in a config becomes a path, and how sources become
executables. Implements *Brief §Directory Structure* and *Brief §Commands* ([00_Brief.md](00_Brief.md)).

---

## 1. The tree

```
High-Energy/
├── configs/<Project>/          run TOMLs, native base cards (.cmnd .in .yaml .sin), optional master.toml
├── modules/<Project>/          project sources for what tool chaining cannot do
│   ├── <Name>.cc               → an executable: build/<Project>/<Name>.exe
│   ├── <Name>.hh, <dir>/*.hh   headers shared by the project's sources
│   ├── Rivet_<name>.cc         → a Rivet plugin (prefix form)
│   └── Rivet/<name>.{cc,info,plot,yoda}   → a Rivet plugin (folder form, recommended)
├── utils/
│   ├── Status.hh  Module.hh               the only C++ headers: status reporting; the kit for module programs
│   ├── App_Pythia.cc  App_yd2rt.cc        single-file standard apps
│   ├── Apps/<Name>/                        multi-file standard apps (Paint)
│   └── Env/                                shell, the runner and one folder per standard tool
│       ├── hep  hep_env.sh  flags.sh  run  master.toml
│       ├── runner/                         the Python runner package
│       └── pythia/ rivet/ yd2rt/ paint/ yoda/ custom/ …   tool folders (05_Tools.md)
├── datasets/                   reference data (YODA), gitignored
├── build/                      everything compiled; disposable
│   ├── App_Pythia.exe  App_yd2rt.exe  Paint.exe
│   ├── <Project>/<Name>.exe
│   ├── Rivet/Rivet_<name>.so + .info .plot .yoda
│   ├── tests/                  compiled C++ tests
│   ├── deps/                   -MMD header dependency files
│   └── flags.mk                cached compiler/linker flags (§5.3)
├── output/
│   ├── <Project>/…             technical files: cards, logs, FIFOs, status, caches (§3)
│   └── tests/                  everything tests write
├── results/<Project>/…         products: YODA, ROOT, plots, provenance (§3)
├── tests/                      runner/ cxx/ integration/ reference/
└── docs/
```

**No `./env`** (moved to `utils/Env/`) and **no `./analyses`** (moved into `modules/<Project>/Rivet/`),
as the brief requires. `legacy/` is deleted (V20). `aux/` and the other non-framework folders are
untouched.

---

## 2. How a name becomes a path

The brief: *"automatically prefix path as expected by convention … unless begun by ./"*. Every key
that takes a path has exactly **one** convention root. There is no search path and no fallback,
because a lookup that tries several places is how v1's `00/B18` happened.

| Form | Resolves to |
|---|---|
| `name` or `sub/name` (bare) | the **convention root for that key** (table below) + `name` |
| `./sub/name` | the **repository root** + `sub/name` (V13: repo root, not the working directory, so a run is the same wherever it is started) |
| `/abs/path` | as written |
| `../x` | **an error**, with a hint to write `./…`. A relative climb depends on which root was applied, which is the ambiguity this rule removes. |

**Convention roots:**

| Key | Root for a bare name | Example |
|---|---|---|
| `hep run <config>` | `configs/` (`.toml` optional) | `hep run PhotoProduction/eic` → `configs/PhotoProduction/eic.toml` |
| `[master].master_toml` | `configs/<project>/` | `master.toml` → `configs/PhotoProduction/master.toml` |
| `[tools.*].baseconfig` | `configs/<project>/` | `photo_ep.cmnd` |
| `[tools.*].executable` | `build/<project>/`; if nothing is built there, a command of that name on `PATH` (shown by `--plan`) | `Lambda.exe` → `build/Lambda/Lambda.exe`; `python3` → the one on `PATH` |
| `[prelim].fifo`, `[prelim].files` | the **point's output directory** (§3) | `events.hepmc` |
| `[tools.*].input` | the name of a `[prelim]` entry or an earlier `output_file`; otherwise a path under the point's output directory | `events.hepmc` |
| `[tools.*].output_file` | a `[prelim]` name → the point's **output** directory; any other name → the point's **results** directory | `photo.yoda` → `results/…/<point>/photo.yoda` |
| `[plot.*].data` | `datasets/` (not in git), or `rivet:<Analysis>` for Rivet's own reference data | `rivet:ZEUS_2012_I1116258` |

**The output/results rule is the only judgement here, so it is stated once:** *an interface file*
(named in `[prelim]`) is technical and lives in `output/`. *Anything else a tool writes* is a
product and lives in `results/`. So a HepMC file kept for re-analysis goes in `[prelim] files` and
lands in `output/`, while a YODA lands in `results/`.

**Placeholders in `arguments`.** A custom tool's command line cannot be guessed, so it is written
out with placeholders the runner fills in:

| Placeholder | Is |
|---|---|
| `{config}` | the extracted `[tools.<tag>.config]` TOML for this point (also passed as the first argument) |
| `{out}` / `{res}` | the point's output / results directory |
| `{in:<name>}` / `{file:<name>}` | the resolved path of an input / `[prelim]` entry |
| `{q:<quantity>}` | the point's value of a quantity |
| `{threads}`, `{events}`, `{seed}` | from the configuration and the point's seed block |
| `{std:<tool>_<export>}` | the `path` of a requested standard configuration, e.g. `{std:pythia_cmnd}` ([04 §7.3](04_Config.md#73-standard-configurations-for-custom-tools)) |

`hep run … --plan` prints every resolved path and argument, so nothing about resolution is hidden.

---

## 3. Output and results

```
output/<Project>/<run>/<configuration>/
  points.json               every point: values, page, products, identity, seed, complete (02 §6)
  status.jsonl              every status message, for `hep watch`
  <point>/
    cards/<tag>.<ext>       each tool's rendered card: for pythia, <tag>.point.cmnd (the overrides) and
                            <tag>.cmnd (base + overrides in one file), also what exports hand out
    config/<tag>.toml       a custom tool's extracted [tools.<tag>.config]
    events.hepmc            [prelim] entries: FIFOs and agreed files
    logs/<tag>.log          stdout+stderr of each tool
    identity/<tag>          the step identity, written with the completion marker
  plots/<page>.toml         the Paint (or YODA) configuration generated per page
output/<Project>/.cache/<tool>/<hash>/   prepare caches (Sherpa/Whizard integration, MadGraph process dirs)

results/<Project>/<run>/<configuration>/
  <point>/
    <products>              photo.yoda, photo.root, delphes.root, …
    provenance.json         (V14)
    .complete               written last; its absence means the point is not done
  post/                     products of post tools
  plots/<page>.{pdf,png,svg}
```

**Directory names:**

| Level | Name | Example |
|---|---|---|
| `<run>` | `NN_<name>` when `[run].serial` is set, else `<name>` | `03_eic` |
| `<configuration>` | `NN_<name>` when `[run.<cfg>].serial` is set, else `<name>` | `01_pdf` |
| `<point>` | the swept quantities' tags joined by `_`, in `sweeps` order; `point` if nothing is swept | `27x920_NNPDF23lo` |

Serials are **location, not identity** (V12). Changing a serial starts a fresh location. Whether a
point reruns inside a location is decided by its identity (02 §7), never by its directory name.
Two points that would get the same directory name are a plan-time error, and the error names the
quantities whose tags collide.

---

## 4. `utils/` after v2

Written from scratch in P0–P3 (V5, V7). Nothing from v1's `utils/` survives as code.

| Path | What | ~Lines |
|---|---|---|
| `Status.hh` | `Status::Reporter`: JSON lines to `$HEP_STATUS_FD`, or plain stderr; heartbeat; drop-on-full; the X11 `Status` macro guard | 120 |
| `Module.hh` | the kit for `modules/<P>/*.cc` programs (05 §5) | 200 |
| `App_Pythia.cc` | the standard Pythia tool (05 §4) | 250 |
| `App_yd2rt.cc` | YODA → ROOT (05 §6) | 250 |
| `Apps/Paint/` | the ROOT plotting app (05 §7) | 900 |
| `Env/` | shell, runner and tool folders (02 §3) | 2,000 Python + tool data |

A helper that a second module needs goes into `utils/` as one more header. Until then it lives in
`modules/<P>/`. `Phys` and `ML` come back from git (`git show rework/v1-final:utils/Phys/…`) only
when a module actually needs them, as a deliberate copy and not as a dependency waiting to be used.

---

## 5. Build

### 5.1 `make <path>.exe` and `make <path>.so`

The brief: *"expect full paths, then determine output path based on conventions"*. The target is
written the way the source is: `make modules/Lambda/Lambda.exe` means *compile
`modules/Lambda/Lambda.cc`*. The output lands where the convention says:

| Source | `make` target | Output |
|---|---|---|
| `utils/App_<X>.cc` | `make utils/App_<X>.exe` | `build/App_<X>.exe` |
| `utils/Apps/<X>/` (entry `main.cc`) | `make utils/Apps/<X>.exe` | `build/<X>.exe` |
| `modules/<P>/<X>.cc` | `make modules/<P>/<X>.exe` | `build/<P>/<X>.exe` |
| `modules/<P>/Rivet/<x>.cc` or `modules/<P>/Rivet_<x>.cc` | `make modules/<P>/Rivet/<x>.so` (or `…/Rivet_<x>.so`) | `build/Rivet/Rivet_<x>.so`, plus the `.info`, `.plot`, `.yoda` copied beside it |
| `tests/cxx/<X>.cc` | `make tests/cxx/<X>.exe` | `build/tests/<X>.exe` |
| any other `<dir>/<X>.cc` | `make <dir>/<X>.exe` or `.so` | `build/<dir>/<X>.exe` or `build/<dir>/lib<X>.so` |

**Parked sources.** A folder whose name starts with `_` (`modules/Lambda/_v1/`,
a `_ref/` copy) is never built by `hep build`. It holds sources kept for reference while
their replacement is written. A single file in it can still be built by naming it explicitly.

**How the rules avoid F4's defects:**

- The target the user types is an alias for the real file in `build/`. Make's up-to-date check
  therefore works on the real file, so nothing rebuilds for no reason and nothing is left stale.
- `-MMD -MP` writes header dependencies to `build/deps/`. Editing `Reconstruction.hh` rebuilds
  `Lambda.exe` *and* `Rivet_Lamriv.so`.
- A copied `.info`/`.plot` is a real target, so editing one re-copies it (`00/B44`).
- Rivet plugins go through `rivet-build` with `-I utils -I modules/<P>`, so an analysis and a
  module program can share a project header (L20). A `.info` with `Requires: ONNX` adds the ONNX
  include path and library (`00/B37`).

### 5.2 What to link: the `requires:` line

A source says which libraries it needs, in one comment line near the top. This is the same
convention as a Rivet `.info`'s `Requires:`:

```cpp
// requires: pythia8 hepmc3
```

| Name | Flags from |
|---|---|
| `pythia8` | `pythia8-config --cxxflags --ldflags` |
| `hepmc3` | `HepMC3-config --cflags --libs` |
| `yoda` | `yoda-config --cxxflags --libs` |
| `root` | `root-config --cflags --libs` |
| `fastjet` | `fastjet-config --cxxflags --libs --plugins=yes` |
| `lhapdf` | `lhapdf-config --cppflags --ldflags` |
| `onnx` | `$ONNXRUNTIME_DIR` |
| `delphes` | `$HEP_INSTALL/delphes` |
| `toml` | `pkg-config tomlplusplus` |
| `zstd`, `zlib` | `pkg-config` |

- **No `requires:` line** means *every library that was found*. That is today's `%.exe` behaviour,
  so a quick manual compile such as `generator_comparison.cc` keeps working with no edits; it is
  just slower to link.
- **`#include "Module.hh"`** implies `hepmc3 toml`. Add `root` or `yoda` for the output the program
  writes.
- An unknown name is an error. A name whose library was not found is an error naming the
  `*-config` tool that was missing.

### 5.3 The flag cache

`build/flags.mk` holds every library's flags. It is written by `utils/Env/flags.sh`, which runs
each `*-config` once. Make includes the file instead of calling seven probes on every invocation.

**The cache records what it depends on.** Following v1's `00/B38`: the resolved path of each
`*-config`, and `HEP_INSTALL`. The Makefile regenerates it when any of those differ. `hep build
--configure` forces a rewrite.

### 5.4 `hep build`

`hep build` is `make all`:

- every `modules/**/*.cc` (executables and Rivet plugins, by the rules above);
- every `utils/App_*.cc`;
- every `utils/Apps/*/`.

Options:

- `hep build <targets…>` passes the targets through;
- `--tests` adds `tests/cxx/*`;
- `--clean` empties `build/`;
- `-j N`.

There is no configure step beyond the flag cache, and no CMake from P0 onwards (V5, V6).

**What V6 gives up**, recorded here:

- **CMake's `AUTO` components.** A missing library is reported by the `requires:` check instead
  of being switched off silently. That is arguably better (lesson: a silently ignored input).
- **ctest.** `make test` runs pytest and the C++ test executables directly.

---

## 6. Commands

| Command | Does |
|---|---|
| `hep run <config> [<configuration>]` | Load, plan, run every point, then `post` and `plot`. `<configuration>` overrides `[run].configuration`. |
| `hep run … --plan` | Print the plan without running anything: points, the quantity × tool consumer table, resolved paths and arguments, identities, seeds, and which points would be skipped. (v1's `hep plan`.) |
| `hep run … --points <sel>` | Run a subset: tags, indices or `quantity=tag`. |
| `hep run … --set <key>=<value>` | Override one value for this invocation, e.g. `--set static.energies=18x275` (v1's `--pin`). Recorded in provenance. |
| `hep run … --rerun` | Ignore skip-unchanged for this invocation. |
| `hep run … --only post` / `--only plot` | Rerun only the post tools, or only the plots, from products already on disk. (v1's `hep plot`.) |
| `hep watch [<config>]` | Attach the watch view from another terminal (reads `status.jsonl`). |
| `hep build [targets…] [--tests] [--clean] [-j N]` | §5.4. |
| `make <path>.exe`, `make <path>.so` | §5.1. |
| `make test`, `make clean` | pytest plus the C++ tests; empty `build/`. |

Shell functions from `utils/Env/hep_env.sh` stay as they are (`load_hep`, `quit`, `hep_cd`,
`hep_status`, …); only their location moves. v1's other commands are gone (V3/V4,
[01_Assessment.md §2](01_Assessment.md#2-sizes)).

---

## 7. Tests

Written fresh, small, and aimed at what can actually go wrong: physics normalisation, process
failure, and config mistakes.

| Where | What | Runs by |
|---|---|---|
| `tests/runner/` | runner unit tests: config checks (one bad file per rule), sweeps, consumers, paths, connections, identity, seeds, card rendering per tool folder | `make test` (pytest) |
| `tests/cxx/` | `Status.hh`, `Module.hh`, App_Pythia's seed and sidecar handling, yd2rt conversions, Paint's range and gutter arithmetic | `make test` |
| `tests/integration/` | real processes: the reference gate, the σ gate, failure injection, one point per standard chain | `make test-slow` |
| `tests/reference/` | **data only**: `legacy_run/` (the legacy pipeline's cards and YODAs) and `point_counts.toml` (v1's expected point and page counts) | read by the tests |

**Rules:**

- **Tests never write into `results/` or `configs/`.** They write to `output/tests/`, and
  `HEKIT_RESULTS`/`HEKIT_OUTPUT` point there.
- **Fakes must have the real type** (L26). A test that builds a fake point card uses the runner's
  own card type, not a look-alike.
- **Name `encoding="utf-8"`** on every text read and write (L17).
- **Keep tests that prove a refusal still refuses**, e.g. a FIFO feeding Delphes is rejected at plan
  time.

---

## 8. P0: delete, keep, move

The whole transition happens in P0 ([phases/P0_clean-slate.md](phases/P0_clean-slate.md)), after the
tag `rework/v1-final`.

**Delete**

| What | Lines | Why |
|---|---|---|
| `utils/` (all of it: 11 C++ namespaces, `apps/`, `python/`) | 24,009 | V5, V7 |
| `CMakeLists.txt`, `cmake/` | 591 | V6 |
| `tests/` except the reference data | ~31,000 | tests code that is gone |
| `legacy/` | 27,971 | V20; consult it through git |
| `docs/rework/`, `docs/post_rework/`, `docs/GUIDE.md`, `docs/MAP.md` | 11,600 | V20; GUIDE is rewritten in P3 |
| `modules/Examples/` | 177 | a demo of the deleted module API |
| `output/scratch/`, stale `output/PhotoProduction/*.exe/.so` (untracked) | — | scratch |

**Keep**

| What | Why |
|---|---|
| `configs/` | cards unchanged; the TOMLs are rewritten in P2 |
| `modules/Lambda/` | the physics to port in P4 (as source, until rewritten) |
| `docs/rework_v1/`, `docs/rework_v2/` | the lessons, and this plan |
| `datasets/`, `results/` (gitignored) | data |
| `bots/` | agent notes (updated) |
| `aux/`, `literature/`, `_vs/`, `_text/`, `cross_machine/`, `archive/`, `.vscode/` | not framework |

**Move**

| From | To |
|---|---|
| `analyses/<P>/<x>.{cc,info,plot,yoda}` | `modules/<P>/Rivet/<x>.{…}` |
| `env/hep_env.sh` | `utils/Env/hep_env.sh` (and the `~/HEP/setup.sh` stub repointed, with approval) |
| `tests/golden/legacy_run/` and `tests/golden/inputs/PhotoProduction/photo_ep.cmnd` | `tests/reference/legacy_run/` (the point cards, YODAs and `run.json`, plus the **frozen base card** they were made with, sha256 `63c1c13a…`; the current `configs/` card has changed since) |
| `tests/golden/test_legacy_counts.py`'s `EXPECTED_COUNTS` | `tests/reference/point_counts.toml` |
