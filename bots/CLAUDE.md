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

> **Build is currently broken** (P0 in [docs/REVIEW.md](../docs/REVIEW.md)):
> missing `utils/Physics/TypeAid.hh`. Fix before other work.

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
   declares ROOT TTree branches via `Lambda::declareDataObjects`, then runs
   `Lambda::dataGenerator` per event in parallel and writes a ROOT file with
   proton/pion branches plus an event index.
2. **`_Lambda_Reconstruction`** opens that ROOT file via `Probe::runParallel`,
   pulls physics parameters with `Lambda::extractPhysics`, declares histograms
   with `Lambda::declareObjects`, applies `Lambda::rootAnalysis` per event, and
   finalizes through `Record::FinalizerController`.

## Config system

`Config::extractConfiguration()` in [utils/Config.hh](../utils/Config.hh) is
the entry point. Three-tier resolution:

1. Defaults from `configs/defaults/*.toml`
2. Limits from `*_Limits.toml` (e.g. `Lambda_Limits.toml`) enforce bounds
3. User TOML overrides

Standard sections: `[events]`, `[probe]`, `[record]`, `[lambda]`, `[pythia]`,
`[log]`. An async monitor thread (`utils/Monitor/`) renders progress and
detects stalls; configured via `configs/Monitor.toml`.

## Reference docs

- [docs/MAP.md](../docs/MAP.md) — full file map, line counts, namespace dependency diagram
- [docs/REVIEW.md](../docs/REVIEW.md) — current backlog (P0 build fix, P1 redundancy items)
- [bots/BOT.md](BOT.md) — process directives, directory layout, code-design rules
- [bots/lessons.md](lessons.md) — accumulated pitfalls (lower priority than BOT.md / user instructions)

## Testing

Per BOT.md §Testing: redirect output paths from `outputs/` to `outputs/test/`
during test runs; restore only after explicit pass or user instruction.
