# Current plan

**What is open:**
- [docs/audit_2/01_Health.md](../docs/audit_2/01_Health.md): findings H1–H16 and phases R0–R3, each
  step only on the user's order.
- The decisions are in docs/07_Record.md, and finished task logs in [archive.md](archive.md).

**Finished, and in git:**
- audit 1 (V52–V89, `git show 3a5ec16:docs/audit_1/06_Plan.md`);
- the figures (V80–V89);
- the manual's rebuild (V90–V92, `git show 3a5ec16:docs/audit_2/02_Manual.md`).
- `[config]` (V93–V97): it replaces `[master]`; `import` nests, crosses projects and takes `only` a part; `drop`; `vars`; `meta` (version warnings). The doc is 04 §3.
- `[run.cfgs.<cfg>]` (V98–V100): configurations moved out of `[run]`; `[run]` gives every configuration its keys (`[run.defaults]` gone); an import's location rule is per folder. The user's configs were migrated by `hep migrate` (2026-10-06, backup in the scratchpad `configs_before_cfgs/`), uncommitted.
- Decks, `hep deck` (V102–V104, docs/reporter, 2026-10-10): `figures/layout.py` (sheets and composites: pdflatex, PNG by pdftoppm), `runner/deck.py` (blocks from result folders or a folder's files; composites; deck.md through pandoc to Beamer, pptx, dzslides HTML, an Overleaf zip), `runner/viewer.py`; the manual's 03 §11, 04 §15, 05 §1.8. Example: `reports/batch_1_deck/` (not in git).
- PhotoProduction TOMLs refactored (2026-10-06, uncommitted): `configs/PhotoProduction/common.toml` (new) holds the chain's tools (parameterised by `[config.vars]` card/analysis/product/shards), the shared quantities, statics and plot keys; eic and zeus_validation import it, zeus_seedSweep and InProcZeus import zeus_validation, InProcEIC eic. Identities unchanged except zeus_seedSweep's (its PDFs now zeus_validation's Pythia sets) and InProcEIC's new pt28 points (pt0ref's 4 values). Backup: scratchpad `refactor_before/`.

## Now

**docs/framework/** (2026-10-08): the plan set that moves the framework and its environment into `$HEP`
(the framework repo **HEimdall**, `$HEP/HEimdall`) and leaves work dirs (many, independent; made by
`hep setup <dir>`) holding only configs, modules and products. Executed by AI agents on the **lab PC
after a clean reinstall** (D16). **High-Energy becomes the lean work repo** (branch `work`, D15).
- Round 1: [README.md](../docs/framework/README.md), D1–D16 (amended in 2a).
- Round 2a: [01_Target.md](../docs/framework/01_Target.md) (the trees, the seam, C1–C78, the move map,
  the pre-wipe checklist, D17–D25) and [02_Agents.md](../docs/framework/02_Agents.md).
- **Round 2b done (2026-10-10, against 9cb907a, the decks V102–V104 included):**
  - the phase files: [03](../docs/framework/03_Preflight.md) P0 preflight,
    [04](../docs/framework/04_Seed.md) P1 seeding (the move-map script, tested: 204 fw / 1363 work),
    [05](../docs/framework/05_Stack.md) P2 the stack, [06](../docs/framework/06_Seam.md) P3 the seam,
    [07](../docs/framework/07_Framework.md) P4 build/tests/manual, [08](../docs/framework/08_Workdirs.md)
    P5 work dirs, [09](../docs/framework/09_Verify.md) P6 verification and handover;
  - the annexes `targets/{ubuntu,cluster,container,macos}.md`;
  - the lab PC's baselines inside them: stack versions, 21 PDF sets, the reference point
    inproc_zeus/default/NNPDF23lo (σ 72,987.12 ± 30.34 pb, 999,892 events, seed 246223968).
- **Next, the user's:** review; then before the wipe, 01 §8's checklist (push `rework`, keep
  datasets/literature/cross_machine/reports, the reference point, optionally tarballs and memory).
- Found while writing 2b (not fixed): `hep reproduce` builds `--set run.<cfg>.seed_type`, the form
  before V98, so it probably fails on a `seed_type = "random"` configuration (C78); `build/flags.mk`
  was last probed without `load_hep` (FOUND = toml zstd zlib; self-heals on the next `hep build`
  with the environment loaded).
- Round 2 writes only `docs/framework/` and this file.

Otherwise nothing is in progress. Waiting on the user:

- **R0 (the user's):**
  - review and commit the migrated `configs/`, together with the untracked
    `configs/PhotoProduction/photo_zs.cmnd`, which three configs use (H1, H4). Since 2026-10-06
    `InProcEIC.toml` and `InProcZeus.toml` import eic.toml / zeus_validation.toml (the originals:
    `git diff configs/PhotoProduction/InProc*`);
  - verify the mpl pages against mkhtml's, after which the yoda backend goes (H11).
- **R1–R3** of the health check: quick fixes (a compare figure drawn once, H2), then structure
  (`runner/figures.py`, the figure-class rules in the schema), then sheets, tests and docs.
- **Four comment lines in the user's `configs/`** still cite old manual sections:
  - `Comparison/generators.toml`;
  - `Lambda/lambda.toml`;
  - `PhotoProduction/eic.toml`;
  - `PhotoProduction/xx/madgraph.toml`.

  They are left for the user.
- **`hep migrate --stamp`** (the [config] plan's optional C3 S3): it would write the stack's versions into `[config.meta].versions`. Only if wanted.
- **Later**, on the user's word:
  - F8 `--more`;
  - F9, a Slurm/HTCondor executor;
  - K15, the `HEKIT_*` rename;
  - Paint's PDF line widths (about 2× too thick);
  - the held C++/Rivet items (K3, K4, K7, K8, K10, yd2rt's dead parameter);
  - `extends`/`common.toml` for zeus_validation ("not now").

## Standing constraints

- **Commits:**
  - local, never pushed, with the Co-Authored-By line;
  - stage named paths only, never `commit -a`: the worktree holds the user's uncommitted
    `configs/`, `modules/PhotoProduction/Rivet/photo_eic.plot`, a legacy README deletion and
    `docs/Untitled-1.md`.
- **Tests:**
  - tests never read or write the user's `configs/` and `results/` (V52: `tests/fixtures/configs/`);
  - one pytest session at a time, and the slow suite not while the user's long runs share the cores;
  - `source ~/HEP/setup.sh` before make or pytest, or `build/flags.mk` is re-probed empty.
- **Approvals:**
  - `~/HEP` changes and downloads need the user's approval; the venv and `hep_env.sh` are the
    user's;
  - a rebuilt App_Pythia, App_yd2rt, InprocJets or Rivet plugin changes the identity of every point
    that ran it, so ask before rebuilding (Paint is plot-only and safe).
- **Docs:** after changing a schema key's `doc`/`notes`, base.toml's comments or the CLI's help, run
  `make docs` (and `make schema`).
- **Way of working:** never implement without an explicit order; plans first, questions when a
  request is ambiguous.
