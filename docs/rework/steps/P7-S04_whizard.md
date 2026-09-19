# P7-S04 — Whizard adapter

| Field | Value |
|---|---|
| Status | done |
| Kind | code |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md), [P7-S02](P7-S02_decide-photoproduction-equivalence.md) |
| Blocks | — |
| Effort | 1 d |
| Findings / decisions | R7; 04 §5 |
| Updated | 2026-09-19 |

## Goal

Whizard points run through `hep run` with SINDARIN rendering, model particle names and HepMC3 FIFO output.

## Context

- Whizard appends `.hepmc` to the sample name.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| 04 §5 | rules | implement |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- insertion-rule check
- PDG → model names
- `beams_momentum`/`sqrts`
- `<stem>.hepmc` FIFO
- parton-level flag
- prepare (grids)

**Out (non-goals)**

- —

## Design notes

- Reject cards that set seed/n_events after the insertion point.

## Tasks

- [x] Implement
- [x] Tests

## Outputs

- `hekit/adapters/whizard.py`

## Verification

| Check | Command | Expected |
|---|---|---|
| Toy | e+e- → jj | runs |
| ep | card from S02 (if any) | runs |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Revert.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — implemented `hekit/adapters/whizard.py`. Whizard 3.1.8 is installed, so both rows were
  run. New ctest test `whizard` (label `slow`, 7 cases, 18 s) and 18 unit tests.

  **Verification, both rows measured**

  | Row | Result |
  |---|---|
  | Toy | `e+e- -> u ubar` at the Z runs end to end: compile and integrate (cached), generate into the FIFO, `hep-run` reads it as `Source::Stream`, a YODA is written. The point card shows `beams = e1, E1` — PDG codes turned into the model's own names — and `beams_momentum = 45.6, 45.6` |
  | ep | the card D-Q7 settled on runs: 50 events, `beams = p, e1 => pdf_builtin, epa` assembled from the plan's half and the card's half, and a YODA normalised by the σ the config supplied |

  A two-seed study compiles and integrates **once**, which for Whizard means not rebuilding the
  matrix-element library — the dominant cost.

  **Two properties of Whizard that bite immediately, both now pinned by tests.**

  1. **It writes no cross-section into HepMC3.** Not a zero — no `C` record at all, verified by
     reading the file. A stream therefore has none to take, and the run was quietly producing a YODA
     normalised by **zero**. 04 §8 already said this must be an error ("unless `rivet.xsec` is a
     number"); nothing enforced it. `Core::RunRecord` now carries `xsec_known` and `Sink::Rivet`
     refuses, naming the remedy. A Whizard point must set `[rivet].xsec`; Whizard's own integration
     prints it as `n_events / corr. to luminosity`.
  2. **Its EPA record has no scattered lepton**, so `photo_eic` — which applies `DISKinematics` to
     build the Breit frame — aborts on a Rivet assertion. Pythia's and Sherpa's EPA records keep the
     lepton, so this is specific to Whizard's. The card says so, and the test uses a generic analysis.

  **Four things the card itself had to be taught**, each found by a failed run: `epa_mass` defaults to
  zero and a zero there is fatal rather than a massless approximation; a flavour alias may not mix
  masses, and Whizard's SM gives `ms = 0.095` while u and d are massless; the incoming order of a
  process must match the beam order, or Whizard says "Product of density matrices is empty"; and the
  base must not assign what the plan owns, because it runs *after* the point card.

  **Design notes**

  1. **The beams line is assembled from two halves.** The plan owns the particles and the energies;
     the structure-function chain after the `=>` is physics only the base can state. The base
     declares its half in a `# hep: beam_structure = pdf_builtin, epa` line. Neither half can be
     written without the other, and a SINDARIN variable would not have helped — `beams` does not read
     one.
  2. **`Stage` gained `writes`.** The integration needs a card *without* the generation lines, and
     Whizard's `--execute` runs before the card rather than after, so it cannot be overridden from
     the command line the way Sherpa's could. An adapter still returns data: it declares the file and
     the runner writes it. Herwig will want the same.
  3. **`$sample` had to join the volatile cache keys**: it carries the point's own directory, so
     without it every seed replica got its own compiled library — found by the two-seed test.
  4. The SINDARIN assignment pattern had to learn the sigils. `?hadronization_active` and `$sample`
     are assignments; a regex that only knew bare names could not see them, so it could neither
     report the parton level nor refuse a base that set one.

  **Deviations**

  1. The toy is `e+e- -> u ubar` rather than `-> jj`: a flavour alias may not mix masses, and a
     jet-inclusive alias would have meant `ms = 0` plus a second process for nothing the row tests.
  2. The `sqrts` path (a scalar √s) is covered by unit tests only — the `energies` quantity is always
     a pair, so an integration test cannot reach it through a config.
  3. `prepare` declares no `produces`. What Whizard leaves behind is named after the processes and
     the library, both of which a card can rename, and a wrong name would silently re-integrate on
     every run; the stage's exit code is the signal instead.
