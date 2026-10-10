# 06 — P3: The seam

**Goal.** Change Heimdall's code so that it runs from `~/Github/Heimdall` against any work dir.
That means:
- the two roots, the `HEP_*` names and the placeholders (S1);
- the build split, `hep setup` and `hep where`, and portability (S2);
- the tests on the fixture work dir, and provenance (S3).

Every task cites its C-row in [01 §6](01_Target.md#6-every-coupling-classified), and the contract
is 01 §5. Nothing outside Heimdall changes. High-Energy is left alone (D31).

**Overlap with P2** (02 §8):
- S1, and S2's Python, may run while the stack builds.
- The rows that compile or need the stack (S2 R6–R9, all of S3) wait for P2.

**Reads:** 01 §2–§6, the knowledge ledger's rows for any tool folder touched (07 §3, 02 §10).

**Writes:** Heimdall only, as one commit per step.

**Gates:** none expected. A row failing twice is one (02 §5.2).

**Mechanical renames.** Every step uses these, in code, comments and messages alike. A comment that
names an old path is a wrong comment. (P1 moved the files; these are the references to them.)

| Old | New |
|---|---|
| `utils/Env/runner/` | `framework/runner/` |
| `utils/Env/<folder>/` (the 16 plugin folders) | `framework/tools/<folder>/` |
| `utils/Env/schema/`, `utils/Env/quantities.toml`, `utils/Env/latex.toml` | `framework/schema/` |
| `utils/Env/hep`, `utils/Env/run` | `framework/bin/` |
| `utils/hepkit.py` | `framework/hepkit.py` |
| `utils/Env/stack.toml`, `stack.py`, `flags.sh`, `hep_env.sh` | `env/` |
| `utils/Env/patches/` | `patches/` |
| `utils/Status.hh`, `Kit.hh`, `Module.hh`, `PythiaRun.hh`, `utils/App_*.cc`, `utils/Apps/Paint/` | `src/` (the same names under it) |
| `build/App_*.exe`, `build/Paint.exe`, `build/Herwig/` (the framework's) | `framework/Apps/` |
| `build/flags.mk`, `build/deps/`, `build/tests/`, `output/tests/` (the framework's) | `forge/make/`, `forge/make/deps/`, `forge/tests/`, `forge/scratch/` |
| `docs/stack/build_stack.py`, `packages.toml`, `settings.toml`; `docs/stack/mac/`; the Dockerfile | the root; `platforms/mac/`; `platforms/container/` |
| `HEKIT_ROOT`, `HEKIT_CONFIGS`, `HEKIT_OUTPUT`, `HEKIT_RESULTS`, `HEKIT_REPORTS` | `HEP`, `HEP_CONFIGS`, `HEP_OUTPUT`, `HEP_RESULTS`, `HEP_REPORTS` |

---

## S1: the roots, the names, the placeholders

**Preconditions:**
- P1 is verified.
- P2 S1 is `done` (the recipes and `env/hep_env.sh` are committed).

**Tasks:**

1. **`framework/runner/paths.py`** (C1–C4; 01 §5.2–5.3):
   - `hep_root()`: `Path(__file__).resolve().parents[2]`. It must hold `framework/runner/`,
     `framework/tools/` and `framework/schema/run.toml`. When `$HEP` is set and resolves elsewhere:
     `HepError("two Heimdalls: $HEP is <x>, this is <y>", hint="source the setup.sh of the one you
     mean")`.
   - `work_root()`: `$HEP_WORK` (it must hold a `hep.toml` with `[work]`), else the walk up from
     `Path.cwd()`. Markers under `hep_root()/tests/` are skipped. Nothing found:
     `HepError("not inside a work dir", hint="cd into one, or make one: hep setup <dir>")`. Cache it
     per process (`functools.cache`). Tests clear the cache.
   - The derived roots of 01 §5.2: `configs_root`, `output_root`, `results_root`, `reports_root`
     (each reads its `HEP_*` variable first, and only then calls `work_root()`), `work_build`,
     `datasets_root`, `apps_dir`, `forge_dir`. `repo_root()` and `build_root()` are removed, with no
     alias: the callers are all listed below.
   - `RETIRED = {"HEKIT_ROOT": "HEP", "HEKIT_CONFIGS": "HEP_CONFIGS", "HEKIT_OUTPUT":
     "HEP_OUTPUT", "HEKIT_RESULTS": "HEP_RESULTS", "HEKIT_REPORTS": "HEP_REPORTS"}`, and a
     `check_retired()` that `cli.main` calls first. A set name refuses the command and names its
     replacement.
   - `ROOTS` as in 01 §5.3; `./` → `work_root()`.
2. **Heimdall's files** (C5–C11, C13, C14, C17, C23–C30, C76). Replace each `repo_root() / "utils" /
   …` and `build_root()` call with `hep_root() / <new place>`, `apps_dir()` or `forge_dir()`, by the
   renames above. That covers:
   - `labels.py:22`;
   - `schema.py:35-36`;
   - `quantities.py:31,73,272`;
   - `config.py:847`;
   - `tools.py:36` (`ENV = hep_root() / "framework" / "tools"`), `:105`, `:268`, `:326`;
   - `cli.py:708,808`;
   - `plot.py:127,168,292,328,397,486,1083,1118,1237`;
   - `deck.py:442`;
   - `docs.py:81,159,165,174`.

   `src/Apps/Paint/Style.hh:110-115` (C76): look for `src/Apps/Paint/base.toml` under `$HEP` first,
   then three levels above `/proc/self/exe` (`framework/Apps/Paint.exe`). The message names both.
3. **The work's files** (C22, C38): `hepfiles.py:73`, `framework/tools/yoda/backend.py:313-314` and
   `framework/tools/mpl/backend.py:102-103` use `work_build() / "Rivet"`. The backends may import
   `paths` (`PLUGINS_MAY_IMPORT`).
4. **Placeholders** (C15, C20, C34–C37, C32; 01 §5.3):
   - every context that held `"repo"` (`tools.py:215,264,671,928,994,1030,1046,1099,1324`,
     `execute.py:294`) holds `"hep"` and `"work"` instead;
   - the tool folders: `{hep}/framework/Apps/…` in `pythia/tool.toml:4,44`, `yd2rt:5`,
     `plotmerge:12`, `herwig:33,48`; `{work}/build/Rivet` in `rivet:15,26,29,42` and `merge:13`;
   - the folder check refuses `{repo}` in a `tool.toml`;
   - loading a run TOML refuses `{repo}`, with the hint of 01 §5.3;
   - `migrate.py` gets one rule, `{repo}` → `{work}` in run TOMLs, with a test;
   - `framework/schema/run.toml:370`'s notes name `{work}` and `{hep}`.
5. **Messages** (C10, C16, C19, C25, C11): the paths and variables they name, by the renames.
   `cli.py:811` (`hep reproduce`) sets `HEP_OUTPUT` and `HEP_RESULTS`.
6. **`framework/bin/hep` and `framework/bin/run`** (C40, C30):
   - `run` puts `hep_root()/framework` on `sys.path` (its own parent's parent);
   - `hep` finds Heimdall from its own location (`readlink -f`, two levels up), and for `build` and
     `make` asks the runner for the work root (`python3 "$here/run" where --work`);
   - `--framework` makes `build` and `make` act on Heimdall;
   - the job count is `python3 -c 'import os; print(os.cpu_count())'`, not `nproc` (I15).
7. **`hep where`** (C31, 01 §5.8) in `cli.py`: two lines, or one with `--hep` or `--work`; exit 2
   when the root asked for does not exist.
8. **`hep reproduce`'s seed** (C78), if `cli.py` still builds `run.<cfg>.seed_type` at
   `split/base`: the `run.cfgs.<cfg>.` form, and a test (`test_reproduce_random_seed`) in
   `tests/runner/test_house.py`.
9. **The docstrings** (C33, C43): `results.py:3` and `framework/hepkit.py:6` show the `.pth` way
   (`from runner import results`, `import hepkit`).
10. **`tests/runner/test_paths.py`** (C54), rewritten for 01 §5.2–5.3. Name the new tests so the
    rows can select them: `test_where_*`, `test_retired_*`, `test_repo_placeholder_*`,
    `test_fixture_marker_skipped`.
11. Commit: `P3.S1: two roots (hep, work), HEP_* names, {hep}/{work}`.

**Verification** (from `$HEP`, after `source $HEP/setup.sh`):

| # | Command | Expected |
|---|---|---|
| R1 | `grep -rn 'repo_root\|build_root\|utils/Env\|utils/Apps\|utils/App_\|{repo}' framework env src \| grep -v 'test_\|retired\|RETIRED' \| wc -l` | `0` |
| R2 | `grep -rn 'HEKIT_\|HEP_FW' framework env src \| grep -vi 'retired' \| wc -l` | `0` |
| R3 | `python3 -m pytest -q tests/runner/test_paths.py tests/runner/test_imports.py -p no:cacheprovider 2>&1 \| tail -1` | `N passed`, 0 failed |
| R4 | `cd "$(mktemp -d)" && hep where --work; echo "exit $?"` | `exit 2` |
| R5 | `cd $HEP/tests/fixtures/work/configs && hep where --work; echo "exit $?"` | `exit 2` (the fixture is skipped) |
| R6 | `HEP_WORK=$HEP/tests/fixtures/work hep where --work` | `<HEP>/tests/fixtures/work`, exit 0 |
| R7 | `HEKIT_ROOT=/x hep where 2>&1 \| grep -c 'HEP'` | ≥ `1` (refused, naming the replacement) |
| R8 | `python3 -m pytest -q tests/runner -k "repo_placeholder or retired or where" -p no:cacheprovider 2>&1 \| tail -1` | ≥ `4 passed`, 0 failed |

---

## S2: the build, `hep setup`, portability

**Preconditions:** S1 `done`.

**Tasks:**

1. **The Makefile split** (C44, I8; 01 §5.4):
   - **`Makefile`** (the root) keeps the rule machinery, with the inputs and outputs re-rooted:
     - `APP_SRCS := $(wildcard src/App_*.cc) $(wildcard src/Apps/*/main.cc)`;
     - the outputs go to `framework/Apps/`, the dependency files to `forge/make/deps/`, the flags to
       `forge/make/flags.mk` (from `env/flags.sh`), and the C++ tests to `forge/tests/`;
     - `-I src`;
     - the targets `all tests test test-slow configure list schema docs clean`;
     - Herwig's repository goes to `framework/Apps/Herwig/`;
     - `clean` empties `framework/Apps/`, `forge/make/` and `forge/tests/`, and never touches
       `stack/`, `stash/` or `forge/<pkg>/`.
   - **`framework/work.mk`** holds the module, Rivet and named-source rules:
     - `-I $(HEP)/src -I modules/<P>`;
     - the work dir's own `build/flags.mk` from `$(HEP)/env/flags.sh`;
     - `all` (programs and plugins);
     - it starts with a guard: `$(if $(HEP),,$(error HEP is not set: load_hep first))`.
   - `Makefile:120`'s `sed -i '1s|…|…|' f` becomes `sed '1s|…|…|' f > f.tmp && mv f.tmp f`, so it
     works on macOS (I15).
2. **`framework/templates/work/`** (01 §4.1): `hep.toml` (placeholders `{name}`, `{revision}`,
   `{date}`), `Makefile` (`include $(HEP)/framework/work.mk`, plus a comment), `.gitignore`,
   `README.md`, `CLAUDE.md`, `.vscode/settings.json` (D33), and `starter/`:
   - `starter/run.toml`, which `--project <P>` writes as `configs/<P>/<p>.toml`, with `<p>` the
     project lowercased:
     ```toml
     # configs/{P}/{p}.toml — a starter (hep setup --project). Two PDFs, 500 events each: hep run {P}/{p} --plan
     [run]
     name          = "{p}"
     project       = "{P}"
     configuration = "pdf"
     event_count   = 500
     threads       = 2

     [run.cfgs.pdf]
     description = "Two proton PDFs; jets in pp at 13 TeV"
     sweeps      = ["pdf"]
     tools       = [["pythia", "rivet"], "yd2rt"]

     [prelim]
     fifo = ["events.hepmc"]

     [quantities.pdf]
     values = ["LHAPDF6:CT14lo", "LHAPDF6:NNPDF23_lo_as_0130_qed"]
     tags   = ["CT14lo", "NNPDF23lo"]
     labels = ["CT14 LO", "NNPDF 2.3 LO"]

     [tools.pythia]
     tool        = "pythia"
     baseconfig  = "{p}.cmnd"
     output_file = "events.hepmc"

     [tools.rivet]
     tool        = "rivet"
     input       = "events.hepmc"
     analyses    = ["MC_JETS"]
     output_file = "{p}.yoda"

     [tools.yd2rt]
     tool        = "yd2rt"
     input       = "{p}.yoda"
     output_file = "{p}.root"

     [plot]
     formats = ["pdf", "png"]
     ```
   - `starter/run.cmnd`, written as `configs/<P>/<p>.cmnd`:
     ```
     ! configs/{P}/{p}.cmnd — the physics: QCD jets in pp at 13 TeV (the PDF is swept by the run TOML).
     Beams:idA = 2212
     Beams:idB = 2212
     Beams:eCM = 13000.
     HardQCD:all = on
     PhaseSpace:pTHatMin = 50.
     ```
   - If `hep check` refuses the starter (a key the schema has moved), fix the starter, not the
     schema. The starter follows the framework.
3. **`framework/runner/setup.py`** (rank 5, entered in `RANKS`) and `hep setup <dir> [--project P]
   [--git] [--adopt] [--name N]` (C31; README §3.1, 01 §4):
   - It lays the template down (not `starter/`, which only `--project` uses) and never overwrites.
     It prints one line `added <path>` per path it adds, and nothing else on success.
   - A non-empty directory without a marker is refused (exit 2) unless `--adopt` is given. With
     `--adopt`, an existing `.gitignore` is kept, and the template lines it lacks are printed.
   - `[work] name` is the directory's name unless `--name` gives one. `[framework] expects` is
     Heimdall's `git rev-parse HEAD`, or `""` when it is dirty.
   - Nothing is written outside `<dir>`.
   - `--git` runs `git init` and makes a first commit of the files it wrote, by path.
4. **Portability** (I15):
   - **`framework/runner/events.py`:** on Linux, unchanged (abstract `@hep-watch-<pid>`, found in
     `/proc/net/unix`). Elsewhere, a socket file `hep-watch-<pid>.sock` in
     `${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/hep-watch-<uid>/`:
     - `hubs()` lists that folder;
     - `connect()` takes the path;
     - the Hub removes its file on close;
     - a file that refuses a connection is stale, and is removed.

     This is the only place where "runtime state stays off disk" (the user, 2026-10-03) cannot
     hold: macOS has no abstract sockets. Say so in the module's docstring.
   - Paint's `Style.hh` (C76, done in S1); `framework/bin/hep`'s core count (S1); the Makefile's
     `sed` (task 1).
   - `env/hep_env.sh` on macOS: `DYLD_LIBRARY_PATH` stays the annex's `setup_extra`
     (`platforms/mac/mac.toml`), now written to `stack/setup_extra.sh` (C45).
5. **`tests/runner/test_setup.py`** for task 3, covering the rows below, in `tmp_path`.
6. Commit: `P3.S2: Makefile and framework/work.mk, hep setup, portability`.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `d=$(mktemp -d)/w && hep setup $d && (cd $d && find . -not -path . \| wc -l)` | the template's count: 14 (`hep.toml Makefile .gitignore README.md CLAUDE.md .vscode .vscode/settings.json` and the 7 folders) |
| R2 | `hep setup $d \| grep -c 'added'` | `0` (the second run adds nothing) |
| R3 | `e=$(mktemp -d) && touch $e/x && hep setup $e; echo "exit $?"` | `exit 2` |
| R4 | `cd $d/configs && hep where --work` | `$d` |
| R5 | `hep setup $d --project Toy && cd $d && hep check Toy/toy; echo "exit $?"` | `exit 0` |
| R6 | `cd $d && hep build; echo "exit $?"` (after P2) | `exit 0`, nothing to build (`make: Nothing to be done` or no targets) |
| R7 | `hep build --framework && ls $HEP/framework/Apps/*.exe \| wc -l` (after P2) | `4` (App_Pythia, App_PythiaCheck, App_yd2rt, Paint) |
| R8 | `test -f $HEP/framework/Apps/Herwig/HerwigDefaults.rpo && echo ok` (after P2) | `ok` |
| R9 | `grep -c '^FOUND' $HEP/forge/make/flags.mk && grep '^FOUND' $HEP/forge/make/flags.mk \| wc -w` (after P2) | `1`, then `15`: `FOUND :=` and the 13 names (`pythia8 hepmc3 yoda root fastjet lhapdf rivet geant4 toml zstd zlib onnx delphes`) |
| R10 | `python3 -m pytest -q tests/runner/test_setup.py -p no:cacheprovider 2>&1 \| tail -1` | `N passed`, 0 failed |
| R11 | `git -C $HEP status --porcelain \| wc -l` | `0` (the build's outputs are all ignored) |

**On failure:** R9 short means the probe ran without `load_hep` (L22). The key includes the tools'
paths, so the next make with the environment loaded probes again. Run `hep build --framework
--configure` and check.

---

## S3: the tests and provenance

**Preconditions:**
- S2 `done`.
- P2 verified: the tests need the stack.

**Tasks:**

1. **`tests/conftest.py`** (C52; 01 §5.7):
   - `HEP = parents[1]`, and `HEP/framework` on `sys.path`;
   - sync `tests/fixtures/work/` into `forge/scratch/work/` (copy what changed, never touch its
     `build/`);
   - set `HEP_WORK`, `HEP_OUTPUT`, `HEP_RESULTS`, `HEP_REPORTS` and clear `HEP_CONFIGS`;
   - basetemp `forge/scratch/pytest`;
   - the guard: `OURS` only;
   - a session fixture `work_built` that runs `make -C forge/scratch/work all` once, for the tests
     that need module programs or plugins.
2. **The test files** (C53–C64, C74–C75): by the renames, and as 01 §6.4 says for each.
   - The integration tests that used `REPO / "build" / …` take `apps_dir()` for the apps and
     `work_built` for the modules.
   - `test_docs.py` (C61) scans `framework src tests` and the `Makefile`, and checks `CLAUDE.md`'s
     links instead of `bots/BOT.md`'s.
3. **Provenance** (C21; 01 §5.6): `record.git_state()` takes a root, and `provenance()` writes `git =
   {heimdall, work}`, `hep` and `work`. `hep reproduce` warns when either revision differs.
   - Add `tests/runner/test_provenance.py`. A point planned in the scratch work dir, which is not a
     git repo, gives `work = {}` and a Heimdall revision equal to `git -C $HEP rev-parse HEAD`.
4. Commit: `P3.S3: tests on the fixture work dir; provenance with two revisions`.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `python3 -m pytest -q -m "not slow" -p no:cacheprovider 2>&1 \| tail -1` | `N passed[, K skipped]`, 0 failed, 0 errors. Record N and K; every skip's reason is listed in the step's log, and with `packages=all` none should name a missing tool |
| R2 | `python3 -m pytest --collect-only -q -p no:cacheprovider 2>&1 \| tail -1` | ≥ `416` tests (309 test functions in `tests/runner` and 107 in `tests/integration` at 9cb907a, before parametrisation), plus the new ones |
| R3 | `git -C $HEP status --porcelain tests/fixtures tests/reference \| wc -l` | `0` (the guard held) |
| R4 | `ls $HEP/forge/scratch/work/build/Rivet/*.so \| wc -l` | `3` (photo_eic, Lamriv, particle_spectra) |
| R5 | `python3 -m pytest -q tests/runner/test_provenance.py -p no:cacheprovider 2>&1 \| tail -1` | `N passed`, 0 failed |
