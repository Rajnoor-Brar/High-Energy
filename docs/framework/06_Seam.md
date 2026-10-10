# 06 — P3: The seam

**Goal.** Change HEimdall's code so that it runs from `$HEP/HEimdall` against any work dir. That
means:
- the two roots, the `HEP_*` names and the placeholders (S1);
- the build split, `hep setup` and `hep where`, and portability (S2);
- the tests on the fixture work dir, and provenance (S3).

Every task cites its C-row in [01 §6](01_Target.md#6-every-coupling-classified), and the contract
is 01 §5. Nothing outside HEimdall changes. High-Energy's own files are P5's.

**Overlap with P2** (02 §8):
- S1, and S2's Python, may run while the stack builds.
- The rows that compile or need the stack (S2 R6–R9, all of S3) wait for P2.

**Reads:** 01 §4–§6, the knowledge ledger's rows for any tool folder touched (07 §3, 02 §10).

**Writes:** HEimdall only, as one commit per step.

**Gates:** none expected. A row failing twice is one (02 §5.2).

**Mechanical renames.** Every step uses these, in code, comments and messages alike. A comment that
names an old path is a wrong comment.

| Old | New |
|---|---|
| `utils/Env/runner/` | `runner/` |
| `utils/Env/<folder>/` (the 16 plugin folders) | `tools/<folder>/` |
| `utils/Env/schema/`, `utils/Env/quantities.toml`, `utils/Env/latex.toml` | `schema/` |
| `utils/Env/stack.toml`, `stack.py`, `flags.sh`, `hep_env.sh` | `env/` |
| `utils/Env/hep`, `utils/Env/run` | `bin/` |
| `utils/Env/patches/` | `stack/patches/` |
| `utils/Status.hh`, `Kit.hh`, `Module.hh`, `PythiaRun.hh`, `hepkit.py` | `kit/` |
| `utils/App_*.cc`, `utils/Apps/Paint/` | `apps/`, `apps/Paint/` |
| `docs/stack/` | `stack/` |
| `HEKIT_ROOT`, `HEKIT_CONFIGS`, `HEKIT_OUTPUT`, `HEKIT_RESULTS`, `HEKIT_REPORTS` | `HEP_FW`, `HEP_CONFIGS`, `HEP_OUTPUT`, `HEP_RESULTS`, `HEP_REPORTS` |

---

## S1: the roots, the names, the placeholders

**Preconditions:**
- P1 is verified.
- P2 S1 is `done` (the recipes and `hep_env.sh` are committed).

**Tasks:**

1. **`runner/paths.py`** (C1–C4; 01 §5.2–5.3):
   - `fw_root()`: `Path(__file__).resolve().parents[1]`. It must hold `runner/`, `tools/` and
     `schema/run.toml`. When `$HEP_FW` is set and resolves elsewhere: `HepError("two frameworks:
     $HEP_FW is <x>, this is <y>", hint="source the setup.sh of the one you mean")`.
   - `work_root()`: `$HEP_WORK` (it must hold a `hep.toml` with `[work]`), else the walk up from
     `Path.cwd()`. Markers under `fw_root()/tests/` are skipped. Nothing found:
     `HepError("not inside a work dir", hint="cd into one, or make one: hep setup <dir>")`. Cache it
     per process (`functools.cache`). Tests clear the cache.
   - The derived roots of 01 §5.2: `configs_root`, `output_root`, `results_root`, `reports_root`
     (each reads its `HEP_*` variable first, and only then calls `work_root()`), `work_build`,
     `fw_build`, `datasets_root`. `repo_root()` and `build_root()` are removed, with no alias: the
     callers are all listed below.
   - `RETIRED = {"HEKIT_ROOT": "HEP_FW", "HEKIT_CONFIGS": "HEP_CONFIGS", "HEKIT_OUTPUT":
     "HEP_OUTPUT", "HEKIT_RESULTS": "HEP_RESULTS", "HEKIT_REPORTS": "HEP_REPORTS"}`, and a
     `check_retired()` that `cli.main` calls first. A set name refuses the command and names its
     replacement.
   - `ROOTS` as in 01 §5.3; `./` → `work_root()`.
2. **The framework's files** (C5–C11, C13, C14, C17, C23–C30, C76). Replace each `repo_root() /
   "utils" / …` and `build_root()` call with `fw_root() / <new place>` or `fw_build()`, by the
   renames above. That covers:
   - `labels.py:22`;
   - `schema.py:35-36`;
   - `quantities.py:31,73,272`;
   - `config.py:847`;
   - `tools.py:36` (`ENV = fw_root() / "tools"`), `:105`, `:268`, `:326`;
   - `cli.py:708,808`;
   - `plot.py:127,168,292,328,397,486,1083,1118,1237`;
   - `deck.py:442`;
   - `docs.py:81,159,165,174`.

   `apps/Paint/Style.hh:110-115` (C76): look for `apps/Paint/base.toml` under `$HEP_FW` first, then
   beside `build/` from `/proc/self/exe`. The message names both.
3. **The work's files** (C22, C38): `hepfiles.py:73`, `tools/yoda/backend.py:313-314` and
   `tools/mpl/backend.py:102-103` use `work_build() / "Rivet"`. The backends may import `paths`
   (`PLUGINS_MAY_IMPORT`).
4. **Placeholders** (C15, C20, C34–C37, C32; 01 §5.3):
   - every context that held `"repo"` (`tools.py:215,264,671,928,994,1030,1046,1099,1324`,
     `execute.py:294`) holds `"fw"` and `"work"` instead;
   - the tool folders: `{fw}` in `pythia/tool.toml:4,44`, `yd2rt:5`, `plotmerge:12`, `herwig:33,48`;
     `{work}` in `rivet:15,26,29,42` and `merge:13`;
   - the folder check refuses `{repo}` in a `tool.toml`;
   - loading a run TOML refuses `{repo}`, with the hint of 01 §5.3;
   - `migrate.py` gets one rule, `{repo}` → `{work}` in run TOMLs, with a test;
   - `schema/run.toml:370`'s notes name `{work}` and `{fw}`.
5. **Messages** (C10, C16, C19, C25, C11): the paths and variables they name, by the renames.
   `cli.py:811` (`hep reproduce`) sets `HEP_OUTPUT` and `HEP_RESULTS`.
6. **`bin/hep` and `bin/run`** (C40, C30):
   - `bin/run` puts `fw_root()`, its parent's parent, on `sys.path`;
   - `bin/hep` finds the framework from its own location (`readlink -f`), and for `build` and `make`
     asks the runner for the work root (`python3 "$here/run" where --work`);
   - `--framework` makes `build` and `make` act on `$fw`;
   - the job count is `python3 -c 'import os; print(os.cpu_count())'`, not `nproc` (I15).
7. **`hep where`** (C31, 01 §5.8) in `cli.py`: three lines, or one with `--work`/`--fw`; exit 2
   when the asked-for root does not exist.
8. **`hep reproduce`'s seed** (C78), if `cli.py` still builds `run.<cfg>.seed_type` at `split/base`:
   the `run.cfgs.<cfg>.` form, and a test (`test_reproduce_random_seed`) in `tests/runner/test_house.py`.
9. **The docstrings** (C33, C43): `results.py:3` and `kit/hepkit.py:6` show the `.pth` way (`from
   runner import results`, `import hepkit`).
10. **`tests/runner/test_paths.py`** (C54), rewritten for 01 §5.2–5.3. Name the new tests so the rows
   can select them: `test_where_*`, `test_retired_*`, `test_repo_placeholder_*`,
   `test_fixture_marker_skipped`.
11. Commit: `P3.S1: two roots (fw, work), HEP_* names, {fw}/{work}`.

**Verification** (from `$HEP/HEimdall`, after `source $HEP/setup.sh`):

| # | Command | Expected |
|---|---|---|
| R1 | `grep -rn 'repo_root\|build_root\|utils/Env\|utils/Apps\|utils/App_\|{repo}' runner tools bin env schema kit apps \| grep -v 'test_\|retired\|RETIRED' \| wc -l` | `0` |
| R2 | `grep -rn 'HEKIT_' runner tools bin env kit apps \| grep -vi 'retired' \| wc -l` | `0` |
| R3 | `python3 -m pytest -q tests/runner/test_paths.py tests/runner/test_imports.py -p no:cacheprovider 2>&1 \| tail -1` | `N passed`, 0 failed |
| R4 | `cd "$(mktemp -d)" && hep where --work; echo "exit $?"` | `exit 2` |
| R5 | `cd $HEP/HEimdall/tests/fixtures/work/configs && hep where --work; echo "exit $?"` | `exit 2` (the fixture is skipped) |
| R6 | `HEP_WORK=$HEP/HEimdall/tests/fixtures/work hep where --work` | `<HEP>/HEimdall/tests/fixtures/work`, exit 0 |
| R7 | `HEKIT_ROOT=/x hep where 2>&1 \| grep -c 'HEP_FW'` | `1` (refused, naming the replacement) |
| R8 | `python3 -m pytest -q tests/runner -k "repo_placeholder or retired or where" -p no:cacheprovider 2>&1 \| tail -1` | ≥ `4 passed`, 0 failed |

---

## S2: the build, `hep setup`, portability

**Preconditions:** S1 `done`.

**Tasks:**

1. **The Makefile split** (C44, I8; 01 §5.4):
   - **`Makefile`** keeps the rule machinery, with the inputs re-rooted: `APP_SRCS := $(wildcard
     apps/App_*.cc) $(wildcard apps/*/main.cc)`, `-I kit`, the flags from `env/flags.sh`, and the
     targets `all tests test test-slow configure list schema docs clean`. Herwig's repository
     stays.
   - **`make/work.mk`** holds the module, Rivet and named-source rules: `-I $(HEP_FW)/kit -I
     modules/<P>`, its own `build/flags.mk` from `$(HEP_FW)/env/flags.sh`, and `all` (programs and
     plugins). It starts with a guard: `$(if $(HEP_FW),,$(error HEP_FW is not set: load_hep
     first))`.
   - `Makefile:120`'s `sed -i '1s|…|…|' f` becomes `sed '1s|…|…|' f > f.tmp && mv f.tmp f`, so it
     works on macOS (I15).
2. **`templates/work/`** (01 §4.1): `hep.toml` (placeholders `{name}`, `{revision}`, `{date}`),
   `Makefile` (one `include` line plus a comment), `.gitignore`, `README.md`, `CLAUDE.md`, and
   `starter/`:
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
3. **`runner/setup.py`** (rank 5, entered in `RANKS`) and `hep setup <dir> [--project P] [--git]
   [--adopt]` (C31; README §3.1, 01 §4):
   - It lays the template down (not `starter/`, which only `--project` uses) and never overwrites.
     It prints one line `added <path>` per path it adds, and nothing else on success.
   - A non-empty directory without a marker is refused (exit 2) unless `--adopt` is given. With
     `--adopt`, an existing `.gitignore` is kept, and the template lines it lacks are printed.
   - `[work] name` is the directory's name unless `--name` gives one. `[framework] expects` is
     HEimdall's `git rev-parse HEAD`, or `""` when it is dirty.
   - Nothing is written outside `<dir>`.
   - `--git` runs `git init` and makes a first commit of the template files, by path.
4. **Portability** (I15):
   - **`runner/events.py`:** on Linux, unchanged (abstract `@hep-watch-<pid>`, found in
     `/proc/net/unix`). Elsewhere, a socket file `hep-watch-<pid>.sock` in
     `${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}/hep-watch-<uid>/`:
     - `hubs()` lists that folder;
     - `connect()` takes the path;
     - the Hub removes its file on close;
     - a file that refuses a connection is stale, and is removed.

     This is the only place where "runtime state stays off disk" (the user, 2026-10-03) cannot
     hold: macOS has no abstract sockets. Say so in the module's docstring.
   - Paint's `Style.hh` (C76, done in S1); `bin/hep`'s core count (S1); the Makefile's `sed`
     (task 1).
   - `env/hep_env.sh` on macOS: `DYLD_LIBRARY_PATH` stays the annex's `setup_extra`
     (stack/mac/mac.toml).
5. **`tests/runner/test_setup.py`** for task 3, covering the rows below, in `tmp_path`.
6. Commit: `P3.S2: Makefile and make/work.mk, hep setup, portability`.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `d=$(mktemp -d)/w && hep setup $d && (cd $d && find . -not -path . \| wc -l)` | the template's count: 12 (`hep.toml Makefile .gitignore README.md CLAUDE.md` and the 7 folders) |
| R2 | `hep setup $d \| grep -c 'added'` | `0` (the second run adds nothing) |
| R3 | `e=$(mktemp -d) && touch $e/x && hep setup $e; echo "exit $?"` | `exit 2` |
| R4 | `cd $d/configs && hep where --work` | `$d` |
| R5 | `hep setup $d --project Toy && cd $d && hep check Toy/toy; echo "exit $?"` | `exit 0` |
| R6 | `cd $d && hep build; echo "exit $?"` (after P2) | `exit 0`, nothing to build (`make: Nothing to be done` or no targets) |
| R7 | `hep build --framework && ls $HEP/HEimdall/build/*.exe \| wc -l` (after P2) | `4` (App_Pythia, App_PythiaCheck, App_yd2rt, Paint) |
| R8 | `test -f $HEP/HEimdall/build/Herwig/HerwigDefaults.rpo && echo ok` (after P2) | `ok` |
| R9 | `grep -c '^FOUND' $HEP/HEimdall/build/flags.mk && grep '^FOUND' $HEP/HEimdall/build/flags.mk \| wc -w` (after P2) | `1`, then `15`: `FOUND :=` and the 13 names (`pythia8 hepmc3 yoda root fastjet lhapdf rivet geant4 toml zstd zlib onnx delphes`) |
| R10 | `python3 -m pytest -q tests/runner/test_setup.py -p no:cacheprovider 2>&1 \| tail -1` | `N passed`, 0 failed |

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
   - `FW = parents[1]`, and `FW` on `sys.path`;
   - sync `tests/fixtures/work/` into `build/scratch/work/` (copy what changed, never touch its
     `build/`);
   - set `HEP_WORK`, `HEP_OUTPUT`, `HEP_RESULTS`, `HEP_REPORTS` and clear `HEP_CONFIGS`;
   - basetemp `build/scratch/pytest`;
   - the guard: `OURS` only;
   - a session fixture `work_built` that runs `make -C build/scratch/work all` once, for the tests
     that need module programs or plugins.
2. **The test files** (C53–C64, C74–C75): by the renames, and as 01 §6.4 says for each.
   - The integration tests that used `REPO / "build" / …` take `fw_build()` for the apps and
     `work_built` for the modules.
   - `test_docs.py` (C61) scans `runner tools kit apps env bin tests make` and checks
     `CLAUDE.md`'s links instead of `bots/BOT.md`'s.
3. **Provenance** (C21; 01 §5.6): `record.git_state()` takes a root, `provenance()` writes `git =
   {framework, work}`, `hep` and `work`; `hep reproduce` warns when either revision differs.
   - Add `tests/runner/test_provenance.py`. A point planned in the scratch work dir, which is not a
     git repo, gives `work = {}` and a framework revision equal to `git -C $HEP_FW rev-parse HEAD`.
4. Commit: `P3.S3: tests on the fixture work dir; provenance with two revisions`.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `python3 -m pytest -q -m "not slow" -p no:cacheprovider 2>&1 \| tail -1` | `N passed[, K skipped]`, 0 failed, 0 errors. Record N and K; every skip's reason is listed in the step's log, and with `packages=all` none should name a missing tool |
| R2 | `python3 -m pytest --collect-only -q -p no:cacheprovider 2>&1 \| tail -1` | ≥ `416` tests (309 test functions in `tests/runner` and 107 in `tests/integration` at 9cb907a, before parametrisation), plus the new ones |
| R3 | `git -C $HEP/HEimdall status --porcelain tests/fixtures tests/reference \| wc -l` | `0` (the guard held) |
| R4 | `ls $HEP/HEimdall/build/scratch/work/build/Rivet/*.so \| wc -l` | `3` (photo_eic, Lamriv, particle_spectra) |
| R5 | `python3 -m pytest -q tests/runner/test_provenance.py -p no:cacheprovider 2>&1 \| tail -1` | `N passed`, 0 failed |
