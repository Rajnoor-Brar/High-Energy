# P8-S02 — Phys namespace

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P8 — Modules, YODA results, Phys, ML |
| Depends on | [P2-S03](P2-S03_core-status.md) |
| Blocks | — |
| Effort | 0.5 d |
| Findings / decisions | 00 §3 verdict (Physics → Phys); 00/B34, 00/B35, 00/B36 |
| Updated | 2026-09-20 |

## Goal

PDG traits, kinematics on HepMC four-vectors, `GenEvent` selectors and jet-definition parsing are available to modules.

## Context

- 13 §2.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `legacy/utils/Physics/{Particles,Types,TypeAid,Kinematics,Properties}.hh` | tables, kinematics | port (drop ROOT GenVector) |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `Phys/{Types,Pdg,Kinematics,Select,Jets}`
- port the legacy Physics tests

**Out (non-goals)**

- —

## Design notes

- Guard for ±inf in Δφ (legacy defect).

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `utils/Phys.hh`, `utils/Phys/{Types,Pdg,Kinematics,Select,Jets}.hh`
- `tests/cxx/test_phys.cc` (ctest `phys`)
- `modules/Examples/ToyJets.cc` rewritten onto `Phys`
- `Module::Base::threadSafe()`, `Sink::Modules::concurrency()`, `Run::Loop::decideMode()`

## Verification

| Check | Command | Expected | Measured |
|---|---|---|---|
| PDG | compare to Pythia `ParticleData` for the table entries | match | 13/13 rows: mass, charge and name all agree (mass to 1e-5, which is the five decimals Pythia keeps) |
| Jets | `jetDefinition("antikt:0.4")` vs FastJet | equal definitions | identical `description()`; also kt, CA, genkt and a named scheme |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated (13 §2 row confirmed; 05 §5 gained `threadSafe`; 00/B34-B36)
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — **done.** Five headers plus the facade, 167 checks in `tests/cxx/test_phys.cc`.

  **Both Verification rows measured.** The PDG row is checked against Pythia's own `ParticleData`
  rather than against a copy of the table: all thirteen rows agree on mass, charge and name.
  Perturbing one mass by 1e-4 in the source fails the row, so it is a live comparison and not a
  tautology. The jets row compares `jetDefinition("antikt:0.4")` with a hand-written
  `fastjet::JetDefinition` through FastJet's own `description()`, since `JetDefinition` has no
  equality operator.

  **ROOT is gone from the physics layer.** `Physics::Lorentz` was `ROOT::Math::PxPyPzEVector`, so
  every user of a trait table linked ROOT and converted each particle out of the event it was already
  holding. `Phys` is on `HepMC3::FourVector`, which is what a `GenEvent` stores, so there is no
  conversion at all — and HepMC3's vector turned out to carry everything the ported code used,
  arithmetic included, so nothing had to be reimplemented.

  **Three defects, recorded as 00/B34-B36.**

  - **B34 — `Physics::particle(-211).charge3` was +3.** The lookup resolved an antiparticle to its
    particle's row and handed back that row's charge, so every negative code came out positive.
    Nothing read it, which is why it survived. `Phys::Pdg::charge3(id)` now carries the sign.
  - **B35 — Δφ hangs on ±inf.** The design note asked for a guard and this is what it was guarding:
    `while (d > π) d -= 2π` never terminates for d = ±∞. **It is not a legacy-only defect** —
    `HepMC3::FourVector::delta_phi` has the same loop and guards NaN but not ∞, which is the reason
    `Phys::deltaPhi` exists rather than deferring to the method on the vector. `std::remainder` wraps
    over the same range ([−π, π]) in one branch-free step and gives NaN for a non-finite input. The
    test times the call, so the loop coming back hangs a 0.05 s test rather than a run.
  - **B36 — a module that clusters jets would have raced.** This step hands modules `Phys::cluster`,
    and `Sink::Modules` is the one sink that shards; 00/B31 applies to a module exactly as it does to
    a Rivet analysis, and nothing detected a module doing the clustering by hand. `Module::Base`
    gained `threadSafe()` (true by default) and the sink reports `Concurrency::Locked` when a module
    says false.

  **And a throughput bug that B36's fix exposed.** With `ToyJets` locked, `mode = "auto"` dropped the
  *whole run* to serial — `decideMode` asked "can any sink be sharded?" when the question is "is
  there anything to gain?". A `Locked` sink still lets the generator run on k threads and serialises
  only the sink call. Measured at 4 threads, 2 000 → 20 000 events: **124 µs/event serial against
  92 µs/event with the lock**, so the rule now counts anything that is not `Serial`. The blast radius
  is exactly the new case: `Sink::Rivet` reports `Serial` plus a `serialReason` when it clusters, and
  `Sink::Count` reports `Serial`, so neither changes.

  **`Phys` has a user, not just a test.** `modules/Examples/ToyJets.cc` carried its own final-state
  loop, its own pT, and a hand-written pseudorapidity with a guard around a particle travelling down
  the beam; all three are one `Phys::Acceptance` now, and it finally clusters the jets it is named
  after. `tests/integration/test_modules.py` re-measures the physics unchanged (9 passed), which is
  the check that the port did not quietly change an answer.

  **Deviations from the step as written.** Three additions, none of them removals:
  `Phys::disKinematics` (Q², x, y, W², ν) because an EIC test bed's kinematics are DIS kinematics and
  Rivet's `DISKinematics` is not reachable from a module; PDG predicates read off the numbering
  scheme (`isNeutrino`, `isHadron`, …) rather than from the table, so they answer for codes nobody
  tabulated; and the `threadSafe`/`decideMode` work above, which this step created the need for.
  The DIS invariants are checked by identities — Q² = x y (s − M²), W² = M² + Q²(1−x)/x — rather than
  by repeating the formulas back.
