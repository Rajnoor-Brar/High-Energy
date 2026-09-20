# P7-S06 — Decide and (optionally) rebuild ThePEG/Herwig

| Field | Value |
|---|---|
| Status | done |
| Kind | decision |
| Phase | P7 — External generators and Delphes |
| Depends on | [P1-S07](P1-S07_doctor-pdf.md) |
| Blocks | [P7-S07](P7-S07_herwig.md) |
| Effort | 0.25 d + build |
| Findings / decisions | Q6; F10; 00 §1.3 |
| Updated | 2026-09-20 |

## Goal

A recorded decision on rebuilding ThePEG with HepMC and Rivet support; if rebuilt, `hep doctor` detects the modules.

## Context

- Without the rebuild Herwig is 'run-only'.
- Design references: [rework README](../README.md), [roadmap](../10_Roadmap.md), [porting map](../00b_PortingMap.md).

## Inputs to reuse

| Source | What to take | How |
|---|---|---|
| `~/HEP/src` build trees | configure flags | read |

Never `#include`/import from `legacy/`; copy or adapt.

## Scope

**In**

- decision; optional rebuild commands and timings

**Out (non-goals)**

- Herwig adapter (S07)

## Decision record

- **Question:** Rebuild ThePEG `--with-hepmc=$HEP_INSTALL/hepmc3 --with-rivet=$HEP_INSTALL/rivet` and Herwig now, later, or never?
- **Options:**
  - now
  - later (when a Herwig study is planned)
  - never (Herwig stays run-only)
- **Criteria:**
  - need for Herwig comparisons
  - build time/risk
  - toolchain stability
- **Evidence**

  The blocker is **not a missing dependency**. HepMC3 3.3.1 and Rivet 4.1.3 are both installed and
  both are used by Pythia and Sherpa. ThePEG simply was not told about them:

  ```
  $ grep -iE "hepmc|rivet" ~/HEP/src/ThePEG-2.3.0/config.log
  ./configure --prefix=…/herwig7 --with-hepmc3=…/hepmc3 --with-fastjet=… --with-lhapdf=…
  configure:18277: result: HepMC support disabled.
  configure:18571: result: Rivet support disabled.
  ```

  ThePEG 2.3.0's option is `--with-hepmc=`, not `--with-hepmc3=`, so the flag was accepted as an
  unknown `--with-*` and ignored; `--with-rivet` was never passed at all. Both supports are therefore
  off, which is why `~/HEP/install/herwig7/lib/ThePEG/` has no `HepMCFile` or `RivetAnalysis` module
  even though the **headers** for both are installed (`ThePEG/Analysis/RivetAnalysis.h`,
  `ThePEG/Config/HepMCHelper.h`). Herwig 7.3.0 itself runs.

  So the cost is a rebuild, not an investigation, and the risk is low — the flags are known and the
  old install can be kept by building into a separate prefix.

- **Decision: later** (user sign-off, 2026-09-20). Record the commands, gate Herwig off, and rebuild
  when a Herwig comparison is actually wanted.

  Herwig is priority 4 of 5 in 04 §2's matrix and nothing else in the plan depends on it: Pythia is
  the reference, Sherpa is the cross-check that works (P7-S03), and MadGraph covers the
  matrix-element route. Spending an hour of compiling now to unblock a step nobody is waiting on is
  the wrong order, and the rebuild does not get harder for waiting.

  **The commands, when it is wanted** — into a fresh prefix, so the working install survives a failure:

  ```bash
  P=$HOME/HEP/install/herwig7-hepmc
  cd $HOME/HEP/src/ThePEG-2.3.0 && make distclean
  ./configure --prefix=$P \
      --with-hepmc=$HOME/HEP/install/hepmc3 \
      --with-rivet=$HOME/HEP/install/rivet \
      --with-fastjet=$HOME/HEP/install/fastjet \
      --with-lhapdf=$HOME/HEP/install/LHAPDF \
      CXXFLAGS="-O2 -std=c++17"
  make -j"$(nproc)" && make install
  cd $HOME/HEP/src/Herwig-7.3.0 && make distclean
  ./configure --prefix=$P --with-thepeg=$P \
      --with-fastjet=$HOME/HEP/install/fastjet \
      --with-lhapdf=$HOME/HEP/install/LHAPDF \
      CXXFLAGS="-O2 -std=c++17"
  make -j"$(nproc)" && make install
  ```

  Check it took: `grep -iE "hepmc|rivet" config.log` must say **enabled**, and
  `ls $P/lib/ThePEG | grep -iE "hepmc|rivet"` must list the modules. Then point
  `~/HEP/setup.sh` at the new prefix.

- **Consequences:** P7-S07 (Herwig adapter) is **blocked**, not dropped — the work is a rebuild away,
  and 04 §2 says so rather than claiming Herwig works. `hep doctor` reports Herwig as present but
  without HepMC/Rivet modules, which is the honest state.
- **Docs to update:** 04_Generators.md §6, 10_Roadmap.md §5, steps/README.md decision register

## Tasks

- [x] Ask user
- [x] If yes: rebuild in `~/HEP/build`, record commands — not now; the commands are in the record
- [x] Update doctor check

## Outputs

- decision record D-Q6

## Verification

| Check | Command | Expected |
|---|---|---|
| Detected | `hep doctor --json \| jq -r .generators.herwig.status` | `ok` (if rebuilt) — **not rebuilt**, so `hep doctor` reports Herwig present without its HepMC/Rivet modules |
| Read works | `Herwig read` toy card | OK (if rebuilt) — n/a |

**Test safety:** work in `output/scratch/` or with `HEKIT_RESULTS` pointing there; never write into `results/` or `configs/` during checks (legacy tools: run from `output/scratch/legacy/`). Commits and tags only with user approval.

## Rollback

Keep old install (build into a separate prefix first).

## Done when

- [x] every Verification row passes
- [x] docs named in this step are updated
- [x] status set here and in [steps/README.md](README.md)

## Log

- 2026-09-17 — step file created (P0-S00).
- 2026-09-20 — decision **D-Q6** recorded above: **later**, with user sign-off.

  The useful part of this step turned out to be the diagnosis. 01 §4 recorded the symptom ("ThePEG
  has no HepMC or Rivet modules here") as though a dependency were missing; it is not. Both libraries
  are installed and in daily use by Pythia and Sherpa. ThePEG was configured with `--with-hepmc3=`,
  which it does not recognise — its option is `--with-hepmc=` — so the flag was ignored, `--with-rivet`
  was never passed, and its own config.log says both supports are **disabled**. The headers are
  installed; only the modules are missing.

  That turns an open-ended "can Herwig work here?" into a known rebuild with known flags, which is
  written out in the record so nobody has to find it again.

  **Deviations**

  1. No rebuild was done, so the two Verification rows are recorded as not applicable rather than
     passed — the decision was "later", and pretending otherwise would be worse than saying so.
  2. P7-S07 is marked **blocked** rather than `todo`: it is ready except for the rebuild, and a
     reader should not pick it up expecting it to be startable.
