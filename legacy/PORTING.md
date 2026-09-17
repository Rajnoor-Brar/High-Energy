# PORTING.md — which archived snippet goes where

Source of truth: [docs/rework/00b_PortingMap.md](../docs/rework/00b_PortingMap.md) §4–5 and the reuse map in
[docs/rework/steps/README.md](../docs/rework/steps/README.md) §9. This file is the same table with the paths as
they are **after** the P0-S06 move.

**Rule:** copy or adapt. Never `#include` or import from `legacy/` — a step that does is wrong, and the greps in
P0-S06 and P10-S01 enforce it.

## C++ (`legacy/utils/`, `legacy/misc/`)

| Archived source | Take | Target | Step |
|---|---|---|---|
| `utils/Utility/Sha256.hh` (whole) + FIPS vectors in `tests/test_utils_hardening.cc:~129-153` | copy; add a regular-file check | `Core/Sha256.hh` | P2-S03 |
| `utils/Utility/Signals.hh:22-57` + cooperative skip in `lambda/sources/_Lambda_Data.cc:43-50` | adapt to `sigaction` + atomic flag | `Core/Signals.hh`, `Run` | P2-S03, P2-S04 |
| `utils/Utility/Time.hh:15-21`, `durationString` :46 | wall vs monotonic clock aliases; plain-mode durations | `Core/Clock.hh` | P2-S03 |
| `utils/Utility/Paths.hh:25-54` | env var, else walk up to an anchor (renamed `HEKIT_ROOT`) | `Core/Paths.hh`, `hekit.env.paths` | P2-S03, P1-S01 |
| `utils/Utility/Toml.hh:75-92` | idea only: `requirePositive` with key context | `hekit.config.schema` | P1-S02 |
| `utils/Physics/Particles.hh:24-58`, `Physics/Types.hh:51-113`, `Physics/Kinematics.hh:24-41` | self-keyed trait tables with `static_assert`; PDG table; ΔR/Δφ/mass | `Phys` | P8-S02 |
| `utils/Monitor/Timer.hh` (whole; standard library only) | copy | `Status/Timer.hh` | P2-S03 |
| `utils/Monitor/Threading.hh:121-136,212-213,256-265` | deadline loop; coalescing | `Status/Heartbeat.hh` | P2-S03 |
| `utils/Monitor/Threading.hh:97-116` | stall predicates (monotonic idle ≥ threshold) | `hekit.run.supervisor` | P3-S02 |
| `utils/Record/Meta.hh:25-110,243-299` | provenance field list; git/host/compiler capture | `Core/Provenance.hh`, `hekit.prov` | P2-S03, P3-S03 |
| `utils/Record/Recording.hh:204-231` | write to a temporary file, then atomic rename | `Results/Writer.hh`, `Store` | P2-S05, P5-S01 |
| `utils/Record/Cloning.hh:31-47,82-86` | per-worker clone, merge by add | `Results` (YODA shards) | P8-S01 |
| `utils/Record/Declaration.hh` | name/shape/duplicate checks at declare time | `Results::Booker` | P8-S01 |
| `utils/Record/Type_Methods.hh:11-27` | enum-keyed ids + hash | `Results` (optional) | P8-S01 |
| `utils/Record/Threading.hh:116-236`, `Record/Lifecycle.hh:76-95` | quiesce/barrier; fatal write with timeout | `Run` checkpoints | P6-S01 |
| `utils/Probe/Lifecycle.hh:229-267` | bounded queue with backpressure, stop, workers-finished | `Source` (replay reader → consumers) | P5-S02 |
| `utils/Probe/Types.hh:148-203` | access patterns: labelled collections, typed columns, per-event scalars | `Events::View` | P2-S04, P8-S01 |
| `utils/Config/Reader.hh:79-102`, `Monitor/Configure.hh:20-60` | the "removed; use X" tables | `hekit.config.migrate` | P1-S06 |
| `utils/Paint/Resolve.hh:124-140,269-280` | preset chain with cycle detection; glob → regex | `hekit.plot` (optional) | P4-S03 |

## Configuration and style

| Archived source | Take | Target | Step |
|---|---|---|---|
| `configs/defaults/Paint.toml`, `misc/root_macros/saveHist.C:20-177` | house style: fonts 43, margins .12/.05/.12/.08, 900×600, blue palette | `hekit/plot/styles/hekit.mplstyle` | P4-S03 |
| `configs/defaults/Limits.toml` | RangeSize binning presets (GeV) | optional binning presets for modules | P8-S01 |
| `configs/templates/Record.toml:172-184`, `[record.metadata]` | naming and metadata vocabulary | provenance fields (07 §2) | P3-S03 |

## Rivet analyses

| Archived source | Take | Target | Step |
|---|---|---|---|
| `analyses/photo_{5x41,10x100,18x275}.*` | nothing: `photo_eic` reproduces them with `WMIN`/`WMAX` | — | — |
| their `.plot` files | bin ranges and axis labels, if `photo_eic.plot` ever loses one | `analyses/PhotoProduction/photo_eic.plot` | P4-S03 |

## Lambda (revival only)

| Lambda piece | Future home | Note |
|---|---|---|
| `harvestParticles` (`isFinal`, pid 2212/−211) | `Phys` selectors on `GenEvent` | add Λ̄ |
| `reconstructCandidates` | a module: pair-in-window + greedy unique | the angle cut is dead; rethink `reserved_protons` |
| `declareObjects` (21 histograms) | `Module::book` (YODA) | make the p_z range symmetric |
| the mass-peak study | `hep proc` fit (P9-S01) | a generator-level peak is a spike: smear or truth-match |
| `lambda/configs/*.cmnd` | fix before reuse | drop the ²⁰Ne redefinition, the duplicate `SigFitNGen` and the Pb `SigFitDefPar` |

## Dropped outright

`utils/Utility/{RootTypes,RootAid}.hh`, `Utility::numberString`, the directory-merge TOML helper, all of
`utils/Probe/*` readers, `Record`'s TTree/TH* writing, `Paint` rendering, and the
`Config::Register`/`Watch` scaffolding. Their roles are covered by HepMC3 (store), YODA (results) and the
Python layer (configuration, terminal).
