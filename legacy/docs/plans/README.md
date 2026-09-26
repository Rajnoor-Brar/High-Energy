# Plans — Rivet/YODA integration into the module stack

> **Superseded (2026-09-17).** This plan (integration into the *old* module stack) is replaced by the from-scratch rework in [`docs/rework/`](../rework/README.md), executed step by step via [`docs/rework/steps/README.md`](../rework/steps/README.md). These files stay for reference and move to `legacy/docs/plans/` in step P0-S06.
>
> | This plan | Where it went |
> |---|---|
> | Phase 0.1 — move tools into the repo | P0-S03 |
> | Phase 0.2 — FIFO hang | done (2026-09-16); supervisor rewrite in P3-S02 |
> | Phase 0.3 — Makefile | P0-S07 (interim), P2-S01 (CMake), P4-S06 (wrapper) |
> | Phase 0.4 — Lambda paths | not repaired; Lambda archived frozen (P0-S06, D17) |
> | Phase 0.5 / 0.6 — configs, generator CLI | done (2026-09-16); hotfixes in P0-S05 |
> | Phase 0.7 — `RIVET_ANALYSIS_PATH` | P0-S02 |
> | Phase 1 — config foundations (C++ `Config::Document`) | replaced: validation in Python (P1-S02…S06), C++ reads a resolved spec (P2-S03) |
> | Phase 1.4 — sweep model | kept and generalised (rework 03; P1-S03, P1-S04) |
> | Phase 2 — Monitor/output decoupling | replaced: `Status` + Python supervisor/terminal (P2-S03, P3-S02…S04) |
> | Phase 3 — in-process Rivet (`Observe::`) | `Sink::Rivet` (P2-S05), sharded in P6-S01 |
> | Phase 4 — event sinks (`Generate::`) | `Sink` namespace; Record sink replaced by YODA modules (P8-S01) |
> | Phase 5 — Python layer on unified schema | `hekit` (P1, P3, P4) |
> | Phase 6 — optional (Paint YODA, HepMC ingest, multiweight, plugin consolidation, batch) | Paint retired; HepMC store/replay (P5); plugin consolidation done (`photo_eic`); multiweight and batch in rework 10 §4 |
> | Q1–Q7 | rework 10 §5 and the decision register |
> | Finding IDs `B*`, `A*`, `M*`, `R1` | cited as `plans/…` in the rework; new findings are `00/Bn` |


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

## Status update (2026-09-16)

- Generalised typed sweeps are implemented in the Python tools
  (`[sweep]` with `across` / `style` / `overlay`, quantity types
  `pythia` / `beams` / `seed` / `plugin` / `option`); see `04_Roadmap.md` §1.4.
- B1 (FIFO hang) fixed; B2 partially (configs migrated; scripts still live in `~/HEP`).
- One base cmnd `configs/PhotoProduction/photo_ep.cmnd`; the per-variant
  cmnds in `configs/PhotoProduction/` and `configs/photo_zeus/` are now redundant.
- Noted, not changed: `photo_zeus/lhc21_cjkl.cmnd` uses `PDF:pSet = 5` (same as
  `mstw_cjkl.cmnd`); `nnpdf119lo_cjkl.cmnd` uses Pythia's default PDF.
- Later the same day: the Rivet plugins are consolidated into `photo_eic`, whose cuts are
  analysis options (`YMIN/YMAX` or `WMIN/WMAX`, `Q2MAX`, `ETMIN`, `ETMIN2`, `ETAMAX`, `R`,
  `CHETAMAX`, `CHPTMIN`). With `WMIN/WMAX` it reproduces `photo_5x41/10x100/18x275`
  exactly (17/17 histograms at 5x41 and 18x275). The default y cut differs by about 0.8 %
  at 5x41, almost all of it from the old plugin's rounded sqrt(s).
- `[sweep].across` accepts coupled groups; the new `[settle]` section holds fixed settings;
  plots can auto-clip their x range. `make <dir>/<name>.so` also installs the plugin's
  `.info`/`.plot` next to the library so Rivet validates its options.
- EIC run configs are consolidated into `configs/PhotoProduction/eic.toml`, with named
  `[study.<name>]` presets selected by `--study` (plus `--pin QUANTITY=TAG`). HERA
  validation stays in `zeus_validation.toml`. Plot pages are named `..._by_<curve quantities>`.
