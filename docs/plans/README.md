# Plans — Rivet/YODA integration into the module stack

Date: 2026-09-16 · Status: **analysis & plan only — nothing implemented.**
Machine context: Lab_PC (Linux, `~/HEP` stack via `load_hep`). Earlier
documents in `docs/` describe the Lambda/`utils/` work done on a Mac with a
different stack.

## Reading order

| File | What it answers |
|---|---|
| [01_CurrentState.md](01_CurrentState.md) | What both workflows look like today, with evidence-backed findings (IDs A*, B*, M*, R1) |
| [02_DesignComparison.md](02_DesignComparison.md) | How their configuration and inter-tool coordination philosophies differ, and which principles to keep |
| [03_IntegrationOptions.md](03_IntegrationOptions.md) | Requirements, six options with trade-offs and a weighted evaluation, proposed decision, Config/Monitor compatibility requirements |
| [04_Roadmap.md](04_Roadmap.md) | Phased plan (0–6) with API sketches, unified TOML schema, key migration map, per-phase verification, risks and open questions |

## Summary

**The two designs.** The Lambda stack is a *framework*: one C++ process,
the library owns lifecycle, configuration is sectioned per subsystem,
and progress/stall/signals/provenance are built in. The PhotoProduction
workflow is a *toolchain*: Python supervises `generator.exe` and `rivet`
joined by a HepMC FIFO; it has a stricter single-object config and
first-class run matrices, but no monitoring or provenance, and its
orchestration lives outside the repo.

**Most important findings**
- **B1 (reproduced):** `rivpyth` hangs forever if the generator fails
  before opening the FIFO.
- **B2:** orchestration scripts in `~/HEP` are unversioned; two repo
  configs already fail to load.
- **M1:** the new Makefile dropped header-dependency tracking (a regression
  of an earlier fix); **M3:** the test harness no longer finds test binaries.
- **A1:** Lambda configs point at pre-move paths; the Lambda drivers cannot
  run as shipped.
- **A2:** `Config::configurePythia` would label EIC runs `14000GeV`
  (`Beams:eCM` is unused with `frameType = 2`).
- **A3:** Monitor cannot run without a `Record::Writer`, which blocks any
  Rivet-only integration.
- **B3:** YODA normalisation uses per-thread σ estimates, not the merged σ.
- **R1 (reasoned):** Pythia 8.317's `RivetHooks` appears to merge
  non-main handlers twice — use a project-owned sink instead.

**Recommendation.** Staged **0 → A → B → C**:
1. Fix the defects (hang, versioning, Makefile, stale paths).
2. Unify configuration: one parsed, strict document, beam energy read
   after `init()`, and a `[sweep]` model.
3. Decouple Monitor and output naming from `Record::Writer`.
4. Add an in-process Rivet stage (`Observe::`) with merged σ, progress
   and provenance.
5. Generalise to event sinks (`Generate::`: Rivet, Record, HepMC).

Keep `rivet-mkhtml` for plotting, keep HepMC/FIFO as an optional mode,
and defer HepMC ingest.

**Next step when you ask for implementation:** Phase 0, then answer
Q1–Q4 in `04_Roadmap.md` before starting Phase 1.
