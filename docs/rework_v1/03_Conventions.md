# 03 — Conventions

The rules you must follow to add something without breaking the shape. Each says what it *is* and,
where it matters, what goes wrong if you ignore it.

---

## 1. Folder organisation

```
High-Energy/
├── analyses/<Project>/        Rivet plugins            .cc + .info + .plot (+ .yoda)
├── modules/<Project>/         C++ analysis modules     .cc
├── configs/<Project>/         TOML configs + native cards
├── datasets/                  reference data (YODA)
├── utils/                     ── the C++ half ──
│   ├── <Namespace>.hh         facade, one per namespace
│   ├── <Namespace>/           submodules
│   ├── apps/hep-run.cc        the only executable
│   └── python/hekit/          ── the Python half ──
├── tests/{cxx,python,integration,tools}/
├── docs/{rework,post_rework,rework_v1}/, GUIDE.md, MAP.md
├── env/hep_env.sh             the versioned shell environment
├── legacy/                    the frozen previous generation
├── build/                     cmake, never committed
├── output/scratch/            everything transient
└── results/<project>/         the only place run output lives
```

**The load-bearing rules:**

| Rule | Why |
|---|---|
| `analyses/` and `modules/` are **globbed by project directory** | Adding a file needs no build-system edit. New project = new directory. |
| `legacy/` is tracked, readable, and **never included from** | Copy or adapt. An `#include` from `legacy/` would resurrect the thing being replaced. |
| `output/scratch/` holds everything transient | Tests and dry runs never write into `results/` or `configs/`. Enforced by a pytest guard. |
| `results/` is the only output root | Overridable by `HEKIT_RESULTS`, which is how tests get their own. |
| `build/` is disposable | Every artefact is reproducible from a source file plus `hep build`. |

---

## 2. C++ conventions

### Namespaces

- **Top-level only, PascalCase, no nesting.** `Core`, `Status`, `Events`, `Store`, `Results`, `ML`,
  `Phys`, `Source`, `Module`, `Sink`, `Run`. The only sub-namespace permitted is `detail`.
- **Facade plus submodules.** Namespace `Foo` has a facade `utils/Foo.hh` exposing its primary
  functions and a directory `utils/Foo/` for the pieces. Cross-namespace code includes the facade or
  `Foo/Types.hh`, never a deeper header.
- **Submodule roles, in order:** `Types.hh` → type methods → interfacing (init, import/export) →
  workers → helpers. They build linearly and include as little as possible.
- **Include path is `-I utils`.** Every include is `"Foo.hh"` or `"Foo/Bar.hh"`.

**Names are checked against the installed toolchain before being adopted.** This is not
bureaucracy — it caught two real clashes:

| Wanted | Clash | Resolution |
|---|---|---|
| `Event` | Delphes declares a *global* `class Event : public TObject`; `Pythia8::Event` and `Rivet::Event` then become ambiguous | the namespace is **`Events`** |
| `Status` | `/usr/include/X11/Xlib.h:83` has `#define Status int` | kept, and `Status.hh` opens with `#ifdef Status` → `#error` |

### Style

- **Header-only.** Every namespace is a CMake `INTERFACE` library. There are no `.cc` files in
  `utils/` except `apps/hep-run.cc`.
- **`camelCase` functions**, `PascalCase` types, `snake_case_` trailing-underscore members.
- **No `using namespace`** of `Pythia8`, `Rivet`, `HepMC3`, `fastjet` or `YODA` at namespace scope.
  Function-local `using` declarations are fine. This is what keeps `Event` and `Run` unambiguous.
- **C++17.** `ML/Types.hh` carries a hand-rolled `Floats` because `std::span` is C++20.
- **Optional components live in their own submodules**, guarded by `HEKIT_WITH_*`, so switching a
  component off removes whole files rather than carving up a shared one.

### The link graph is the layering

Each namespace is an `INTERFACE` library naming exactly its allowed dependencies:

```cmake
target_link_libraries(hekit_Status  INTERFACE hekit_Core)
target_link_libraries(hekit_Events  INTERFACE hekit_Status Pythia8::Pythia8)
target_link_libraries(hekit_Module  INTERFACE hekit_Results hekit_Phys hekit_ML)
target_link_libraries(hekit_Sink    INTERFACE hekit_Results hekit_Store hekit_Module)
```

**This is why the C++ layering held and the Python one did not.** A rule a build system enforces is
a rule; a rule in a document is a hope. Two violations in 6,837 lines, against four cycles in
16,853 lines of Python with no declared rank.

---

## 3. Python conventions

### Package shape

- **A package is named for what it owns**, as a noun: `config`, `plan`, `run`, `plot`, `proc`.
- **Commands live in `<package>/cli.py`** and are registered in one table:

  ```python
  COMMANDS = {"run": ("hekit.run.cli:run", "P3-S05", "generate and analyse the points of a config")}
  ```

  The entry carries the **step that introduced it** and its one-line help. A command not yet
  implemented raises `NotImplementedYet(command, step)` rather than being absent.
- **Imports inside a command are deferred on purpose.** `hep --help` must not import ROOT,
  matplotlib or uproot. This is a real constraint, not laziness — and it is also load-bearing in a
  way that is a known weakness (§7).

### Errors

**One error type.** `HepError(message, where=…, hint=…)`; `hekit.cli` catches it, prints
`render()`, exits 2. Nothing else in the package prints error text.

```python
raise HepError("[plot] merge = \"yodamerge\" only combines statistically equivalent runs",
               where=str(config.path),
               hint="every scanned quantity must have type = \"seed\"; this scan has pdf")
```

`where` is a config key, a file or a point name. `hint` says **what to do**. A message without a
hint is acceptable; a message that only restates the failure is not. `did_you_mean()` is used for
misspelled keys and command names.

### Style

- Dataclasses for anything carrying more than two values; `frozen=True` where it is a value.
- Type hints throughout, `from __future__ import annotations` at the top of every module.
- **Module docstrings carry the reasoning**, including the finding number that shaped the module
  (`plot/data.py` opens with the full story of `00/B5`). This is the project's primary form of
  documentation and it is deliberate.

---

## 4. Naming

| Thing | Convention | Example |
|---|---|---|
| C++ namespace | PascalCase, top-level, checked against the toolchain | `Phys` |
| C++ function | camelCase | `deltaPhi`, `disKinematics` |
| Python package | lowercase noun for what it owns | `adapters` |
| Rivet analysis | lowercase with underscores; file = class = plugin = config name | `photo_eic` |
| C++ module | PascalCase; file = library = `HEKIT_MODULE` name = config name | `ToyJets` |
| Project | PascalCase directory under `analyses/`, `modules/`, `configs/`, `results/` | `PhotoProduction` |
| Config | lowercase, the study family it holds | `eic.toml` |
| Quantity | lowercase, what varies | `pdf`, `pt0ref`, `energies` |
| Tag | short, filename-safe, no spaces | `MSTW08lo`, `27x920`, `pt32` |
| Point directory | `<run name>_<tag>_<tag>…`, from identity | `eic_27x920_ep_MSTW08lo_pt32_mpi` |
| Study directory | `NN_<study>` — serial on the **study only** | `studies/03_pdf/` |
| Finding | `00/Bn` (this rework) or `plans/Bn` (legacy) | `00/B31` |
| Decision | `Dn`; open question `Qn` / `D-Qn` | `D21`, `D-Q6` |
| Step | `P<phase>-S<step>` | `P8-S02` |

**The identity chain is the convention that matters most.** For a module:

```
ToyJets.cc  →  libhekit_ToyJets.so  →  HEKIT_MODULE("ToyJets", ToyJets)  →  [[sinks.module]].name
```

All the same string. The build and the config cannot drift because there is nowhere for them to
drift to.

---

## 5. Configuration

- **`schema = 2` at the top.** Migration from schema 1 is a command (`hep config migrate`), and it
  **reports what it changed** — the migration notes are preserved as comments in the migrated file.
- **Physics in the native card, never in TOML.** TOML carries run control, wiring, overrides, sweeps.
- **The schema is the documentation.** `hep config reference` generates
  [rework/reference/config.md](../rework/reference/config.md) from `schema.py`, and a test fails if
  the committed file is stale. There is no second place to update.
- **Validation is strict and early**: unknown keys are errors with `did_you_mean`; cross-field rules
  that depend on the *selection* are re-checked after the study and pins are applied (`00/B7`).
- **A quantity's `type` decides its meaning**: `setting` (a generator key), `option` (a Rivet
  analysis option), `beams`, `energies`, `pdf`, `seed`. An `option` quantity is **rejected if the
  analysis does not declare it** in its `.info` (`00/B14`).

---

## 6. Tests

```
tests/cxx/           C++ unit tests, one executable per namespace     label: cxx
tests/python/        pure-Python unit tests                           label: python
tests/integration/   the real toolchain, real subprocesses            label: slow
tests/tools/         generators of test fixtures (toy models, …)
```

Rules:

- **Never write into `results/` or `configs/`.** Use `output/scratch/` or `HEKIT_RESULTS`. A pytest
  guard enforces it; legacy tools are run from a scratch CWD.
- **`ctest -L cxx`** is the fast subset; the full run is ~5 minutes wall.
- **A test that proves a convention cannot rot is worth more than one that proves it works today.**
  `test_onnx_plugin.py` builds a probe plugin through `rivet-build` *and checks that the old flags
  still fail* — so `00/B37` cannot silently return.
- **Docs are tested.** `test_docs.py` resolves every relative link in the documentation; it caught a
  broken anchor in this very document set's predecessor.
- **Verification rows that cannot be satisfied are replaced, and the substitution is argued.** Two
  were: see [01_Philosophy.md §8](01_Philosophy.md).

---

## 7. Known convention debt

Recorded because a conventions document that only lists the rules that worked is a sales brochure.

| | |
|---|---|
| **Python has no declared layering** | Four module-level cycles; nine with deferred imports. The laziness is load-bearing — several deferred imports would become import errors if tidied to the top of the file. |
| **`results/` fuses three layers** | Layout (lowest), judgement (near-top) and housekeeping in one package. It is the junction that forces `results → plot` and `prov → results`. |
| **Five commands hand-roll the same preamble** | `load_config → select_points → build → Layout.of`, and it has already drifted: `hep compare` passes `overlay` but not `style`. |
| **`env/` is a grab-bag** | `paths.py` is a rank-0 utility living in a package that also scaffolds Rivet plugins and probes LHAPDF. |
| **Two C++ value types sit in the wrong namespace** | 9 lines (`Sink::Needs`, `Sink::Output`) cause both C++ layering violations. |
| **The module build is guarded on Rivet** | `Sink::Modules` has zero Rivet includes and YODA is unconditionally required, but the CMake guard is `HEKIT_WITH_RIVET` and it links `Rivet::Rivet`. |
| **`LegendXPos`/`LegendYPos` are parsed then ignored** by the mpl backend | The keys reach `settings` and `draw_one` hardcodes `loc="best"`. A silently-ignored style key is the class of bug `00/B5` was. |

Fixes and costs for the first five are in
[post_rework/02_Proposals.md](../post_rework/02_Proposals.md). **The single highest-value one** is
not a reorganisation: it is giving the Python half the thing the C++ half already has — a written
rank, and a test that enforces it.
