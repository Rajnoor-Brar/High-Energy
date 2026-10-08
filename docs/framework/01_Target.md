# 01 — The target

What exists when the plans are done, and the contract between its parts. This page details
[README](README.md) §2's decisions without reopening them. Rows added here continue the numbering
(D17 onwards, §9).

The phase files (`03`–`09`, round 2b) say *how* to get here. This page says *what* "here" is, and
it gives three things those phases build on:
- the move map (§7);
- the classification of every coupling in the code (§6);
- the list of what the user keeps before the reinstall (§8).

Written 2026-10-08 against `rework` at `31817f8`. Every file:line below was checked by grep on that
day. Phase P1 pins its own revision, tagged `split/base`, and re-checks the rows against it.

---

## 1. Three places

| Place | Is | Made by | In git |
|---|---|---|---|
| `$HEP` (default `~/HEP`) | the machine's home: the stack, the venv, the framework, `setup.sh`, the agents' state | `stack/build_stack.py` (P2), the seeding (P1) | no; `$HEP/HEimdall` is |
| `$HEP/HEimdall` (`$HEP_FW`) | the framework: runner, tool folders, kits, apps, build rules, stack recipes, manual, tests | P1 (moves) and P3 (the seam) | its own repo, fresh history (D2) |
| a work dir (`$HEP_WORK`, or the one found from the working directory) | one workspace: configs, modules, datasets and what runs make of them | `hep setup <dir>` (D14); High-Energy by `hep setup --adopt` (D15) | its own repo, optional |

There is one `$HEP` per machine, and any number of work dirs, which share nothing but `$HEP`
(D4). The first work dir is **High-Energy itself**, made lean on branch `work`, at
`~/Github/High-Energy` (D15).

---

## 2. `$HEP`

```
$HEP/
  setup.sh             load_hep: exports HEP, HEP_INSTALL, HEP_FW; sources $HEP_FW/env/hep_env.sh   (P2, from stack/)
  .venv/               the venv (prompt "HEP"); site-packages/heimdall.pth: $HEP_FW and $HEP_FW/kit   (P2, P3)
  src/                 tarballs and unpacked sources (may be deleted after the build)                (P2)
  build/               the stack's build trees (may be deleted after the build)                      (P2)
  install/<dir>/       the stack: LHAPDF hepmc3 fastjet root yoda rivet pythia8 herwig7 delphes sherpa
                       madgraph whizard onnxruntime geant4                                           (P2)
  logs/<package>.log   one per package                                                               (P2)
  .stamps/             <package>-<release>: what is installed                                        (P2)
  .setup/              the agents' state: state.toml, log.md, kept/ (what came back after the wipe)  (P0; 02)
  HEimdall/            the framework (§3)                                                            (P1)
```

**Who writes where:**
- `build_stack.py` writes only `src/ build/ install/ logs/ .stamps/ .venv/` and `setup.sh`.
- The framework's own build (`hep build --framework`) writes only `HEimdall/build/`.
- A work dir's build never writes into `$HEP` (D5, amended).

---

## 3. HEimdall

```
HEimdall/
  README.md          what it is, how to install it (points to stack/ and docs/)        new
  CLAUDE.md          the framework's agent rules                                         from bots/BOT.md
  Makefile           the framework's build (§5.4)                                        from Makefile, split
  pytest.ini         testpaths = tests/runner tests/integration                          as is
  .gitignore         build/ __pycache__/ .pytest_cache/                                  new
  bin/               hep, run                                                            utils/Env/{hep,run}
  env/               hep_env.sh, flags.sh, stack.toml, stack.py                          utils/Env/
  runner/            the package, its 23 modules                                         utils/Env/runner/
  tools/<folder>/    every plugin folder (16): the tools custom delphes herwig madgraph merge module
                     plotmerge pythia rivet sherpa whizard yd2rt; the provider lhapdf; the backends yoda,
                     mpl; figures                                                        utils/Env/<folder>/
  schema/            run.toml, run.schema.json, quantities.toml, latex.toml              utils/Env/{schema/,*.toml}
  kit/               Status.hh Kit.hh Module.hh PythiaRun.hh hepkit.py                   utils/
  apps/              App_Pythia.cc App_PythiaCheck.cc App_yd2rt.cc Paint/                utils/
  make/work.mk       the module and Rivet rules a work dir includes (§5.4)               from Makefile, split
  stack/             build_stack.py packages.toml settings.toml build_by_hand.txt README.md
                     patches/ mac/ container/{Dockerfile,Dockerfile.dockerignore,heimdall.def}
                                                                                         docs/stack/, utils/Env/patches/; .def new
  templates/work/    hep.toml Makefile .gitignore README.md CLAUDE.md                    new (§4)
  docs/              01–07, README.md, audit_2/, framework/ (these plans)                docs/
  bots/              current_plan.md intent.md archive.md                                bots/
  tests/             conftest.py support.py runner/ integration/ cxx/ reference/
                     fixtures/work/{hep.toml,README.md,configs/,modules/,datasets/}      tests/; fixtures re-rooted (§5.7)
  build/             (ignored) App_*.exe Paint.exe Herwig/ flags.mk flags.log deps/ tests/ scratch/
```

**Why this shape:**
- **`tools/`** holds every folder the runner loads by path, as `utils/Env/<folder>/` did. The
  folder contract (06 §16) does not change. `runner/tools.py:36`'s `ENV` becomes `fw_root() /
  "tools"`, and nothing else in it moves. As a side effect, the yoda and rivet folders no longer
  sit on `sys.path` next to the real `yoda` and `rivet` packages (the hazard `hepkit.py`'s
  docstring warns about).
- **`schema/`** is the language a run TOML speaks: its keys, its quantity vocabulary, its label
  macros.
- **`env/`** is what the shell and make need before Python: `hep_env.sh`, `flags.sh`, and the stack
  registry that both read.
- **`kit/`** is what a module includes (`-I $HEP_FW/kit`) and what a Python tool imports, `hepkit`
  through the venv's `.pth`.
- **`apps/`** is the framework's own programs. They are compiled once per `$HEP` (D5).

The internals of `runner/` do not change, apart from the call sites in §6.

---

## 4. A work dir

### 4.1 What `hep setup <dir>` lays down

```
<dir>/
  hep.toml           the marker
  Makefile           include $(HEP_FW)/make/work.mk
  .gitignore         build/ output/ results/ datasets/* reports/* __pycache__/ *.exe
  README.md          what each folder is for; that datasets/ and reports/ are not in git
  CLAUDE.md          the work dir's agent rules: configs/ and modules/ are the user's; read the manual
                     at $HEP_FW/docs; never write into results/ from a test; stage by path
  configs/  modules/  datasets/  results/  output/  reports/  build/
```

With `--project <P>`, it also writes:
- `configs/<P>/<p>.toml`, a commented starter run TOML: one App_Pythia → Rivet chain at a few
  hundred events, with a `[plot]`, which `hep check <P>/<p>` accepts;
- `configs/<P>/<p>.cmnd`, its base card;
- an empty `modules/<P>/`.

Git does not keep empty folders. On a fresh clone of a work dir, `hep setup <dir>` (idempotent) makes
the missing ones again, so no `.gitkeep` files are needed.

### 4.2 `hep.toml`

```toml
# hep.toml — this folder is a HEimdall work dir (made by `hep setup`, 2026-…).
[work]
name = "High-Energy"

[framework]
expects = "<HEimdall's revision when this file was made>"
```

**What `hep.toml` means:**
- **`[work]`** marks the work dir. A `hep.toml` without it is not a marker.
- **`name`** is used in provenance and in `hep where`.
- **`[framework] expects`** is checked the way `[config.meta]` is (V97): warned about, never
  enforced. The runner warns once per command when `expects` is not an ancestor of HEimdall's
  `HEAD`, meaning the work dir was made with a framework newer than the one running. A dirty or
  missing revision is not warned about.
- Unknown keys are refused, as in every TOML the runner reads.

### 4.3 High-Energy as the first work dir (D15)

In P5, on branch `work` from `split/base`:
1. Remove every path the move map (§7) sends to HEimdall (`side = "fw"`).
2. Run `hep setup --adopt ~/Github/High-Energy`. It adds `hep.toml`, `Makefile`, `README.md`,
   `CLAUDE.md` and the missing key folders (`results/ output/ build/` exist untracked; `reports/`
   comes back from §8).
3. Merge the template's `.gitignore` into High-Energy's by hand. `--adopt` keeps the existing file
   and lists the template lines it is missing.
4. Rewrite `{repo}` as `{work}` with `hep migrate` (§5.3): one line today, at
   `configs/PhotoProduction/eic.toml:170`. Show the diff first, because configs are the user's.
5. Repoint I13's citations: `delphes_jets.py:16` loses its `sys.path` line;
   `Inproc/Analysis.hh:68` and the two `InProc*.toml:23` comments name
   `$HEP_FW/stack/patches/…`. Show the diff first.
6. Commit by path, then `git status` must be clean. Pushing `work` is a gate.

What stays (D13), unchanged:
- `configs/ modules/ aux/ _text/ _vs/ archive/ .vscode/ generator_comparison.* docs/Untitled-1.md`;
- untracked, brought back from §8: `datasets/ literature/ cross_machine/ reports/`.

---

## 5. The seam

### 5.1 Variables

| Variable | Set by | Means |
|---|---|---|
| `HEP` | `setup.sh` | the prefix |
| `HEP_INSTALL` | `setup.sh` | `$HEP/install` |
| `HEP_FW` | `setup.sh` (`${HEP_FW:-$HEP/HEimdall}`) | the framework: `bin/` on `PATH`, `make -C`. Replaces `HEKIT_ROOT` |
| `HEP_WORK` | the user, the tests | the work dir, instead of the search (§5.2) |
| `HEP_CONFIGS`, `HEP_OUTPUT`, `HEP_RESULTS` | the user, the tests | replace the work dir's `configs/`, `output/`, `results/` (V52's roles, renamed) |
| `HEP_SETUP`, `HEP_ENV_LOADED` | `hep_env.sh` | as today |
| `HEP_STATUS_FD` | the runner, per tool | as today |
| `LHAPDF_DATA_PATH`, `GEANT4_DATA_DIR`, `ONNXRUNTIME_DIR` | `hep_env.sh` | as today |
| `RIVET_ANALYSIS_PATH` | the rivet and merge folders, per run | `{work}/build/Rivet` |

**Retired:** `HEKIT_ROOT`, `HEKIT_CONFIGS`, `HEKIT_OUTPUT` and `HEKIT_RESULTS` (K15). If one of them
is set, every command refuses and names its replacement. A stale shell or script fails loudly, not
silently (01 §4.5 of the manual).

### 5.2 The two roots

`runner/paths.py` replaces `repo_root()` with two functions.

**`fw_root()`** is the framework the code is running from: `Path(__file__).resolve().parents[1]`.
- It must hold `runner/`, `tools/` and `schema/run.toml`.
- If `$HEP_FW` is set and resolves elsewhere, the command refuses: two frameworks in one shell. The
  convenient inference "use the variable" is refused (01 §4.5).

**`work_root()`** is the work dir:
1. If `$HEP_WORK` is set, it is that directory. It must hold a `hep.toml` with `[work]`, or the
   command is refused.
2. Otherwise, walk up from the working directory to `/`. The first directory whose `hep.toml` has
   a `[work]` table wins.
3. A marker under `fw_root()/tests/` is skipped: the fixture work dir is found only through
   `$HEP_WORK`, which the tests set to its scratch copy (§5.7).
4. If nothing is found: `HepError("not inside a work dir", hint="cd into one, or make one: hep
   setup <dir>")`.

This is the walk-up search the user chose (D3). V13's rule ("never by the working directory") was
about relative paths, and still holds: a path in a run TOML never resolves against the working
directory (§5.3).

**What hangs from each root:**

| Function | Is |
|---|---|
| `configs_root()` | `$HEP_CONFIGS` or `work_root()/configs` |
| `output_root()` | `$HEP_OUTPUT` or `work_root()/output` |
| `results_root()` | `$HEP_RESULTS` or `work_root()/results` |
| `work_build()` | `work_root()/build`: module programs, `Rivet/`, `deps/`, `flags.mk` |
| `fw_build()` | `fw_root()/build`: the apps, `Herwig/`, `flags.mk`, the C++ tests, `scratch/` |
| `datasets_root()` | `work_root()/datasets` |

**Which commands need which root:**

| Commands | Need |
|---|---|
| `run`, `plot`, `overlay`, `check`, `ls`, `status <config>`, `clean`, `reproduce`, `migrate`, `build`, `make` | a work dir |
| `explain`, `status --stack`, `build --framework`, `make --framework` | the framework only |
| `setup`, `where`, `watch` without a config | nothing; they run anywhere |

`hep watch` finds runs by their sockets machine-wide (06 §10). With a config, it resolves that
config in the current work dir.

### 5.3 Paths in a run TOML, and placeholders

**Convention roots** (04 §2; `paths.ROOTS`). Each has exactly one root, as before:

| Key | Root |
|---|---|
| `config`, `master`, `import`, `baseconfig`, `filters`, `root_style` | `configs_root()[/<P>]` |
| `executable` | `work_build()/<P>` |
| `data` | `datasets_root()` |

**The path rules:**
- A leading `./` means `work_root()`: V13 restated (D7).
- `/abs` is taken as written.
- `../` is refused.

**Placeholders.** `{repo}` is retired, and two placeholders replace it:

| Placeholder | Is | Used by |
|---|---|---|
| `{fw}` | `fw_root()` | `pythia/tool.toml` (`{fw}/build/App_Pythia.exe`, `App_PythiaCheck.exe`), `yd2rt`, `plotmerge` (`App_yd2rt.exe`), `herwig` (`{fw}/build/Herwig/HerwigDefaults.rpo`) |
| `{work}` | `work_root()` | `rivet` and `merge` (`{work}/build/Rivet`), a run TOML's own arguments and `[prelim.commands]` (`{work}/modules/…`) |

- **A run TOML that still says `{repo}`** is refused with a hint: "`{repo}` is retired: `{work}`
  for your files, `{fw}` for the framework's; `hep migrate` rewrites it". In a run TOML, `{repo}`
  only ever meant the user's files, so `hep migrate` rewrites it to `{work}` (a new rule in
  `runner/migrate.py`).
- **A tool folder that says `{repo}`** is a load error (folder checks, 06 §16.1).

### 5.4 The build

**`$HEP_FW/Makefile`** builds the framework into `fw_build()`:

| Source | Output |
|---|---|
| `apps/App_<X>.cc` | `build/App_<X>.exe` |
| `apps/Paint/main.cc` | `build/Paint.exe` |
| `tests/cxx/<X>.cc` | `build/tests/<X>.exe` |
| (Herwig, when on `PATH`) | `build/Herwig/HerwigDefaults.rpo`, as today (L15) |

- The targets are `all`, `tests`, `test`, `test-slow`, `configure`, `list`, `schema`, `docs` and
  `clean`.
- Includes come from `-I kit`.
- The flags are its own `build/flags.mk`, written by `env/flags.sh`.

**`$HEP_FW/make/work.mk`** is included by a work dir's one-line `Makefile`, and builds into
`work_build()`. It keeps today's rules (06 §15.1) for:
- `modules/<P>/<X>.cc` → `build/<P>/<X>.exe`;
- `modules/<P>/Rivet/<x>.cc` and `modules/<P>/Rivet_<x>.cc` → `build/Rivet/Rivet_<x>.so`, with
  their `.info`, `.plot` and `.yoda`;
- any `<dir>/<X>.cc` named on the command line, such as High-Energy's
  `generator_comparison.cc`.

It differs from today's rules in four ways:
- the includes are `-I $(HEP_FW)/kit -I modules/<P>`, and `rivet-build` gets the same;
- the flags are `<work>/build/flags.mk`, written by `$(HEP_FW)/env/flags.sh` with the same key
  logic (L22). The probe is shared, the caches are per tree (D5, amended);
- `all` is the modules and plugins only;
- there are no `tests`, `schema` or `docs` targets.

**Commands:**

| Command | Is |
|---|---|
| `hep build` | `make -C <work> all`. It warns when a framework app the work's tools need is missing: "run `hep build --framework`" |
| `hep build --framework` | `make -C $HEP_FW all` |
| `hep make …` | `make -C <work> …` |
| `hep make --framework …` | `make -C $HEP_FW …` |
| core count | `os.cpu_count()` through `hep`, not `nproc` (I15) |

Rebuilding a framework app changes the identity of every point, in every work dir, that ran it
(06 §27): the apps are shared. `hep build --framework` says so when it rebuilds an app.

### 5.5 Python

- **`bin/run`** puts `fw_root()` on `sys.path` and imports `runner.cli`.
  `runner/cli.py:778` (`hep reproduce`) runs `fw_root()/bin/run`.
- **The venv's `site-packages/heimdall.pth`** holds two lines, `$HEP_FW` and `$HEP_FW/kit`.
  - It is written by the stack's `python` step, when the venv is made (P2). `hep where` warns when
    it is missing or names another framework.
  - Any Python in the venv can then `from runner import results` (02 §11 of the manual) and `import
    hepkit`, with no `sys.path` lines. `delphes_jets.py:16` and `hepkit.py:6`'s example lose theirs.
- **Plugins** (`render.py`, `backend.py`, `provider.py`, the figures) are still loaded by path,
  from `fw_root()/tools/<folder>/` (`runner/plugins.py`).

### 5.6 Provenance and identity

`record.provenance()` (`record.py:266`) writes:

```json
"git":  {"framework": {"revision": "…", "dirty": false}, "work": {"revision": "…", "dirty": true}},
"hep":  "/home/…/HEP",
"work": {"name": "High-Energy", "root": "/home/…/Github/High-Energy"}
```

- A work dir that is not a git repo gives `{}` for `work`.
- `hep reproduce` reads both revisions and warns when either differs from now.
- **Identity is unchanged** (D8): `exe_sha256` and `files_sha256` hash contents, so the same
  App_Pythia gives the same identity from any work dir on one machine.

### 5.7 Tests

**The fixture work dir** is `tests/fixtures/work/`. It holds:
- `hep.toml`;
- `README.md` (today's `tests/fixtures/README.md`, re-rooted);
- `configs/`: today's `tests/fixtures/configs/`, moved as is;
- `modules/`: frozen copies of High-Energy's `modules/` at `split/base`, 18 files, because the tests
  build Lambda.exe, InprocJets.exe and the photo_eic, Lamriv and particle_spectra plugins;
- `datasets/zeus_eic.yoda`: 20 kB, the one dataset the plot tests name. It comes back from §8;
  2b checks whether any test actually reads it, and drops it if none does.

These copies are frozen like `configs/`: a change goes only together with the test that needs it.

**A session (`tests/conftest.py`):**
1. Sync `tests/fixtures/work/` into `build/scratch/work/`. Only changed files are copied, and
   `build/` there is never touched, so make rebuilds only what changed.
2. Set `HEP_WORK` to that copy, `HEP_OUTPUT` to `build/scratch/output`, and `HEP_RESULTS` to
   `build/scratch/results`.
3. Use `build/scratch/pytest` as the basetemp.
4. The integration tests that need module programs or plugins run `make -C build/scratch/work all`
   once per session (a session fixture).

**The guard** keeps V52's first half: `tests/fixtures/` and `tests/reference/` must come out byte
for byte. Its second half (`THEIRS`, the user's `results/ configs/ modules/`) goes. There are no
user folders in the framework repo, and no test may name a real work dir.

The test files that change are listed in §6.4.

### 5.8 The environment

**`setup.sh`** is written by `build_stack.py` from a template in `stack/`, replacing today's stub
(`build_stack.py:52-55`). It sets `HEP`, `HEP_INSTALL` and `HEP_FW`, then sources
`$HEP_FW/env/hep_env.sh`. `settings.toml`'s `hekit_root` goes: the framework is always
`$prefix/HEimdall`. A `setup.sh` already there is still kept.

**`hep_env.sh`** changes in three places:

| Lines | Becomes |
|---|---|
| `:10-17` | `HEP_FW` instead of `HEKIT_ROOT` |
| `:177` | `$HEP_FW/bin` on `PATH` instead of `utils/Env` |
| `:133-136` (`hep_cd PROJECT [dir]`) | cds into `$(hep where --work)/<dir>/<P>`, and refuses outside a work dir |

The rest is unchanged: `quit`, `hep_refresh`, `hep_status` and the `hep_src`/`hep_build`/
`hep_install` helpers. On macOS, the annex's `setup_extra` lines still add `DYLD_LIBRARY_PATH` and
the GNU tools (stack/mac).

**`hep where`** prints three lines: `hep=<prefix>`, `fw=<HEimdall root> <revision>` and
`work=<root or ->`. With `--work` or `--fw`, it prints one path, for scripts and agents. Its exit
code is 2 when the root asked for does not exist.

---

## 6. Every coupling, classified

This extends README §6. Each row names one call site at `31817f8` and what it becomes. P3's tasks
cite these rows by number (C1…).

**Kind:**
- *fw*: a framework file, found from `fw_root()`;
- *work*: under `work_root()`;
- *both*: the site needs both roots;
- *ok*: already derives from a root that §5.2 re-points, so it is unchanged.

### 6.1 The runner (`utils/Env/runner/`)

| # | Site | Today | Kind | Becomes |
|---|---|---|---|---|
| C1 | `paths.py:23-47` | `MARKERS`, `HEKIT_ROOT`, `repo_root()` by markers | — | `fw_root()`, `work_root()` (§5.2); the `HEKIT_*` guard |
| C2 | `paths.py:50-70` | `results/output/configs_root`, `build_root` | work | `HEP_*` variables; `work_build()`, `fw_build()` |
| C3 | `paths.py:77-86` | `ROOTS` | work | the table in §5.3 |
| C4 | `paths.py:104` | `./` → `repo_root()` | work | `work_root()` |
| C5 | `labels.py:22` | `utils/Env/latex.toml` | fw | `schema/latex.toml` |
| C6 | `schema.py:33` | `utils/Env/schema/run.toml` | fw | `schema/run.toml` |
| C7 | `quantities.py:31` | `utils/Env/quantities.toml` | fw | `schema/quantities.toml` |
| C8 | `quantities.py:73` | glob `utils/Env/*/quantities.toml` | fw | `tools/*/quantities.toml` |
| C9 | `quantities.py:272` | `utils/Env/<name>/provider.py` | fw | `tools/<name>/provider.py` |
| C10 | `quantities.py:78` (hint) | "add it to utils/Env/quantities.toml" | fw | names `schema/quantities.toml` |
| C11 | `config.py:847`, `:850` (message) | `utils/Env/stack.py`; "a package of utils/Env/stack.toml" | fw | `env/stack.py`, `env/stack.toml` |
| C12 | `config.py:410,661` | `configs_root()` | ok | — |
| C13 | `tools.py:36` | `ENV = parents[1]` (`utils/Env`) | fw | `fw_root() / "tools"` |
| C14 | `tools.py:105,268` | paths shown relative to `repo_root()` | fw | relative to `fw_root()` |
| C15 | `tools.py:215,264,671,928,994,1030,1046,1099,1324` | contexts with `"repo"` | both | contexts with `"fw"` and `"work"`; `"repo"` gone |
| C16 | `tools.py:270`, `:674` (hints) | "make utils/App_*.exe", "see utils/Env/<f>/tool.toml" | fw | "`hep build --framework`", `tools/<f>/tool.toml` |
| C17 | `tools.py:326`; `cli.py:678` | `utils/Env/stack.py` | fw | `env/stack.py` |
| C18 | `tools.py:422,983,1318`; `cli.py:162,607,774,786`; `results.py:58`; `house.py:32,48,195,196,210,216`; `plot.py:630,1240,1241` | `output/results/configs_root()` | ok | — |
| C19 | `tools.py:1164` (message) | "or $HEKIT_OUTPUT" | work | `$HEP_OUTPUT` |
| C20 | `execute.py:294` | `[prelim]` context `"repo"` | both | `"fw"`, `"work"` |
| C21 | `record.py:234-241,266` | `git_state()` at `repo_root()` | both | two states, `hep`, `work` (§5.6) |
| C22 | `hepfiles.py:73` | `build_root()/Rivet` | work | `work_build()/Rivet` |
| C23 | `plot.py:127` | `utils/Env/<name>/backend.py` | fw | `tools/<name>/backend.py` |
| C24 | `plot.py:168`; `docs.py:81` | `utils/Apps/Paint/base.toml` | fw | `apps/Paint/base.toml` |
| C25 | `plot.py:189` (hint) | "utils/Apps/Paint/base.toml has: …" | fw | `apps/Paint/base.toml` |
| C26 | `plot.py:292,328` | `build_root()/App_yd2rt.exe` | fw | `fw_build()` |
| C27 | `plot.py:1083,1236` | `build_root()/Paint.exe` | fw | `fw_build()` |
| C28 | `plot.py:397,486,1117` | `utils/Env/figures/{derive,sheet}.py` | fw | `tools/figures/` |
| C29 | `docs.py:159,165,174` | `repo_root()/docs` | fw | `fw_root()/docs` |
| C30 | `cli.py:778` | `parents[1]/"run"` | fw | `fw_root()/bin/run` |
| C31 | `cli.py` (new) | — | — | `setup` (`--project`, `--git`, `--adopt`), `where`; `build`/`make --framework` live in `bin/hep` |
| C32 | `migrate.py` (new rule) | — | work | `{repo}` → `{work}` in run TOMLs (§5.3) |
| C33 | `results.py:3` (docstring) | `sys.path.insert(0, "<repo>/utils/Env")` | fw | `from runner import results` through the `.pth` (§5.5) |

### 6.2 Plugins, data and scripts

| # | Site | Today | Kind | Becomes |
|---|---|---|---|---|
| C34 | `pythia/tool.toml:4,44`; `yd2rt/tool.toml:5`; `plotmerge/tool.toml:12` | `{repo}/build/App_*.exe` | fw | `{fw}/build/…` |
| C35 | `herwig/tool.toml:33,48` | `{repo}/build/Herwig/HerwigDefaults.rpo` | fw | `{fw}/build/Herwig/…` |
| C36 | `rivet/tool.toml:15,26,29,42`; `merge/tool.toml:13` | `{repo}/build/Rivet` | work | `{work}/build/Rivet` |
| C37 | `schema/run.toml:370` (`[prelim.commands]` notes) | "`{repo}`, `{out}`, …" | — | "`{work}`, `{fw}`, `{out}`, …"; then `make docs` |
| C38 | `yoda/backend.py:313-314`; `mpl/backend.py:102-103` | `build_root()/Rivet` | work | `work_build()/Rivet` (they may import `paths`: `PLUGINS_MAY_IMPORT`) |
| C39 | `mpl/backend.py:36`; `yoda/backend.py:43`; `stack.py:21` | their own location | ok | — (siblings move together) |
| C40 | `hep:12-13`, `:48`, `:52-62` | `root` from `HEKIT_ROOT` or `../..`; `nproc`; `make -C $root` | both | the work root from `hep where --work`, the framework root from its own location; `--framework`; a portable core count |
| C41 | `flags.sh` | `here`, `stack.py` beside it; `OUT` default `build/flags.mk` | ok | — (`env/`; make passes `OUT`) |
| C42 | `hep_env.sh:10-17,133-136,177` | `HEKIT_ROOT`, `hep_cd`, `PATH` | fw | §5.8 |
| C43 | `hepkit.py:6` (docstring) | the `sys.path` line from `modules/<P>/` | fw | "import hepkit" (§5.5) |
| C44 | `Makefile` | one file | both | `Makefile` and `make/work.mk` (§5.4); `Makefile:120`'s `sed -i` made portable (I15) |

### 6.3 Stack recipes (`docs/stack/` → `stack/`)

| # | Site | Today | Becomes |
|---|---|---|---|
| C45 | `build_stack.py:52-55` | the `setup.sh` text: `HEKIT_ROOT`, `utils/Env/hep_env.sh` | §5.8 |
| C46 | `build_stack.py:177`; `settings.toml` `hekit_root` | `{repo}`, `{hekit_root}` | `{repo}` is the HEimdall checkout (as today: `REPO` is the recipe's own repo); `hekit_root` removed |
| C47 | `build_stack.py:443` | keeps an existing `setup.sh` | unchanged |
| C48 | `packages.toml` `[fastjet] patch` | `utils/Env/patches/…` | `stack/patches/…` |
| C49 | `Dockerfile` (`COPY docs/stack/`, `utils/Env/patches/`, `HEKIT_ROOT=/work`); `Dockerfile.dockerignore` | the repo's layout | `stack/container/`; the image holds `/opt/hep/HEimdall` and mounts a work dir |
| C50 | `mac/launch.sh`, `mac/README.md`, `README.md` | `utils/Env/hep_env.sh`, the checkout | `$HEP_FW` |
| C51 | `packages.toml [python]` | the venv and `python_packages` | one more `pre` command writes `heimdall.pth` (§5.5); `python_packages` unchanged |

### 6.4 Tests

| # | Site | Becomes |
|---|---|---|
| C52 | `conftest.py:23-33` | `FW = parents[1]`; `sys.path` gets `FW`; the scratch work (§5.7); `HEP_*`; the guard without `THEIRS` |
| C53 | `pytest.ini` | unchanged |
| C54 | `test_paths.py` (whole) | rewritten for §5.2–5.3: `fw_root`, the walk-up search, `HEP_WORK`, the `tests/` skip, the `HEKIT_*` refusal, `{repo}` refused |
| C55 | `test_hepkit.py:14-20` | `FW/kit` |
| C56 | `test_stack.py:14-35` | `FW/env`; `fw_build()/flags.mk` |
| C57 | `test_plan.py:242`; `test_yd2rt.py:11`; `test_post.py:197`; `test_paint.py:21-22,262,272`; `test_plot_stage.py:23`; `test_gates_p1.py:21`; `test_process_generators_p4.py:52` | the apps and `base.toml` under `fw_build()` and `apps/` |
| C58 | `test_modules_p4.py:19`; `test_plot.py:91`; `test_plot_stage.py:88` | module programs and plugins under the scratch work's `build/` |
| C59 | `test_gates_run_sweep.py:124` (`cwd=REPO`) | `cwd` = the scratch work |
| C60 | `test_layers.py:268` (message) | `env/stack.toml` |
| C61 | `test_docs.py` | `DOCS = FW/docs`; `CODE` scans `runner/ tools/ kit/ apps/ env/ bin/ tests/ make/`, not `modules/` (none in the repo; the fixture modules are under `tests/`) |
| C62 | `test_stack_build.py` | `stack/` paths; the setup text without `hekit_root` |
| C63 | `test_imports.py` | `runner/` under `FW`; the "core never names a tool" check reads `tools/` |
| C64 | `tests/support.py`, `tests/runner/helpers.py` | the `hep` path (`FW/bin/hep`); the environment helpers set `HEP_*` |

### 6.5 Work → framework (High-Energy's own files, P5)

| # | Site | Becomes |
|---|---|---|
| C65 | `configs/PhotoProduction/eic.toml:170` | `{work}/modules/PhotoProduction/delphes_jets.py` (by `hep migrate`) |
| C66 | `modules/PhotoProduction/delphes_jets.py:16` | the `sys.path` line removed |
| C67 | `modules/PhotoProduction/Inproc/Analysis.hh:68`; `configs/PhotoProduction/InProc{EIC,Zeus}.toml:23` (comments) | `$HEP_FW/stack/patches/…` |
| C68 | comments citing old manual sections (current_plan: `Comparison/generators.toml`, `Lambda/lambda.toml`, `PhotoProduction/eic.toml`, `xx/madgraph.toml`) | left to the user, as now |

### 6.6 The manual (`docs/`, P4)

| # | Where | Becomes |
|---|---|---|
| C69 | 01 (layout), 02 §1 and §12, 05 §2, 06 §1, §2, §14, §15, §16, §25 | rewritten for the three places; `utils/Env/<x>` → `tools/<x>`, `utils/X.hh` → `kit/X.hh`, and so on |
| C70 | 07 (the record) | new V-rows for this split (V102 onward); D-rows here are cited from them |
| C71 | `docs/README.md` | the reading paths, plus `stack/` and `docs/framework/` |

---

## 7. The move map

Every path `git ls-files` lists at `split/base` goes to exactly one place. The block below is data:
P1's script reads it from this page, applies it, and fails on any path matched by no rule.

**Reading a rule:**
- **`side`:** `"fw"` copies the path into HEimdall at `to`; `"work"` leaves it in High-Energy only.
- **First match wins.**
- **`to`:** a `to` ending in `/` receives the path minus the rule's literal prefix (everything
  before the first wildcard, up to its last `/`). Any other `to` is a file name.

```toml
# 01_Target.md §7 — High-Energy (split/base) → HEimdall. Read by P1 (04_Seed.md).
rules = [
  # the runner and its data
  ["utils/Env/runner/**",       "fw",   "runner/"],
  ["utils/Env/hep",             "fw",   "bin/hep"],
  ["utils/Env/run",             "fw",   "bin/run"],
  ["utils/Env/hep_env.sh",      "fw",   "env/hep_env.sh"],
  ["utils/Env/flags.sh",        "fw",   "env/flags.sh"],
  ["utils/Env/stack.toml",      "fw",   "env/stack.toml"],
  ["utils/Env/stack.py",        "fw",   "env/stack.py"],
  ["utils/Env/schema/**",       "fw",   "schema/"],
  ["utils/Env/quantities.toml", "fw",   "schema/quantities.toml"],
  ["utils/Env/latex.toml",      "fw",   "schema/latex.toml"],
  ["utils/Env/patches/**",      "fw",   "stack/patches/"],
  ["utils/Env/*/**",            "fw",   "tools/"],            # the 16 plugin folders
  # the kits and apps
  ["utils/*.hh",                "fw",   "kit/"],
  ["utils/hepkit.py",           "fw",   "kit/hepkit.py"],
  ["utils/App_*.cc",            "fw",   "apps/"],
  ["utils/Apps/**",             "fw",   "apps/"],             # Paint/
  ["Makefile",                  "fw",   "Makefile"],          # split in P3; High-Energy gets the template's
  ["pytest.ini",                "fw",   "pytest.ini"],
  # the stack, the manual, the agents' files
  ["docs/stack/Dockerfile*",    "fw",   "stack/container/"],
  ["docs/stack/**",             "fw",   "stack/"],
  ["docs/Untitled-1.md",        "work", ""],
  ["docs/**",                   "fw",   "docs/"],             # 01–07, README, audit_2/, framework/
  ["bots/BOT.md",               "fw",   "CLAUDE.md"],         # rewritten in P1 for HEimdall
  ["bots/**",                   "fw",   "bots/"],
  # the tests
  ["tests/fixtures/configs/**", "fw",   "tests/fixtures/work/configs/"],
  ["tests/fixtures/README.md",  "fw",   "tests/fixtures/work/README.md"],
  ["tests/**",                  "fw",   "tests/"],
  # the work: stays in High-Energy
  ["configs/**",                "work", ""],
  ["modules/**",                "work", ""],                  # and frozen copies → tests/fixtures/work/modules/ (P1)
  ["aux/**",                    "work", ""],
  ["_text/**",                  "work", ""],
  ["_vs/**",                    "work", ""],
  ["archive/**",                "work", ""],
  [".vscode/**",                "work", ""],
  ["generator_comparison.*",    "work", ""],
  [".gitignore",                "work", ""],                  # merged with the template's in P5
]
```

**Counts at `31817f8`:** 1554 tracked paths (P1 recounts at `split/base`).

| Group | Paths | Side |
|---|---|---|
| `utils/` | 80 (`Env/` 66, kits 5, apps 9) | fw |
| `tests/` | 83 | fw |
| `docs/` except `Untitled-1.md` | 22 (pages 8, `audit_2` 1, `framework` 1 at 31817f8, `stack` 12) | fw |
| `bots/` | 4 | fw |
| `Makefile`, `pytest.ini` | 2 | fw |
| **fw total** | **191** | |
| `configs/` | 25 | work |
| `modules/` | 18 | work (and copied into the fixture) |
| `aux/` | 1311 | work |
| `_text/`, `_vs/`, `archive/`, `.vscode/`, `generator_comparison.*`, `docs/Untitled-1.md`, `.gitignore` | 9 | work |
| **work total** | **1363** | |

**Made new in HEimdall** (P1 and P3), not moved:
- `README.md`, `.gitignore`, `make/work.mk`;
- `templates/work/*`;
- `stack/container/heimdall.def`;
- `tests/fixtures/work/{hep.toml, modules/**, datasets/zeus_eic.yoda}`.

**Removed from High-Energy's `work` branch** in P5: every `side = "fw"` path. `docs/` then keeps
only `Untitled-1.md`, and `bots/`, `tests/` and `utils/` are gone.

---

## 8. Before the reinstall (the user's checklist)

The fresh system is this lab PC, wiped (D16). Git holds the code. These are what it does not hold,
to copy to a disk that survives the wipe:

| What | Why | How |
|---|---|---|
| High-Energy, every branch and tag | the source of everything | `git push origin rework` (and the tags), or `git bundle create HE.bundle --all` |
| `datasets/` (`zeus_eic.yoda`, 20 kB) | not in git; the work dir and the fixture use it | copy |
| `literature/`, `cross_machine/`, `reports/` | the user's, not in git | copy |
| `$HEP/src/*.tar*`, `*.tgz` (optional) | saves the downloads: `build_stack.py` uses a tarball already in `$prefix/src` | copy |
| `results/` (optional) | only to look at again; the comparisons in `09` use numbers recorded in these files | copy if wanted |
| `~/.claude/projects/…High-Energy/memory/` (optional) | the agents' notes about this repo | copy |
| the Mac paths in `.vscode/` | nothing to do | they stay in High-Energy (D13) |

**Before the copy:**
- Round 2b records the lab PC's baselines into these files: the stack's versions, pass counts,
  `FOUND`, the PDF sets, one reference point's numbers.
- These files are committed and pushed with `rework`, because the baselines must survive the wipe.

On the new install, P0 brings the copies back into `$HEP/.setup/kept/`, and P1 and P5 take them from
there.

---

## 9. Decisions added here

These continue README §2's table.

| # | Decision |
|---|---|
| D17 | HEimdall's layout is §3's: `bin/ env/ runner/ tools/ schema/ kit/ apps/ make/ stack/ templates/ docs/ bots/ tests/ build/`. `tools/` holds every plugin folder, so the folder contract is unchanged. |
| D18 | `fw_root()` is where the running code is. A `$HEP_FW` that disagrees with it is refused. `work_root()` is `$HEP_WORK`, or the first `hep.toml` with `[work]` walking up from the working directory. Markers under `fw_root()/tests/` are skipped. |
| D19 | `{repo}` is retired: `{fw}` and `{work}`. A run TOML's `{repo}` is refused, and `hep migrate` rewrites it to `{work}`. Set `HEKIT_*` variables are refused, naming their replacements. |
| D20 | Commands are scoped (§5.2): work, framework-only, or anywhere. `hep where` is new. `hep build` and `hep make` act on the work dir, and `--framework` acts on HEimdall. |
| D21 | Every build tree has its own `flags.mk` from the one probe (D5, amended). |
| D22 | Python reaches the framework through the venv's `heimdall.pth` (`$HEP_FW`, `$HEP_FW/kit`). No module or notebook writes `sys.path` lines. |
| D23 | The tests run in a persistent scratch copy of the fixture work dir, `build/scratch/work`. The fixture carries frozen copies of the modules the tests build. |
| D24 | The move map is data (§7). P1 applies it, and fails on a path no rule matches. |
| D25 | `hep.toml` is `[work] name` and `[framework] expects`, nothing else. `expects` is warned about when it is not an ancestor of HEimdall's `HEAD`, never enforced. |

---

## 10. Risks 2b must plan around

| Risk | Where it bites | Plan |
|---|---|---|
| The reinstall is Ubuntu 26.04: some `apt_packages` names may be gone or renamed (`libpcre3-dev` is a likely one: Debian has been removing PCRE 1), and Python and GCC are newer | P2 | P0 checks every package with `apt-cache policy`. The ubuntu annex lists allowed renames as *allowed adjustments* (02 §7). A compiler or Python incompatibility in ROOT, Herwig or Whizard is a gate, not a quiet fix |
| A move breaks a relative assumption the grep did not see | P3 | the fast suite after every task group; C1–C71 are each a task |
| The fixture's frozen modules drift from High-Energy's | P4, later | they are test data (V52's rule): changed only with a test |
| Identities: everything reruns on the new install | P5, P6 | expected; the comparisons in `09` are by numbers within tolerances, not by identity |
| `aux/` (1311 files) makes High-Energy heavy | none for the plans | stays (D13); moving it is the user's choice, later |
