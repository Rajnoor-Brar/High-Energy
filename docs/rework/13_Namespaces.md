# 13 — Namespaces and packages

Date: 2026-09-17 · Status: Proposed · Decision D16 (house style)

## 1. House style (from `bots/BOT.md`)

- **Top-level namespaces only.** They use PascalCase, and there is no sub-namespacing unless it clearly helps readability (only `detail` for internals).
- **Facade plus submodules.** Each namespace `Foo` has a facade `utils/Foo.hh` exposing its primary functions, and a directory `utils/Foo/` for submodules.
- **Submodule roles:** `Types.hh` · type methods · type interfacing (initialisation, import/export) · workers · helpers.
  - Submodules build linearly on each other and include as little as possible.
  - Other namespaces normally only need `Types.hh`.
- **Include path:** `-I utils`. Cross-namespace code includes the facade or `Foo/Types.hh`.

**New rules for this rework:**
- **No `using namespace`** of `Pythia8`, `Rivet`, `HepMC3`, `fastjet` or `YODA` at namespace scope in our headers or sources. Function-local `using` declarations are fine. This keeps `Event`, `Run` and friends unambiguous.
- **Names are checked against the installed toolchain** before adding a new top-level namespace (table in §3).
- **Optional components** (Rivet, HepMC, ONNX, Delphes) live in their own submodules or classes, so that switching a component off removes whole files (09 §1).

## 2. C++ namespaces

**Dependency layers.** A lower layer never includes a higher one.
```
Core ─► Status ─► Events ─► { Store, Results, ML, Phys } ─► { Source, Module } ─► Sink ─► Run ─► apps/hep-run.cc
```

| Namespace | Facade | Submodules (planned) | Purpose | External libs | Replaces | Step |
|---|---|---|---|---|---|---|
| `Core` | `Core.hh` | `Types`, `Spec`, `Errors`, `Signals`, `Clock`, `Sha256`, `Paths`, `Provenance` | Resolved-spec reader (structure only), exit-code mapping, signals (`sigaction`), clocks, hashing, repo-root discovery, provenance record | toml++ | `Config`, `Utility` | P2-S03 |
| `Status` | `Status.hh` | `Types`, `Writer`, `Heartbeat`, `Plain`, `Timer` | JSON lines on fd 3, heartbeat deadline loop, plain fallback, optional scope timers | — | `Monitor` (facts only) | P2-S03 |
| `Events` | `Events.hh` | `Types` (`View`), `Convert`, `Weights` | Per-event view: live `Pythia8::Pythia*` (optional), lazy `HepMC3::GenEvent`, weights | HepMC3, Pythia8 (optional) | — | P2-S04 |
| `Store` | `Store.hh` | `Types` (`Index`, `Shard`), `Writer`, `Reader`, `Compression`, `Queue` | HepMC3 event store: sharded writer and reader, index, bounded queue | HepMC3, zlib (zstd) | `Probe` | P5-S01/S02 |
| `Results` | `Results.hh` | `Types`, `Booker`, `Worker`, `Merge`, `Writer` | YODA booking per worker, merge, scaling contract, atomic writes (`.tmp` + rename, `analysis.partial.yoda`) | YODA | `Record` | P2-S05, P8-S01 |
| `ML` | `ML.hh` | `Types`, `OnnxModel`, `Features` | ONNX Runtime sessions with per-worker scratch | ONNX Runtime | — | P8-S03 |
| `Phys` | `Phys.hh` | `Types`, `Pdg`, `Kinematics`, `Select`, `Jets` | PDG traits, kinematics on `FourVector`, selectors on `GenEvent`, jet definitions | HepMC3, FastJet | `Physics` | P8-S02 |
| `Source` | `Source.hh` | `Types`, `Pythia`, `StoreReplay`, `Stream` | Event sources: Pythia (cards, LHE), store replay, FIFO/file HepMC | Pythia8, HepMC3 | `generator.cc` loop | P2-S04, P5-S02, P7-S01 |
| `Module` | `Module.hh` | `Types` (`Module`, `Context`), `Registry`, `Loader` | User analysis modules, `HEKIT_MODULE` registration, `dlopen` loader | — | `modules/Lambda` scaffolding | P8-S01 |
| `Sink` | `Sink.hh` | `Types` (`Sink`, `Needs`, `Concurrency`), `Rivet`, `Store`, `Modules`, `Delphes` | Sink interface and implementations | Rivet, HepMC3, YODA, Delphes (optional) | — | P2-S05, P5-S01, P8-S01, P7-S08 |
| `Run` | `Run.hh` | `Types` (`Context`, `Result`), `Loop`, `Concurrency`, `Checkpoint` | Wires source → sinks; serial/sharded; chunking; stop; merged σ; `RunResult` | Pythia8 | `Config::configure<Pipeline>` | P2-S04, P6-S01 |

**Class naming inside namespaces.** Short nouns, because the namespace carries the context: `Sink::Rivet`, `Sink::Store`, `Source::Pythia`, `Source::StoreReplay`, `Store::Writer`, `Results::Booker`, `Events::View`, `Run::Result`.

## 3. Clash check (installed toolchain, 2026-09-17)

| Name | Finding | Resolution |
|---|---|---|
| `Event` | Delphes declares a global `class Event : public TObject` (`delphes/include/classes/DelphesClasses.h:46`). `Pythia8::Event` and `Rivet::Event` become ambiguous under `using namespace`. | Namespace is **`Events`** |
| `Status` | `/usr/include/X11/Xlib.h:83` has `#define Status int`. No toolchain header pulls in Xlib. | Keep `Status`; `Status.hh` starts with `#ifdef Status` → `#error "X11 Status macro defined before Status.hh"` |
| `Run` | `Rivet::Run` exists; it only clashes under `using namespace Rivet` | Keep; covered by the no-using rule |
| `Core`, `Source`, `Store`, `Results`, `Sink`, `Module`, `ML`, `Phys` | No global or macro clashes found in the ROOT, Pythia, Rivet, YODA, HepMC3, FastJet, LHAPDF, ONNX or Delphes headers | Keep |
| Legacy `Config`, `Monitor`, `Probe`, `Record`, `Paint`, `Physics`, `Utility`, `Lambda` | Leave the include path when moved to `legacy/` (P0-S06) | No coexistence problems |

## 4. Python packages (`utils/python/hekit`, CLI `hep`)

| Package | Holds | C++ counterpart | Step |
|---|---|---|---|
| `hekit.cli` | click groups (no logic) | `apps/hep-run.cc` | P1-S01 |
| `hekit.errors` | `HepError(msg, where, hint)` | `Core/Errors` | P1-S01 |
| `hekit.config` | `schema`, `load`, `layer`, `validate`, `migrate`, `reference` | — | P1-S02, P1-S06 |
| `hekit.sweep` | `quantity`, `select` (across, settle, study, pins), `expand`, `pages` | — | P1-S03 |
| `hekit.plan` | `model`, `build`, `naming`, `hashing`, `seeds`, `spec` (writer + `spec_v2.json`) | `Core/Spec` (reader) | P1-S04, P1-S05 |
| `hekit.adapters` | `base`, `pythia`, `rivet`, `store`, `sherpa`, `whizard`, `madgraph`, `herwig`, `delphes` | `Source` | P1-S05, P5-S02, P7 |
| `hekit.run` | `supervisor`, `transport` (FIFO), `status` (reader), `parsers`, `signals` | `Status` | P3-S02 |
| `hekit.term` | `dashboard`, `plain`, `events` (tables/trees), `theme` | — | P3-S04, P5-S03 |
| `hekit.results` | layout, manifests, skip rule, YODA model, `stats`, `compare` | `Results` | P3-S03, P4-S01, P4-S04 |
| `hekit.store` | index model, `ls`, `verify`, `info` | `Store` | P5-S01 |
| `hekit.plot` | `io`, `select`, `transform`, `data`, `plotfile`, `backends/{mkhtml,mpl}`, `styles/` | — | P4 |
| `hekit.proc` | `models`, `backends/{minuit2,roofit,scipy}`, `hist` (rdf/uproot) | — | P9 |
| `hekit.prov` | `git`, `versions`, `provenance`, `stamp` | `Core/Provenance` | P1-S07, P3-S03 |
| `hekit.env` | `paths`, `doctor`, `lhapdf`, `tools` | `Core/Paths` | P1-S01, P1-S07 |

## 5. Old → new

| Old | New |
|---|---|
| `Config::` | `hekit.config` (validation) + `Core` `Spec` (reading) |
| `Monitor::` | `Status` (facts) + `hekit.term` (rendering) + `hekit.run` (stall detection) |
| `Record::` | `Results` (YODA) + `Core` `Provenance` |
| `Probe::` | `Store` + `Source::StoreReplay` + `Phys` selectors |
| `Paint::` | `hekit.plot` (+ `hekit.proc` for fits) |
| `Physics::` | `Phys` |
| `Utility::` | `Core` |
| `Lambda::` | archived (`legacy/lambda/`); a future module |
| `rivpyth_common` | `config`, `sweep`, `plan`, `adapters`, `results`, `plot` (see 00b) |
