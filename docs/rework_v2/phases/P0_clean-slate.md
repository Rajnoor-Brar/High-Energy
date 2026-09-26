# P0 — Clean slate

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| **done** (2026-09-26) | 2 | — | v1 deleted; the v2 tree, Makefile and shell in place; Rivet plugins build; nothing runs yet | 2026-09-26 |

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

### S1 — 2026-09-26 — done

- The user's uncommitted edits are in `stash@{0}`; `docs/Untitled-1.md` is in `output/_v1/`.
- The plan was committed as `8daff46`, and tagged **`rework/v1-final`** there.
- **Baseline (R4)**, v1 at `rework/v1-final`:

  | Setting | Value |
  |---|---|
  | command | `hep run configs/PhotoProduction/eic.toml --study single --set run.events=50000` |
  | results | `HEKIT_RESULTS=output/_v1/baseline` |
  | threads | 20 |
  | mode | `serial` (photo_eic cannot shard, L16) |
  | events accepted / attempted | 49,995 / 50,000 |
  | wall inside `hep-run` | **34.36 s**, i.e. **1,455 events/s** |
  | whole command | 44.7 s wall, 253 MB RSS |
  | σ | 73,078.39 ± 136.50 pb |
  | seeds | 680145921 … 680145940 |

- Row 4: 23 moves, all **R100**. One file added (`tests/reference/point_counts.toml`, with a
  `pages_v2` column: v2 draws a page even for a one-point configuration). 520 files deleted.
- Row 5: the tracked tree, excluding `aux/`, `literature/` and `docs/rework_v*`, went from
  **226,337 → 137,197 lines**. The rest is mostly `configs/`, `aux`-adjacent assets and data.
- Deviations:
  - **Lamriv parked with Lambda.** `Lamriv` went to `modules/Lambda/_v1/Rivet/`, not
    `modules/Lambda/Rivet/`, because it includes the parked `Reconstruction.hh`, which needs the
    deleted `Phys`.
  - **Legacy plot intermediates kept.** `tests/reference/legacy_run/{ydmrg,ydplt_p1}/` came along
    (the voided curves and `auto_range.plot`). They are the P3 test vectors.
  - **Untracked leftovers moved, not deleted.** The old `build/`, `output/scratch/`,
    `output/PhotoProduction/`, `.pytest_cache/` and the `__pycache__` trees are in `output/_v1/`.
  - **Old stub backed up.** `~/HEP/setup.sh` was repointed to `utils/Env/hep_env.sh`; the old one is
    `~/HEP/setup.sh.pre-v2`.
  - **`rework_v1/README.md` banner.** It now opens with a banner pointing at the tag, for its 14
    links into the deleted docs.
  - **`hekit` is still installed in the venv.** It is an editable install in `~/HEP/.venv`, which was
    not touched. Its `hep` entry point is now dead, and S2 makes `utils/Env` come first on `PATH`.

### S2 — 2026-09-26 — done

| Row | Result |
|---|---|
| 1 | A fresh shell (`env -i`, then `source ~/HEP/setup.sh`) finds `hep` in `utils/Env/`, ahead of the venv's dead v1 entry point. `hep --help` lists run, watch and build. `hep run` says it arrives in P1 (exit 2). |
| 2 | `make` from an empty `build/`: `Rivet_photo_eic.so` plus `photo_eic.info`/`.plot`, in 9.4 s |
| 3 | A second `make`: *Nothing to be done*, and **0** probes (`build/flags.log` unchanged) |
| 4 | After touching `photo_eic.plot`, only the `cp` runs; `rivet-build` is not called |
| 5 | `// requires: nosuchlib`: *requires 'nosuchlib', which is not a known library (known: …)*. `// requires: none` builds with no library flags. |
| 6 | `rivet --list-analyses photo_eic` with `RIVET_ANALYSIS_PATH=build/Rivet`: found |
| 7 | `make test`: **15 passed** (paths 10, import ranks 4, plus the guard on results/ and configs/) |

**Deviations:**
- **Version probes kept.** `hep_env.sh` keeps its version probe as `hep_status`. The plan said to
  drop it as a duplicate of `hep doctor`, but `doctor` is gone, so it is now the only version view.
  The stub calls it on every load. Dropped instead: the doctor hook, click completion, and the
  `sources/` references.
- **`yoda-config` needs `--cppflags`** for its `-I`; `--cxxflags` gives only compiler flags.
- **`rivet-build` drops the path after `-MF`**, taking it for a file, so it gets the joined form
  `-MF<path>`. It also compiles a temporary copy of the source, so the recipe rewrites the `.d`
  file's first line to name the plugin. Header dependencies now reach Rivet plugins.
- **The import rule is "own rank or lower, and no cycles"**, not "strictly lower". Otherwise
  `paths → errors`, both rank 0, would already fail. 02 §3 is updated, and a cycle test is added.
- **One translation unit per app.** `utils/Apps/<X>/main.cc` is the only file compiled; the rest of
  the folder is headers it includes, as in the house header-only style.
- **pytest scratch in `output/tests/`.** pytest's temporary directories go to
  `output/tests/pytest` (`--basetemp`), so tests write only under `output/tests/`.
