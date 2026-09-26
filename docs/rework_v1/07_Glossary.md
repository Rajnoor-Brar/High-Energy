# 07 — Glossary

Every term the framework uses, what it means here, and the alternatives — because a name that was
chosen is only legible next to the names that were not.

[03_Conventions.md](03_Conventions.md) gives the *rules*; this gives the *words*.

**Bold** in the alternatives column marks a name the project actually considered and rejected, with
the reason. The rest are plausible alternatives, offered so the choice can be re-argued.

---

## 1. Pipeline vocabulary

| Term | Means here | Alternatives |
|---|---|---|
| **point** | one row of a sweep — one set of values, one results directory | sample, config point, job, variation, scenario |
| **group** / **generation** | the events produced once; several points may alias one | batch, generation unit, event set, **run** (taken: `[run]` is the config section) |
| **study** | a named scan (`[study.pdf]`) | scan, campaign, series, comparison |
| **page** | the set of curves drawn on one axes | figure, **canvas** (rejected with Paint/ROOT, D9), panel, plot group |
| **curve** | one point's histogram on a page | series, line, trace, entry |
| **variant** | one analysis-option combination inside a generation | flavour, configuration, instance |
| **alias** | a point sharing another's generation | sibling, co-point, shared point |
| **analyzer** | where events go: Rivet, a module, the store, the Delphes tee | **sink** (the original name; renamed 2026-09-23 — see §8), consumer, writer, observer |
| **source** | where events come from | producer, reader, **generator** (taken: `[generator]` is the tool) |
| **module** | user C++ booking YODA directly | **plugin** (taken: Rivet's word), analyzer (now taken), task, processor |
| **stage** | one supervised process, as data | step, job, task, action |
| **phase** | stages that run together; a later phase waits | wave, tier, round |
| **spec** | the resolved TOML `hep-run` reads | run card, **manifest** (taken: the study manifest), resolved config |
| **identity** | the hash deciding whether two points share events | fingerprint, signature, digest, key |
| **replica** | points differing only by seed | repeat, trial, statistical copy |
| **replay** | re-running analyzers over a stored event set | re-analysis, **rerun** (taken: `--rerun` means "ignore the skip rule") |
| **store** | sharded HepMC3 event archive | **cache** (taken: the prepare cache), event file, **dataset** (taken: `datasets/`) |
| **shard** | one file or worker slice | **chunk** (taken: the event-loop batch), partition, slice |
| **chunk** | a batch of events in the loop | **block** (taken: the seed block), batch, window |

---

## 2. Sweep vocabulary

| Term | Means here | Alternatives |
|---|---|---|
| **quantity** | a named axis with values, labels and tags | parameter, axis, variable, knob, dimension |
| **across** | which quantities vary | scan, vary, over, dimensions |
| **overlay** | the quantity drawn as curves; the rest become pages | curves, series-by, group-by, split-by |
| **pin** | hold a quantity at one value for this run | fix, freeze, hold, select |
| **static** | values held fixed by default in the config (`[static]`) | **settle** (the original name; renamed 2026-09-23 — see §8), defaults, baseline, nominal, fixed |
| **tag** | short, filename-safe token in a point name | slug, key, short name, id |
| **label** | the human/LaTeX text on a legend | **title** (taken: `.plot` `Title`), caption, legend text |
| **setting** | a generator card key → **new generation** | generator setting, card key, parameter |
| **option** | a Rivet analysis option → **shared generation** | analysis option, post-cut, knob |

The `setting` / `option` split is the most load-bearing naming distinction in the config: it decides
whether a sweep costs events. The mechanics are in [02_Design.md](02_Design.md) and the failure mode
when a module tries to use it is `00/B40`.

---

## 3. C++ conventions

| Convention | Rule | Alternatives |
|---|---|---|
| Namespace | top-level, PascalCase, no nesting | **`hekit::Core::…` nested (rejected, D16)**, `hep_`, `HE::` |
| `Events` not `Event` | **Delphes declares a global `class Event`** | `EventView`, `Ev`, **`Record`** (the legacy name, split up) |
| `Status` kept | X11 has `#define Status int`; guarded with `#ifdef Status` → `#error` | `Report`, `Progress`, **`Monitor`** (the legacy name, split up) |
| Facade + submodule | `Foo.hh` + `Foo/Bar.hh` | one header per namespace, `Foo/Foo.hh` |
| Sub-namespace | only `detail` | `impl`, `internal`, `priv` |
| Functions | `camelCase` | `snake_case` (STL), `PascalCase` (ROOT) |
| Types | `PascalCase` | `TFoo` (ROOT), `foo_type` |
| Members | `trailing_underscore_` | `m_prefix` (ROOT/Qt), `_leading` |
| Header-only | every namespace is a CMake `INTERFACE` library | compiled static libs, one shared lib |
| Registration | `HEKIT_MODULE("Name", Class)` | `REGISTER_MODULE`, static self-registrar, factory table |
| Feature guards | `HEKIT_WITH_RIVET` | `HAVE_RIVET` (autotools), `USE_`, `ENABLE_` |

---

## 4. Python conventions

| Convention | Rule | Alternatives |
|---|---|---|
| Package name | lowercase noun for *what it owns* (`plan`, `plot`, `proc`) | verb names (`planning`), `hekit_plan` |
| Commands | `<package>/cli.py`, one `COMMANDS` table | **one `cli/` package (rejected: kills the lazy import that keeps `hep --help` fast)**, entry points |
| Errors | one `HepError(message, where=, hint=)` | an exception hierarchy, error codes |
| CLI vs package | command `hep`, package `hekit` | the same name for both |

---

## 5. Files and directories

| Name | Is | Alternatives |
|---|---|---|
| `analyses/<Project>/` | Rivet plugins | `rivet/`, `plugins/`, `src/analyses/` |
| `modules/<Project>/` | C++ modules | `analyzers/` (now ambiguous), `tasks/`, `user/` |
| `results/<project>/points/<point>/` | per-point output | **`output/`** (taken: scratch), `runs/`, `data/` |
| `studies/NN_<study>/` | per-study output, serial on the study **only** | **a serial prefix on points (rejected, D11/Q3)** — a point's location must be a function of its identity |
| `analysis.yoda` | the record | `results.yoda`, `out.yoda` |
| `analysis.partial.yoda` | an interrupted run (D22) | `.incomplete`, a flag file, **`.tmp`** (taken: atomic renames) |
| `analysis.root` | the derived ROOT view (`[proc.export]`) | `histograms.root`, `out.root` |
| `run.summary.json` | what the run did | `summary.json`, `status.json` |
| `provenance.json` | how to explain the numbers | `metadata.json`, **`manifest.json`** (taken) |
| `proc.yoda`, `fits.json` | `hep proc` output | `derived.yoda`, `postproc/` |
| `output/scratch/` | everything transient | `tmp/`, `.cache/` |
| `legacy/` | the frozen previous generation | `archive/`, `old/`, `attic/`, a git tag only |

---

## 6. Reference conventions

| Form | Means | Alternatives |
|---|---|---|
| `00/B31` | audit finding 31 | `BUG-31`, `#31`, issue links |
| `D21` | decision 21 | `ADR-021`, `RFC-21` |
| `Q6` / `D-Q6` | open question | `TODO`, `OPEN-6` |
| `P8-S02` | phase 8, step 2 | `8.2`, ticket ids |
| `05 §5` | design document 05, section 5 | `EventPipeline.md#scaling`, doc slugs |

---

## 7. Concurrency

| Term | Means | Alternatives |
|---|---|---|
| `Serial` | wants the callback thread | single, exclusive, main-thread |
| `Locked` | one instance behind a mutex | synchronised, guarded, shared |
| `Sharded` | one instance per worker, merged at the end | parallel, per-worker, cloned |
| `threadSafe()` | may `process` run concurrently? | **`isReentrant()`** — Rivet's own word, and what `Reentrant:` in a `.info` means |

`threadSafe` against Rivet's `Reentrant` is the one place the project uses a different word for a
near-identical idea. Worth knowing when reading an `.info` beside a module.

---

## 8. Renames

| Was | Is | When | Why |
|---|---|---|---|
| `Sink` / `sink` / `[[sinks.module]]` | `Analyzer` / `analyzer` / `[[analyzers.module]]` | 2026-09-23 | terminology consistency across C++, config and docs |
| `settle` / `[settle]` | `static` / `[static]` | 2026-09-23 | *settle* reads as a verb; the section is a set of fixed values |

Both were mechanical and complete: the C++ namespace, the header directory (`utils/Analyzer/`), the
CMake facade (`hekit_Analyzer`), the config keys, the spec, the tests, the step files and every
document. `Core::SinkSpec` became `Core::AnalyzerSpec`.

**Two things worth revisiting**, recorded here rather than silently accepted:

- **Spelling.** The codebase is otherwise British — `normalise`, `analyse` (the stage role is
  literally `"analyse"`), `serialise`. `Analyzer` is American. `Analyser` would match the house
  style; Rivet's own `analyze()` is American, so either choice clashes with something.
- **Fit.** `Analyzer::Store` writes events and `Analyzer::Delphes` tees to a detector process —
  neither analyses anything. *Sink* covered them accurately; *analyzer* describes the Rivet and
  module cases better and the other two worse. The name now fits the common case rather than the
  whole set.
