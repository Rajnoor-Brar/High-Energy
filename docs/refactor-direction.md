# Refactor Direction

Companion to [file-map.md](file-map.md). Captures the *shape* the codebase is moving toward and the rules that decide where things live.

---

## Guiding rules

1. **`modules/Lambda.hh` is not a mere aggregator.** It owns the analysis-callback orchestrators (`pythiaAnalysis`, `rootAnalysis`, `dataGenerator`) and the `logString` helper. The `Lambda/` subfolder holds the parts those orchestrators compose.
2. **`*Aid` headers are type-extending only.** They contain string representations, name/alias maps, enum↔string conversions, operator overloads — *no calculations, no I/O, no business logic*. If something computes a result or touches a file, it does not belong in an Aid header.
3. **Top-level `utils/` files earn their place by being entry points.** `Analysis` and `Meta` are not entry points — they are building blocks for `Extract` and `Record` respectively, and should live under those umbrellas.
4. **Cross-cutting types belong to `Config`, not `Lambda`.** Anything used by `Monitor`/`Record`/`Analysis`/`Extract` lives under `utils/Config/`.
5. **Configs split by lifetime.** Run-specific TOMLs live directly in `configs/`; baselines/defaults live in `configs/defaults/`.

---

## 1. Immediate fixes (compile / correctness)

These restore the codebase to a buildable state without committing to the larger reshuffle.

- **Create `modules/Lambda/Schema.hh`** as the umbrella header (`#include` Types, Parameters, Reconstruction, Recording) so the existing `#include "Lambda/Schema.hh"` in `Lambda.hh` resolves.
- **Remove `#include "Lambda/Execution.hh"`** from `Lambda.hh`. Keep the three analysis functions inline in `Lambda.hh` per rule §1.
- **Fold `LogStrings.hh` into `Lambda.hh`** and delete the file. `logString(Parameters&)` lives next to the orchestrators that call it.
- **Restore the cross-cutting types** under `Config::` (see §2) so `utils/Config.hh` compiles standalone.
- **Fix the recursive `publish` bug** in `utils/Monitor.hh::AsyncLogger::publish` — the body starts with a self-call (`publish(logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);`) that must be removed.

---

## 2. Cross-cutting types — restore to `Config`

These types are referenced outside Lambda and must not live under `modules/Lambda/`:

- `Bounds`, `RangeSize`
- `ParticleProperty`, `EventProperty`
- `Log` (logger state)
- type aliases: `ParticleLimits`, `EventLimits`, `TimePoint`, `uSeconds`, `Seconds`

**Target home:** `utils/Config/Types.hh`, included by `utils/Config.hh`.

The string-conversion helpers that go with them (`tryStringToParticleProperty`, `tryStringToEventProperty`, `stringToLevel`, name maps) belong in **`utils/Config/TypeAid.hh`** per the Aid rule.

`modules/Lambda/TypeAid.hh` stays where it is — it provides Lambda-specific *aliases* (`Mass_Invariant` → "Mass") used in TOML output.

---

## 3. The `*Aid` rule applied

| Header                            | Currently contains                                                                    | Aid-compliant? | Action                                                                                                                                                                    |
| --------------------------------- | ------------------------------------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `modules/Lambda/ParamAid.hh`      | `defaultTreeName`, `resolveTreeName`, `resolveCandidateLabels`                        | mixed          | Keep `defaultTreeName` (string transform). Move `resolveTreeName` and `resolveCandidateLabels` to `Parameters.hh` — they are config-resolution logic, not type extension. |
| `modules/Lambda/TypeAid.hh`       | property-alias map, range-size names                                                  | yes            | keep                                                                                                                                                                      |
| *(new)* `utils/Config/TypeAid.hh` | enum↔string conversions, name maps for `ParticleProperty`/`EventProperty`/`RangeSize` | yes            | new file (§2)                                                                                                                                                             |

---

## 4. Demote `Analysis` and `Meta` to submodules

Both are building blocks consumed by exactly one top-level utility.

- **`utils/Analysis.hh` → `utils/Extract/Analysis.hh`.** `Extract.hh` already includes it; physics primitives (mass, energy, ΔR, …) are the atoms `Extract` composes into observables. `Extract.hh` becomes the umbrella; callers update `#include "Analysis.hh"` → `#include "Extract.hh"` (or directly `Extract/Analysis.hh` if they only need primitives).
- **`utils/Meta.hh` → `utils/Record/Meta.hh`.** Both write ROOT objects; `Record.hh` already includes `Meta.hh`. Making it structural reflects the existing dependency. Contract stays: Meta = provenance under `About/`, Record = histograms/trees.

---

## 5. Rename + split `Explore` → `Probe`

`utils/Explore.hh` (951 LOC) is large enough to split, and the name is being changed to `Probe` (matches `[probe]` section in `newfile.toml`).

```
utils/
  Probe.hh                # umbrella include
  Probe/
    Event.hh              # Event type, EventStream
    FlatReader.hh         # index-based ROOT reader
    VecReader.hh          # array-based ROOT reader
    Schema.hh             # (if shared schema-resolution helpers warrant a file)
```

Update every `#include "Explore.hh"` and `Explore::` reference: `utils/Extract.hh`, `utils/Record.hh`, `modules/Lambda/Parameters.hh`, and the `_Lambda_*.cc` drivers.

---

## 6. Configs layout

```
configs/
  newfile.toml                    # active run-specific schema
  Lambda_Reconstruction.toml      # legacy run-specific (phase out)
  Lambda_Reconstruction.cmnd
  Lambda_Generation.toml
  NeNe.cmnd
  defaults/
    Lambda_Limits.toml
    General_Limits.toml
    Monitor.toml
    Paint.toml
```

`Config.hh`'s loader resolves `configs/defaults/<name>.toml` for baselines and lets the run-specific TOML override individual keys.

---

## 7. Target structure

```
utils/
  Config.hh                  # TOML + ROOT file/dir setup (entry point)
  Config/
    Types.hh                 # Bounds, RangeSize, ParticleProperty, EventProperty, Log
    TypeAid.hh               # enum↔string, name/alias maps
  Monitor.hh                 # async logger
  Record.hh                  # umbrella: histograms + trees + provenance
  Record/
    Meta.hh                  # provenance under About/
  Extract.hh                 # umbrella: extractors + physics primitives
  Extract/
    Analysis.hh              # particle property primitives, two-particle observables
  Probe.hh                   # umbrella for ROOT readers (was Explore.hh)
  Probe/
    Event.hh
    FlatReader.hh
    VecReader.hh
  Paint.hh                   # tooling, not main analysis path

modules/
  Lambda.hh                  # orchestrator: pythiaAnalysis, rootAnalysis, dataGenerator, logString
  Lambda/
    Schema.hh                # umbrella for everything below
    Types.hh                 # Lambda-specific structs only
    Parameters.hh            # TOML parameter loading + bound + tree-name + candidate-label resolution
    Reconstruction.hh
    Recording.hh
    ParamAid.hh              # type-extending only (defaults, formatting)
    TypeAid.hh               # Lambda-side aliases for Config enums

configs/
  *.toml *.cmnd              # run-specific
  defaults/                  # baselines
```

---

## 8. Sequencing recommendation

1. Fixes from §1 — buildable state.
2. §2 — restore cross-cutting types to `Config`.
3. §4 — demote `Analysis`/`Meta` (mechanical, low-risk).
4. §5 — rename + split `Explore` → `Probe`.
5. §6 — move default TOMLs into `configs/defaults/` and update loader.
6. §3 — tighten Aid headers last; smallest diff, lowest urgency.
