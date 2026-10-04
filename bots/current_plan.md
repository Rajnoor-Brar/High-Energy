# Current plan

**What is open:**
- [docs/audit_2/01_Health.md](../docs/audit_2/01_Health.md): findings H1–H16 and phases R0–R3, each
  step only on the user's order.
- The decisions are in docs/07_Record.md, and finished task logs in [archive.md](archive.md).

**Finished, and in git:**
- audit 1 (V52–V89, `git show c5cbaa3:docs/audit_1/06_Plan.md`);
- the figures (V80–V89);
- the manual's rebuild (V90–V92, `git show c5cbaa3:docs/audit_2/02_Manual.md`).

## Now

Nothing is in progress. Waiting on the user:

- **R0 (the user's):**
  - review and commit the migrated `configs/`, together with the untracked
    `configs/PhotoProduction/photo_zs.cmnd`, which three configs use (H1, H4);
  - verify the mpl pages against mkhtml's, after which the yoda backend goes (H11).
- **R1–R3** of the health check: quick fixes (a compare figure drawn once, H2), then structure
  (`runner/figures.py`, the figure-class rules in the schema), then sheets, tests and docs.
- **Four comment lines in the user's `configs/`** still cite old manual sections:
  - `Comparison/generators.toml`;
  - `Lambda/lambda.toml`;
  - `PhotoProduction/eic.toml`;
  - `PhotoProduction/xx/madgraph.toml`.

  They are left for the user.
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
