# P0 — Clean slate

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| **in progress** | 2 | — | v1 deleted; the v2 tree, Makefile and shell in place; Rivet plugins build; nothing runs yet | 2026-09-26 |

## Goal

**Delete v1 and lay the v2 tree down**, so every later line is written against the brief and none
against v1's shape (V5). After this phase:

- `utils/` holds only the shell environment;
- the Makefile builds Rivet plugins;
- `hep` prints its help;
- **nothing generates events.** That is accepted (R3); v1 stays one command away through git.

Design: [03_Layout_Build.md](../03_Layout_Build.md) §§1, 5, 8. Ledger: L20, L22.

## Before starting

Ask the user once for the P0 approvals ([06 §2](../06_Roadmap.md#2-how-a-phase-is-run)):

- the tag;
- the deletion commit;
- per-step commits;
- the `~/HEP/setup.sh` stub.

*Given 2026-09-26: all four. The root-level `generator_comparison.*` is the user's scratch file,
to be left alone.*

**The working tree had uncommitted user changes**: `env/doctor.py` and its test,
`docs/rework/04_Generators.md`, `docs/rework/steps/P7-S06_…md`, and `docs/Untitled-1.md`. The user
said none needs committing (2026-09-26). They are **stashed** (`git stash list`) rather than
discarded, and `Untitled-1.md` is moved to `output/_v1/`. The Herwig findings in them are in the
ledger as L15.

---

## S1 — Tag, measure once, delete, move

**Tasks**

1. `git tag rework/v1-final`.
2. **One timing baseline** (R4), while v1 still exists: run
   `hep run configs/PhotoProduction/eic.toml --study single` at **50k events** (the user's choice)
   and threads = 20, with `HEKIT_RESULTS` pointing into `output/`.
   Copy the events/s and wall time from `run.summary.json` into this Log. This is the only v1 run
   in the whole plan.
3. **Move**, following [03 §8](../03_Layout_Build.md#8-p0-delete-keep-move):

   | From | To |
   |---|---|
   | `analyses/<P>/*` | `modules/<P>/Rivet/` (`git mv`) |
   | `tests/golden/legacy_run/` and the frozen `tests/golden/inputs/PhotoProduction/photo_ep.cmnd` | `tests/reference/legacy_run/` |
   | `test_legacy_counts.py`'s `EXPECTED_COUNTS` | `tests/reference/point_counts.toml` |

4. **Delete**, also per [03 §8](../03_Layout_Build.md#8-p0-delete-keep-move): `utils/`,
   `CMakeLists.txt`, `cmake/`, `env/` (after saving `hep_env.sh` into the new
   `utils/Env/hep_env.sh`), the rest of `tests/`, `legacy/`, `docs/rework/`, `docs/post_rework/`,
   `docs/GUIDE.md`, `docs/MAP.md` and `modules/Examples/`. **Untracked** leftovers (the old `build/`,
   `output/scratch/`, the stale `output/PhotoProduction/*`) are **moved to `output/_v1/`**, not
   deleted. The user removes them when satisfied.
5. Park `modules/Lambda/*` in `modules/Lambda/_v1/`. **Folders starting with `_` are not built** (a
   make convention, documented in 03 §5.1). P4 rewrites Lambda; until then its Rivet twin `Lamriv`
   needs the deleted `Phys` and cannot build.
6. Update `.gitignore`, `docs/README.md` (it points at `rework_v1/` and `rework_v2/`), and
   `bots/BOT.md`'s layout table and testing rules (`output/tests/`, `tests/reference/`).

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `git tag -l rework/v1-final` | exists |
| 2 | `git ls-files utils` | exactly `utils/Env/hep_env.sh` |
| 3 | `ls analyses env legacy cmake CMakeLists.txt 2>&1` | all absent |
| 4 | `git diff --stat -M rework/v1-final -- tests/reference modules/*/Rivet` | only renames (100% similarity) |
| 5 | `wc -l` over the tracked tree, excluding `aux/`, `literature/` and `docs/rework_v*` | recorded in the Log: the before and after line count |
| 6 | timing baseline | a number in the Log |

---

## S2 — The skeleton: Makefile, shell, runner stub

**Tasks**

1. **`utils/Env/flags.sh`** probes each `*-config` once and writes `build/flags.mk`. It records each
   tool's resolved path and `HEP_INSTALL`, and the Makefile regenerates the file when any of them
   differ (L22).
2. **`Makefile`:**
   - the convention table of [03 §5.1](../03_Layout_Build.md#51-make-pathexe-and-make-pathso);
   - `requires:` parsing ([03 §5.2](../03_Layout_Build.md#52-what-to-link-the-requires-line));
   - `-MMD -MP` into `build/deps/`;
   - the `rivet-build` rule, with `-I utils -I modules/<P>` and ONNX `Requires:` (L20);
   - `.info`, `.plot` and `.yoda` copies as real targets;
   - `_`-prefixed folders skipped;
   - the targets `all`, `test`, `test-slow`, `clean`.
3. **`utils/Env/hep_env.sh`:** trim it. Drop the version probes (they duplicated `doctor`), drop the
   `sources/` references, and put `utils/Env` on `PATH`. **Repoint `~/HEP/setup.sh`** (approval).
4. **`utils/Env/hep`**, a bash dispatcher:
   - `hep build` → `make`;
   - `hep run` / `hep watch` → `utils/Env/run`, which says "arrives in P1" until then.
5. **`utils/Env/runner/`** starts with three modules: `errors.py` (`HepError`, did-you-mean),
   `paths.py` (the root markers are `configs/`, `modules/` and `utils/Env/`, plus the 03 §2 rules),
   and `cli.py` (argparse). Also `tests/runner/test_imports.py` (the rank rule, 02 §3) and
   `tests/runner/test_paths.py`.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | fresh shell: `load_hep && hep --help` | lists `run`, `watch`, `build` |
| 2 | `hep build` from an empty `build/` | `build/Rivet/Rivet_photo_eic.so` plus `.info` and `.plot`; nothing else fails |
| 3 | `make` a second time | 0 compilations and 0 `*-config` probes (count the probes in `flags.sh`) |
| 4 | `touch modules/PhotoProduction/Rivet/photo_eic.plot && make` | the `.plot` is re-copied; the `.so` is not relinked |
| 5 | a scratch source with `// requires: nosuchlib` | fails, naming the library |
| 6 | `rivet --list-analyses photo_eic` with `RIVET_ANALYSIS_PATH=build/Rivet` | found |
| 7 | `make test` | `tests/runner` passes (paths, imports) |

**Done when** every row of S1–S2 passes.

---

## Rollback

`git reset --hard rework/v1-final`. To run v1 without rolling back:
`git worktree add ../High-Energy-v1 rework/v1-final`, then build it there with its CMake.

## Log

*(filled during execution)*
