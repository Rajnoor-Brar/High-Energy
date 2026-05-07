# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Process directives live in [bots/BOT.md](BOT.md).** That file governs plan
> approval, testing protocol, code-design philosophy, and the directory layout
> table. This file covers what the codebase *is* and how to work in it.

## Project

Lambda baryon (Λ → p + π⁻) reconstruction simulation in C++17. Pythia8 generates
events → ROOT TTree → reconstruction pass produces histograms. Two-stage pipeline
with shared utility namespaces.

## Build & run

Build system is GNU Make with a single pattern rule (`%.cc → %.exe`):

```sh
make _Lambda_Data            # builds _Lambda_Data.exe
make _Lambda_Reconstruction
make clean                   # rm -f *.exe
```

Toolchain (resolved via `root-config`, `pythia8-config`, `pkg-config tomlplusplus`):
ROOT, Pythia8, toml++. `-I./utils -I./modules` are on the include path.

Drivers (top-level `_*.cc`) and their default configs:

| Driver                       | Config                               | Purpose                              |
| ---------------------------- | ------------------------------------ | ------------------------------------ |
| `_Lambda_Data.exe`           | `configs/Lambda_Generation.toml`     | Pythia8 → ROOT file                  |
| `_Lambda_Reconstruction.exe` | `configs/Lambda_Reconstruction.toml` | Read ROOT → reconstruct → histograms |
| `_Lambda_Parallel.exe`       | `configs/Lambda_Generation.toml`     | Generation + analysis in one pass    |
| `_Lambda_Test.exe`           | (hardcoded)                          | Smoke test                           |

Run as `./_Lambda_Data.exe [config.toml]` — config arg optional; defaults exist.

> **Build status (2026-05-03):** ✗ drivers and `make test` do **not**
> build. `Config::extractConfiguration` is referenced in 4 call sites
> but never defined in `utils/Config.hh`, and `namespace Config { ... }`
> in that file is missing its closing `}`. Both blockers are tracked as
> ROADMAP **P1 (pre-flight)** and must land before any W-item below is
> verifiable. The earlier W7 fix to `_Lambda_Data.exe`
> (`declareDataObjects` restored, BuildIndex via `preCloseHook`) is still
> in tree and will resume passing once P1 lands.

## Architecture: namespace + facade pattern

The single most important convention. Every namespace `Foo` (in `modules/` or
`utils/`) has both:

- `Foo.hh` — **public facade**, a pure `#include` aggregator. No inline logic.
- `Foo/` — submodule directory holding the actual implementation headers.

**Cross-namespace code includes only the facade** (`#include "Config.hh"`),
never a sibling's submodule. Inside a namespace, submodules are split by role
(per BOT.md §Code Design): `Types.hh`, type methods, type interfacing, workers,
helpers. The codebase is header-only; there are no `.cc` files outside the
top-level drivers.

Active namespaces: `Config`, `Monitor`, `Paint`, `Physics`, `Probe`, `Record`,
`Utility` (utils), and `Lambda` (module). Dependency order roughly:
Physics → Config → Probe → Record → Lambda. See
[docs/MAP.md](../docs/MAP.md) for the full diagram.

## Data flow

1. **`_Lambda_Data`** loads Pythia8 from `configs/Lambda_Reconstruction.cmnd`,
   declares ROOT TTree branches (proton/pion + event index), runs
   `Lambda::dataGenerator` per event in parallel via `PythiaParallel::run`,
   and writes a ROOT file. *Currently broken — see REVIEW §1.*
2. **`_Lambda_Reconstruction`** uses `Config::configureProbe` to load
   `[probe].event_particles` into a `Config::ProbeConfig`, converts that to
   `Probe::CollectionSpec` via `Probe::toCollectionSpecs`, then drives
   `Probe::runParallel` over the input ROOT file. Per event it calls
   `Lambda::rootAnalysis`, which asks the `Probe::Event` for collections by
   the explicit string labels `parameters.protonLabel` / `pionLabel` (read
   from `[lambda].proton_label` / `pion_label`). Finalisation goes through
   `Record::FinalizerController`.
3. **`_Lambda_Parallel`** does both at once: `PythiaParallel::run` +
   `Lambda::pythiaAnalysis` per event (no intermediate ROOT file).

## Config system

Configure entry points:

- `Config::configuration(path, project, watch, reg)` (`utils/Config.hh`) — base
  TOML→Watch+Register parse. `Register` is now a transitional working buffer
  consumed by `Record::configureWriter`; consumers outside `Config` see the
  Writer, not the Register.
- `Config::configurePythia(path, project, watch, reg, pythia)` — adds `[pythia]`.
- `Config::configureProbe(path, project, watch, reg, probe)` — adds `[probe]`
  parsing into a `Config::ProbeConfig`. Used by the reconstruction driver.
- `Record::configureWriter(writer, project, path, watch, reg, probeFile?)`
  (`utils/Record/Writer.hh`) — opens the output `TFile`, populates
  `Record::Paths` + `Record::HistConfig` + `Record::Meta::Record` (priority:
  defaults → TOML → Probe extraction). Drivers call this after
  `configureProbe`/`extractConfiguration`.
- `Config::extractConfiguration` — *currently missing*. Drivers call it but
  it is not defined; ROADMAP P1.1 adds the alias. Will become redundant
  once W2's `Config::configure` facade lands.

Driver-facing types after the W7 refactor: `Config::Watch` (live counters /
pacing), `Record::Writer` (output TFile + paths + hist config + meta).
`Config::Register` is internal scaffolding — drivers construct it but only
pass it to Config readers + `configureWriter`; never read it themselves.

Three-tier resolution inside `configuration()`:

1. Defaults from `configs/defaults/Monitor.toml`
2. Limits from `configs/General_Limits.toml` (required) then
   `[lambda].hist_limits` (e.g. `Lambda_Limits.toml`)
3. User TOML overrides

Standard sections: `[events]`, `[probe]` (with the new nested
`event_particles` form — see MAP.md), `[record]`, `[record.paths]`,
`[record.file]`, `[lambda]`, `[pythia]`, `[monitor]`/`[log]`. An async
monitor thread (`utils/Monitor/`) renders progress and detects stalls.

The central per-run state is `Config::Watch` (atomic `iEvent`, `mutex`,
non-copyable, non-movable; per-event accounting via `Watch::recordEvent(now)`,
snapshots via `Watch::freeze() → unique_ptr<Watch>`). The legacy
`Config::Log` / `Config::Root` aliases are gone — use `Config::Watch` /
`Config::Register` directly.

## Reference docs

- [docs/MAP.md](../docs/MAP.md) — full file map, line counts, namespace dependency graph
- [docs/Architecture.md](../docs/Architecture.md) — strategic plan-of-plans (W1–W10)
- [docs/ROADMAP.md](../docs/ROADMAP.md) — active execution plan; opens with P1 build-unblock
- [docs/REVIEW.md](../docs/REVIEW.md) — open backlog of additions/removals/restructures
- [docs/DataFlow.md](../docs/DataFlow.md) — TOML key inventory, end-to-end flow
- [docs/Gemini/](../docs/Gemini/) — parallel-agent observations (PROPOSAL.md,
  ConfigReport.md, DataPath.md, Plan_ProbePArticle.md). Treat as proposals,
  not as ground truth.
- [bots/BOT.md](BOT.md) — process directives, directory layout, code-design rules
- [bots/lessons.md](lessons.md) — accumulated pitfalls (lower priority than BOT.md / user instructions)

## Testing

Per BOT.md §Testing: redirect output paths from `outputs/` to `outputs/test/`
during test runs; restore only after explicit pass or user instruction.
