# P7-S02 — Decide cross-generator photoproduction set-ups

| Field | Value |
|---|---|
| Status | done |
| Kind | decision |
| Phase | P7 — External generators and Delphes |
| Depends on | [P7-S01](P7-S01_adapter-framework.md) |
| Blocks | [P7-S03](P7-S03_sherpa.md), [P7-S04](P7-S04_whizard.md) |
| Effort | 0.5 d |
| Findings / decisions | Q7; D3; D20 |
| Updated | 2026-09-19 |

## Goal

A documented choice of Sherpa and Whizard settings that best match `photo_ep.cmnd` (EPA/WW, Q²max, photon PDF, pTHatMin analogue, MPI), with base cards committed.

## Context

- PhotoProduction is a test bed: document, don't gate.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `configs/PhotoProduction/photo_ep.cmnd` | reference physics | read |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- `configs/PhotoProduction/photo_ep.sherpa.yaml`, `photo_ep.sin`
- low-statistics 18x275 comparison

**Out (non-goals)**

- Tuning

## Decision record

- **Question:** Which generator settings count as 'the same physics' as `photo_ep.cmnd`?
- **Options:**
  - per-generator defaults with matched cuts only
  - matched EPA/WW parameters + Q²max + photon PDF where available
  - defer (no external photoproduction)
- **Criteria:**
  - availability of equivalent knobs
  - comparison quality
  - effort

- **Evidence**

  *What the reference actually is.* `photo_ep.cmnd` is **resolved** photoproduction: `PDF:lepton2gamma
  = on` puts a quasi-real photon (`Photon:Q2max = 1.0`) on the lepton, and `HardQCD:all` collides its
  partons with the proton's. 00/B30 measured that the direct contribution is unreachable with this
  card, so the reference sample is resolved-only — which decides most of what follows.

  *The photon PDF can be matched exactly.* Pythia has **one** photon PDF and no way to change it:
  `PDF:GammaSet` is declared `min="1" max="1"`, CJKL (`PDFSelection.xml:627`). Sherpa's `CJKSherpa`
  library provides `CJKLLO`, the same leading-order parameterisation. This is the single most
  important knob in a resolved photoproduction comparison, and it is not an approximation.

  *Whizard cannot do this physics at all.* Its own manual (`share/doc/manual.tex:6241`): "there is no
  builtin PDF that contains a photon structure function. There is a `beams` structure function
  specifier `pdf_builtin_photon`, but at the moment this throws an error." Whizard can put an EPA
  photon on a beam and collide it **directly**, which is Pythia's `PhotonParton:all` — the part of the
  reference that 00/B30 showed is empty. The overlap is approximately nothing.

  *Two things had to be found before Sherpa would run at all here.*

  1. **`MPI_PDF_SET` is a separate key from `PDF_SET`.** The multiple-interaction model reads
     `MPI_PDF_SET`/`MPI_PDF_LIBRARY` and falls back to Sherpa's compiled default proton set
     `PDF4LHC21_40_pdfas` (`PDF/Main/PDF_Base.C:25`), which this LHAPDF does not have. Every run with
     a hadron beam then dies in initialisation naming a set the card never mentions. Setting
     `PDF_SET` alone — in the card *or* on the command line — does not help.
  2. **Amisic MPI is unusable for this process here.** With `MI_HANDLER: Amisic` the integration
     finished in 75 s and then produced **0 events in 768 s**. With `MI_HANDLER: None` the same card
     generates 2 000 events in **4 s**. Not diagnosed further: it is P7-S03's problem, and it is
     recorded so that step does not rediscover it.

  *The comparison,* at 18×275, both leading order, both resolved, both MPI off, both with the
  NNPDF2.3 LO proton PDF, both cut at 6 GeV:

  | | σ (pb) | events |
  |---|---|---|
  | Pythia 8.317, `pTHatMin = 6`, CJKL | **11 950 ± 34** | 19 980 |
  | Sherpa 3.0.5, `NJetFinder{PTMin: 6, R: 1}`, CJKLLO | **9 636 ± 782** | 2 000 |

  Ratio **0.81 ± 0.07**. The remaining difference is dominated by the one knob that cannot be
  matched: Pythia cuts on the 2→2 matrix element's pT-hat, Sherpa on a clustered jet, and those are
  different surfaces in the same phase space. For two independent generators with a different cut
  definition this is a good agreement, and per D20 it is documented rather than gated.

- **Decision: matched EPA/Q²max + photon PDF for Sherpa; defer photoproduction for Whizard.**

  Sherpa gets option 2 — every knob that has an equivalent is matched (beams, EPA Q²max, photon PDF,
  proton PDF, order, MPI on/off), and the two that do not are written down in the card itself:
  the pT cut's definition, and `MultipartonInteractions:pT0Ref = 3.2` (a Pythia tune parameter with
  no counterpart in Amisic, a different model). Whizard gets option 3 for *this* reference: its card
  targets direct photoproduction and says plainly that it is not a cross-check of `photo_ep.cmnd`.

- **Consequences:**
  - `configs/PhotoProduction/photo_ep.sherpa.yaml` — runnable, verified to initialise and generate.
  - `configs/PhotoProduction/photo_ep.sin` — direct-only, labelled as not equivalent.
  - **P7-S03** must solve the Amisic MPI problem before a Sherpa point can carry the underlying event,
    and must keep `MPI_PDF_SET` in step with `PDF_SET` when it sweeps proton PDFs.
  - **P7-S04** should treat Whizard direct photoproduction as its own physics point, not as a
    comparison. Its "Photoproduction (ep) ✓" row in 04 §2 was too generous and is corrected.
- **Docs to update:** 04_Generators.md §2, steps/README.md decision register

## Tasks

- [x] Research knobs
- [x] Write base cards
- [x] Run comparison
- [x] Record

## Outputs

- base cards
- decision record D-Q7

## Verification

| Check | Command | Expected |
|---|---|---|
| Recorded | Decision record | filled |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

n/a.

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-19 — decision **D-Q7** recorded above, with a measured comparison rather than an asserted
  one: Sherpa 3.0.5 is installed here, so the cards could be run instead of only written.

  Headline numbers: Pythia **11 950 ± 34 pb** against Sherpa **9 636 ± 782 pb** at 18×275, matched
  leading order, resolved, MPI off, same proton PDF, same 6 GeV cut — a ratio of 0.81 ± 0.07, with
  the residue explained by pT-hat versus clustered-jet cuts.

  Three findings that P7-S03 and P7-S04 would otherwise have had to make for themselves: Sherpa needs
  `MPI_PDF_SET` as well as `PDF_SET` or it dies naming a PDF nobody asked for; Sherpa's Amisic MPI
  produced 0 events in 768 s for this process while MPI-off produced 2 000 in 4 s; and Whizard cannot
  do resolved photoproduction at all, by its own manual.

  **Deviations**

  1. The step's scope said "low-statistics 18×275 comparison" and left the form open. It is a **cross
     section** comparison, not a histogram one: with MPI off on one side and the analysis not yet
     wired to Sherpa, a shape comparison would have been comparing the cut definitions rather than
     the generators. σ is the number both sides agree on the meaning of.
  2. The beam order in both cards is **proton first**, unlike Sherpa's own HERA example. Sherpa's
     example puts the lepton on beam 1, which sends the proton along −z and mirrors every
     pseudorapidity distribution — the same class of error as 00/B26, and much harder to spot in a
     cross-generator comparison than in one generator.
