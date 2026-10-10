# 01 — The target

What exists when the plans are done, and the contract between its parts. This page details
[README](README.md) §2's decisions without reopening them. Rows added here continue the numbering
(§9).

The phase files (`03`–`09`) say *how* to get here. This page says *what* "here" is, and it gives
three things those phases build on:
- the classification of every coupling in the code (§6);
- the move map (§7);
- the list of what the user keeps before the reinstall (§8).

**History:**
- 2026-10-08: written against `rework` at `33b0ed9` (round 2a).
- 2026-10-10: updated against `9cb907a` for the decks, V102–V104 (round 2b).
- 2026-10-10: **round 2c**, the user's layout:
  - Heimdall at `~/Github/Heimdall`, which is itself `$HEP`;
  - `stack/ forge/ stash/`, `env/venv/` and `framework/Apps/` ignored;
  - `env/` for the Python and HEP environment;
  - `framework/` and `src/`;
  - Top-Quark as the test work dir;
  - High-Energy left alone (D26–D33).

Every file:line below was checked by grep at `9cb907a` or later. Phase P1 pins its own revision,
tagged `split/base`, and re-checks the rows against it.

---

## 1. Two places, and a source

| Place | Is | Made by | In git |
|---|---|---|---|
| **Heimdall**, `~/Github/Heimdall` (`$HEP`) | the framework **and** the machine's home: the stack's recipes and its installs, the environment, the runner, the tool folders, the kits and apps, the manual, the tests, the agents' state | P1 (the moves), P2 (the stack), P3 (the seam) | its own repo, fresh history (D2). `stack/ forge/ stash/ env/venv/ framework/Apps/ .setup/` are ignored |
| **a work dir**, e.g. `~/Github/Top-Quark` (`$HEP_WORK`, or found from the working directory) | one workspace: configs, modules, datasets, and what runs make of them | `hep setup <dir>` (D14) | its own repo, optional |
| *High-Energy*, `~/Github/High-Energy` | the source P1 seeds Heimdall from, and the origin of the tests' fixture. **Left alone** (D31) | the user's clone | as it is |

There is one Heimdall per machine, and any number of work dirs, which share nothing but Heimdall
(D4). The first work dir is **Top-Quark**, made fresh by `hep setup` as a test (D32).

---

## 2. Heimdall

```
~/Github/Heimdall/                  = $HEP
  README.md  CLAUDE.md  .gitignore  Makefile  pytest.ini
  setup.sh                          load_hep: tracked, finds its own folder (§5.8)
  build_stack.py                    builds the stack into this folder (stack/ forge/ stash/)
  packages.toml  settings.toml      what is built, and how
  pth.py                            writes the venv's heimdall.pth (P2, §5.5)
  patches/                          patches the stack's sources need (FastJet's SISCone, L29)
  platforms/mac/                    Brewfile, mac.toml, build.sh, launch.sh, README.md
  platforms/container/              Dockerfile, Dockerfile.dockerignore, heimdall.def
  env/                              the HEP environment: hep_env.sh, flags.sh, stack.toml, stack.py
    venv/          (ignored)        the Python environment (was ~/HEP/.venv), with heimdall.pth
  framework/
    bin/                            hep, run
    runner/                         the Python package, its 25 modules
    tools/<folder>/                 the 16 plugin folders: the tools custom delphes herwig madgraph merge module
                                    plotmerge pythia rivet sherpa whizard yd2rt; the provider lhapdf; the
                                    backends yoda, mpl; figures
    schema/                         run.toml, run.schema.json, deck.toml, quantities.toml, latex.toml
    templates/work/                 what `hep setup` lays down (§4.1), and starter/
    work.mk                         the module and Rivet rules a work dir's Makefile includes (§5.4)
    hepkit.py                       the kit for a custom tool in Python
    Apps/          (ignored)        App_Pythia.exe App_PythiaCheck.exe App_yd2rt.exe Paint.exe Herwig/HerwigDefaults.rpo
  src/                              Status.hh Kit.hh Module.hh PythiaRun.hh App_Pythia.cc App_PythiaCheck.cc
                                    App_yd2rt.cc Apps/Paint/ (main.cc, *.hh, base.toml)
  docs/                             the manual 01–07, README.md, stack/ (README.md, build_by_hand.txt),
                                    reporter/, audit_2/, framework/ (these plans)
  bots/                             current_plan.md intent.md archive.md
  tests/                            conftest.py support.py runner/ integration/ cxx/ reference/
                                    fixtures/work/{hep.toml,README.md,configs/,modules/,datasets/}
  stack/           (ignored)        <pkg>/ the installs (LHAPDF hepmc3 fastjet root yoda rivet pythia8 herwig7
                                    delphes sherpa madgraph whizard onnxruntime geant4), .stamps/,
                                    setup_extra.sh (this machine's extra lines, §5.8)
  forge/           (ignored)        <pkg>/ the stack's build trees; logs/<pkg>.log; make/ (the framework's
                                    deps/, flags.mk, flags.log); tests/ (the C++ test binaries);
                                    scratch/ (the tests' work copy, output, results, reports, pytest)
  stash/           (ignored)        <pkg>-<release>.<ext> archives, and their unpacked sources
  .setup/          (ignored)        the agents' state.toml, log.md, kept/, verify/ (02 §3)
```

**Who writes where:**

| Writer | Writes |
|---|---|
| `build_stack.py` (P2) | `stash/`, `forge/<pkg>/`, `forge/logs/`, `stack/` (installs, `.stamps/`, `setup_extra.sh`), `env/venv/` |
| `hep build --framework` | `framework/Apps/` (the apps, Herwig's repository) and `forge/make/`, `forge/tests/` |
| the tests | `forge/scratch/` only |
| the agents | `.setup/` |
| a work dir's build | its own `build/`; never anything in Heimdall (D30) |

---

## 3. Why this shape

- **The root is how Heimdall gets onto a machine:**
  ```bash
  git clone <Heimdall> ~/Github/Heimdall && cd ~/Github/Heimdall && python3 build_stack.py
  ```
  This builds the stack into the clone itself, and `source setup.sh` loads it. The recipes sit at
  the root because they are the first thing run.
- **`env/`** is the HEP environment (the user, 2026-10-10):
  - what the shell and make need before Python (`hep_env.sh`, `flags.sh`, and the stack registry
    `stack.toml`/`stack.py` that both read);
  - the Python environment itself, `env/venv/` (ignored).

  `setup.sh` sources `env/hep_env.sh`, which activates `env/venv`.
- **`framework/`** is what runs:
  - the commands (`bin/`);
  - the Python (`runner/`, `hepkit.py`);
  - the folders the runner loads by path (`tools/`, `schema/`);
  - the compiled apps, once built (`Apps/`).

  `tools/` keeps the folder contract (06 §16) unchanged. `runner/tools.py:36`'s `ENV` becomes
  `hep_root() / "framework" / "tools"`, and the yoda and rivet folders never sit on `sys.path` next
  to the real `yoda` and `rivet` packages.
- **`src/`** is what is compiled: today's `utils/` without `Env/` and `hepkit.py` (D29).
  - The Makefile's conventions carry over: `src/App_<X>.cc` and `src/Apps/<X>/main.cc`.
  - A work dir's modules include the kits with `-I $HEP/src`.
- **Ignored, and where each kind of file goes** (D27):
  - `stash/` holds what was downloaded and unpacked;
  - `forge/` holds what is being built: trees, intermediates, test binaries, scratch;
  - `stack/` holds what is installed, and `env/venv/` the Python packages;
  - `framework/Apps/` holds the framework's own programs, ready to run.

  `forge/` and `stash/` may be emptied at any time; `stack/`, `env/venv/` and `framework/Apps/` are
  what runs.
- **A repo that holds its own stack** (D33): `git clean -x` in Heimdall would delete `stack/`
  (hours of building). It is never run there, and `CLAUDE.md` says so. Editors exclude `stack/
  forge/ stash/` from watching and search (`.vscode/settings.json`, `files.watcherExclude`).

---

## 4. A work dir

### 4.1 What `hep setup <dir>` lays down

```
<dir>/
  hep.toml           the marker
  Makefile           include $(HEP)/framework/work.mk
  .gitignore         build/ output/ results/ datasets/* reports/* __pycache__/ *.exe
  README.md          what each folder is for; that datasets/ and reports/ are not in git
  CLAUDE.md          the work dir's agent rules: configs/ and modules/ are the user's; read the manual
                     at $HEP/docs; never write into results/ from a test; stage by path
  .vscode/settings.json   files.watcherExclude for build/ output/ results/ (D33)
  configs/  modules/  datasets/  results/  output/  reports/  build/
```

With `--project <P>`, it also writes:
- `configs/<P>/<p>.toml`, a commented starter run TOML: one App_Pythia → Rivet (`MC_JETS`) → yd2rt
  chain, 2 PDFs, 500 events, with a `[plot]`, which `hep check <P>/<p>` accepts (06 S2);
- `configs/<P>/<p>.cmnd`, its base card;
- an empty `modules/<P>/`.

Git does not keep empty folders. On a fresh clone of a work dir, `hep setup <dir>` (idempotent)
makes the missing ones again, so no `.gitkeep` files are needed.

### 4.2 `hep.toml`

```toml
# hep.toml — this folder is a Heimdall work dir (made by `hep setup`, 2026-…).
[work]
name = "Top-Quark"

[framework]
expects = "<Heimdall's revision when this file was made>"
```

**What `hep.toml` means:**
- **`[work]`** marks the work dir. A `hep.toml` without it is not a marker.
- **`name`** is the folder's name unless `--name` gives one. It is used in provenance and in `hep
  where`.
- **`[framework] expects`** is checked the way `[config.meta]` is (V97): warned about, never
  enforced. The runner warns once per command when `expects` is not an ancestor of Heimdall's
  `HEAD`, meaning the work dir was made with a newer Heimdall than the one running. A dirty or
  missing revision is not warned about.
- Unknown keys are refused, as in every TOML the runner reads.

### 4.3 Top-Quark, the test work dir (D32)

```bash
hep setup ~/Github/Top-Quark --project Starter --git
```

This makes `~/Github/Top-Quark` with §4.1's files and folders, plus
`configs/Starter/starter.{toml,cmnd}` (the generic starter) and an empty `modules/Starter/`, and
commits once. P5 builds it, checks it and runs it (08 S1). It is a test: the user decides later
what Top-Quark becomes.

### 4.4 Parked: High-Energy as a work dir (D31)

Not done now. High-Energy is the source of P0–P1 and of the fixture only, and stays as it is. If
the user later asks for it, the steps are 08's appendix:
- on a branch `work`, remove the paths §7 sends to Heimdall;
- `hep setup --adopt`;
- `{repo}` → `{work}` by `hep migrate`;
- C65–C67 and C77, shown first.

---

## 5. The seam

### 5.1 Variables

| Variable | Set by | Means |
|---|---|---|
| `HEP` | `setup.sh` (its own folder) | Heimdall: the framework and the machine's home. Replaces `HEKIT_ROOT`; `HEP_FW` is not used (D28) |
| `HEP_INSTALL` | `setup.sh` | `$HEP/stack` |
| `HEP_WORK` | the user, the tests | the work dir, instead of the search (§5.2) |
| `HEP_CONFIGS`, `HEP_OUTPUT`, `HEP_RESULTS`, `HEP_REPORTS` | the user, the tests | replace the work dir's `configs/`, `output/`, `results/`, `reports/` (V52's roles and V103's, renamed) |
| `HEP_SETUP`, `HEP_ENV_LOADED` | `hep_env.sh` | as today |
| `HEP_STATUS_FD` | the runner, per tool | as today |
| `LHAPDF_DATA_PATH`, `GEANT4_DATA_DIR`, `ONNXRUNTIME_DIR` | `hep_env.sh` | as today, under `$HEP/stack` |
| `RIVET_ANALYSIS_PATH` | the rivet and merge folders, per run | `{work}/build/Rivet` |

**Retired:** `HEKIT_ROOT`, `HEKIT_CONFIGS`, `HEKIT_OUTPUT`, `HEKIT_RESULTS` and `HEKIT_REPORTS`
(K15). If one of them is set, every command refuses and names its replacement. A stale shell or
script fails loudly, not silently (01 §4.5 of the manual).

### 5.2 The two roots

`runner/paths.py` replaces `repo_root()` with two functions.

**`hep_root()`** is the Heimdall the code is running from: `Path(__file__).resolve().parents[2]`
(`framework/runner/paths.py`).
- It must hold `framework/runner/`, `framework/tools/` and `framework/schema/run.toml`.
- If `$HEP` is set and resolves elsewhere, the command refuses: two Heimdalls in one shell. The
  convenient inference "use the variable" is refused (01 §4.5).

**`work_root()`** is the work dir:
1. If `$HEP_WORK` is set, it is that directory. It must hold a `hep.toml` with `[work]`, or the
   command is refused.
2. Otherwise, walk up from the working directory to `/`. The first directory whose `hep.toml` has
   a `[work]` table wins.
3. A marker under `hep_root()/tests/` is skipped: the fixture work dir is found only through
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
| `reports_root()` | `$HEP_REPORTS` or `work_root()/reports`: decks (V103) |
| `work_build()` | `work_root()/build`: module programs, `Rivet/`, `deps/`, `flags.mk` |
| `datasets_root()` | `work_root()/datasets` |
| `apps_dir()` | `hep_root()/framework/Apps`: the compiled apps and Herwig's repository |
| `forge_dir()` | `hep_root()/forge`: `make/`, `tests/`, `scratch/` |

A root whose variable is set never searches for the work dir. Tests that set all four variables, as
`test_deck*.py` do, therefore run without one.

**Which commands need which root:**

| Commands | Need |
|---|---|
| `run`, `plot`, `overlay`, `deck`, `check`, `ls`, `status <config>`, `clean`, `reproduce`, `migrate`, `build`, `make` | a work dir |
| `explain`, `status --stack`, `build --framework`, `make --framework` | Heimdall only |
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
| `{hep}` | `hep_root()` | `pythia/tool.toml` (`{hep}/framework/Apps/App_Pythia.exe`, `App_PythiaCheck.exe`), `yd2rt`, `plotmerge` (`App_yd2rt.exe`), `herwig` (`{hep}/framework/Apps/Herwig/HerwigDefaults.rpo`) |
| `{work}` | `work_root()` | `rivet` and `merge` (`{work}/build/Rivet`), a run TOML's own arguments and `[prelim.commands]` (`{work}/modules/…`) |

- **A run TOML that still says `{repo}`** is refused with a hint: "`{repo}` is retired: `{work}`
  for your files, `{hep}` for Heimdall's; `hep migrate` rewrites it". In a run TOML, `{repo}` only
  ever meant the user's files, so `hep migrate` rewrites it to `{work}` (a new rule in
  `runner/migrate.py`).
- **A tool folder that says `{repo}`** is a load error (folder checks, 06 §16.1).

### 5.4 The build

**`$HEP/Makefile`** builds the framework's programs:

| Source | Output |
|---|---|
| `src/App_<X>.cc` | `framework/Apps/App_<X>.exe` |
| `src/Apps/<X>/main.cc` | `framework/Apps/<X>.exe` (Paint) |
| `tests/cxx/<X>.cc` | `forge/tests/<X>.exe` |
| (Herwig, when on `PATH`) | `framework/Apps/Herwig/HerwigDefaults.rpo`, as today (L15) |

- The targets are `all`, `tests`, `test`, `test-slow`, `configure`, `list`, `schema`, `docs` and
  `clean`.
- `clean` empties `framework/Apps/` and `forge/make/`, `forge/tests/`. It never touches `stack/`,
  `stash/` or the stack's trees in `forge/<pkg>/`.
- The includes are `-I src`. The flags are `forge/make/flags.mk`, written by `env/flags.sh`,
  and the dependency files are in `forge/make/deps/`.

**`$HEP/framework/work.mk`** is included by a work dir's one-line `Makefile`, and builds into the
work dir's `build/` (D30). It keeps today's rules (06 §15.1) for:
- `modules/<P>/<X>.cc` → `build/<P>/<X>.exe`;
- `modules/<P>/Rivet/<x>.cc` and `modules/<P>/Rivet_<x>.cc` → `build/Rivet/Rivet_<x>.so`, with
  their `.info`, `.plot` and `.yoda`;
- any `<dir>/<X>.cc` named on the command line.

It differs from today's rules in four ways:
- the includes are `-I $(HEP)/src -I modules/<P>`, and `rivet-build` gets the same;
- the flags are `<work>/build/flags.mk`, written by `$(HEP)/env/flags.sh` with the same
  key logic (L22). The probe is shared, the caches are per tree (D21);
- `all` is the modules and plugins only;
- there are no `tests`, `schema` or `docs` targets.

**Commands:**

| Command | Is |
|---|---|
| `hep build` | `make -C <work> all`. It warns when a framework app the work's tools need is missing: "run `hep build --framework`" |
| `hep build --framework` | `make -C $HEP all` |
| `hep make …` | `make -C <work> …` |
| `hep make --framework …` | `make -C $HEP …` |
| core count | `os.cpu_count()` through `hep`, not `nproc` (I15) |

Rebuilding a framework app changes the identity of every point, in every work dir, that ran it
(06 §27): the apps are shared. `hep build --framework` says so when it rebuilds an app.

### 5.5 Python

- **`framework/bin/run`** puts `hep_root()/framework` on `sys.path` and imports `runner.cli`.
  `runner/cli.py:808` (`hep reproduce`) runs `framework/bin/run`.
- **The venv** is `env/venv`. Its `site-packages/heimdall.pth` holds one line, `$HEP/framework`
  (D29).
  - It is written by the stack's `python` step, when the venv is made (P2). `hep where` warns when
    it is missing or names another Heimdall.
  - Any Python in the venv can then `from runner import results` (02 §11 of the manual) and `import
    hepkit`, with no `sys.path` lines.
- **Plugins** (`render.py`, `backend.py`, `provider.py`, the figures) are still loaded by path,
  from `framework/tools/<folder>/` (`runner/plugins.py`).

### 5.6 Provenance and identity

`record.provenance()` (`record.py:266`) writes:

```json
"git":  {"heimdall": {"revision": "…", "dirty": false}, "work": {"revision": "…", "dirty": true}},
"hep":  "/home/…/Github/Heimdall",
"work": {"name": "Top-Quark", "root": "/home/…/Github/Top-Quark"}
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
- `modules/`: frozen copies of High-Energy's `modules/` at `split/base` (18 files at 9cb907a),
  because the tests build Lambda.exe, InprocJets.exe and the photo_eic, Lamriv and
  particle_spectra plugins;
- `datasets/zeus_eic.yoda`: 20 kB, from §8's kept files.

These copies are frozen like `configs/`: a change goes only together with the test that needs it.

**A session (`tests/conftest.py`):**
1. Sync `tests/fixtures/work/` into `forge/scratch/work/`. Only changed files are copied, and the
   copy's `build/` is never touched, so make rebuilds only what changed.
2. Set `HEP_WORK` to that copy, and `HEP_OUTPUT`, `HEP_RESULTS` and `HEP_REPORTS` to
   `forge/scratch/{output,results,reports}`.
3. Use `forge/scratch/pytest` as the basetemp.
4. The integration tests that need module programs or plugins run `make -C forge/scratch/work all`
   once per session (a session fixture).

**The guard** keeps V52's first half: `tests/fixtures/` and `tests/reference/` must come out byte
for byte. Its second half (`THEIRS`, the user's `results/ configs/ modules/`) goes. There are no
user folders in Heimdall, and no test may name a real work dir.

The test files that change are listed in §6.4.

### 5.8 The environment

**`setup.sh`** is tracked at Heimdall's root. It replaces the stub `build_stack.py` wrote
(`build_stack.py:51-57`, `:443`), and finds its own folder, so a clone anywhere works:

```bash
#!/bin/bash
# setup.sh — Heimdall's environment: source it once per session (alias load_hep). Tracked; finds its own folder.
export HEP=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
export HEP_INSTALL=$HEP/stack
[ -f "$HEP/stack/setup_extra.sh" ] && source "$HEP/stack/setup_extra.sh"     # this machine's lines (macOS: DYLD, GNU tools)
source "$HEP/env/hep_env.sh"
```

`settings.toml`'s `setup_extra` lines go to `stack/setup_extra.sh`, which `build_stack.py` writes:
they are per machine, so they are not in git.

**`env/hep_env.sh`** changes in five places:

| Lines | Becomes |
|---|---|
| `:10-17` | `HEP` defaults to its own folder's parent; `HEP_INSTALL` to `$HEP/stack`; `HEKIT_ROOT` gone (if set: "retired: HEP" and unset) |
| `:129-131`, `:145-147` (`hep_src`, `hep_build`, `hep_install`) | `hep_stash`, `hep_forge`, `hep_stack` (cd to `$HEP/stash`, `forge`, `stack`) |
| `:133-136` (`hep_cd PROJECT [dir]`) | cds into `$(hep where --work)/<dir>/<P>`, and refuses outside a work dir |
| `:160`, `:162` | the venv at `$HEP/env/venv` |
| `:177` | `$HEP/framework/bin` on `PATH` instead of `utils/Env` |

The rest is unchanged: `quit`, `hep_refresh` and `hep_status`.

**`hep where`** prints two lines, `hep=<Heimdall root> <revision>` and `work=<root or ->`. With
`--hep` or `--work`, it prints one path, for scripts and agents. Its exit code is 2 when the root
asked for does not exist.

---

## 6. Every coupling, classified

This extends README §6. Each row names one call site at `9cb907a` and what it becomes. P3's tasks
cite these rows by number (C1…). The paths in "Becomes" are under `$HEP` unless they say
otherwise.

**Kind:**
- *hep*: a Heimdall file, found from `hep_root()`;
- *work*: under `work_root()`;
- *both*: the site needs both roots;
- *ok*: already derives from a root that §5.2 re-points, so it is unchanged.

### 6.1 The runner (`utils/Env/runner/` → `framework/runner/`)

| # | Site | Today | Kind | Becomes |
|---|---|---|---|---|
| C1 | `paths.py:23-48` | `MARKERS`, `HEKIT_ROOT`, `repo_root()` by markers | — | `hep_root()`, `work_root()` (§5.2); the `HEKIT_*` guard |
| C2 | `paths.py:51-76` | `results/output/reports/configs_root`, `build_root` | work | `HEP_*` variables; `work_build()`, `apps_dir()`, `forge_dir()` |
| C3 | `paths.py:85-92` | `ROOTS` | work | the table in §5.3 |
| C4 | `paths.py:111` | `./` → `repo_root()` | work | `work_root()` |
| C5 | `labels.py:22` | `utils/Env/latex.toml` | hep | `framework/schema/latex.toml` |
| C6 | `schema.py:35-36` | `utils/Env/schema/<name>.toml` (run, deck) | hep | `framework/schema/<name>.toml` |
| C7 | `quantities.py:31` | `utils/Env/quantities.toml` | hep | `framework/schema/quantities.toml` |
| C8 | `quantities.py:73` | glob `utils/Env/*/quantities.toml` | hep | `framework/tools/*/quantities.toml` |
| C9 | `quantities.py:272` | `utils/Env/<name>/provider.py` | hep | `framework/tools/<name>/provider.py` |
| C10 | `quantities.py:78` (hint) | "add it to utils/Env/quantities.toml" | hep | names `framework/schema/quantities.toml` |
| C11 | `config.py:847`, `:850` (message) | `utils/Env/stack.py`; "a package of utils/Env/stack.toml" | hep | `env/stack.py`, `env/stack.toml` |
| C12 | `config.py:410,661` | `configs_root()` | ok | — |
| C13 | `tools.py:36` | `ENV = parents[1]` (`utils/Env`) | hep | `hep_root() / "framework" / "tools"` |
| C14 | `tools.py:105,268` | paths shown relative to `repo_root()` | hep | relative to `hep_root()` |
| C15 | `tools.py:215,264,671,928,994,1030,1046,1099,1324` | contexts with `"repo"` | both | contexts with `"hep"` and `"work"`; `"repo"` gone |
| C16 | `tools.py:270`, `:674` (hints) | "make utils/App_*.exe", "see utils/Env/<f>/tool.toml" | hep | "`hep build --framework`", `framework/tools/<f>/tool.toml` |
| C17 | `tools.py:326`; `cli.py:708` | `utils/Env/stack.py` | hep | `env/stack.py` |
| C18 | `tools.py:422,983,1318`; `cli.py:169,637,804,816`; `results.py:58`; `house.py:32,48,195,196,210,216`; `plot.py:630,1241,1242`; `deck.py:101,193,232,236` | `output/results/configs/reports_root()` | ok | — |
| C19 | `tools.py:1164` (message); `cli.py:811` (`hep reproduce`'s environment) | `HEKIT_OUTPUT`, `HEKIT_RESULTS` | work | `HEP_OUTPUT`, `HEP_RESULTS` |
| C20 | `execute.py:294` | `[prelim]` context `"repo"` | both | `"hep"`, `"work"` |
| C21 | `record.py:234-241,266` | `git_state()` at `repo_root()` | both | two states, `hep`, `work` (§5.6) |
| C22 | `hepfiles.py:73` | `build_root()/Rivet` | work | `work_build()/Rivet` |
| C23 | `plot.py:127` | `utils/Env/<name>/backend.py` | hep | `framework/tools/<name>/backend.py` |
| C24 | `plot.py:168`; `docs.py:81`; `cli.py:72` (`--style` help) | `utils/Apps/Paint/base.toml` | hep | `src/Apps/Paint/base.toml` |
| C25 | `plot.py:189` (hint) | "utils/Apps/Paint/base.toml has: …" | hep | `src/Apps/Paint/base.toml` |
| C26 | `plot.py:292,328` | `build_root()/App_yd2rt.exe` | hep | `apps_dir()` |
| C27 | `plot.py:1083,1237` | `build_root()/Paint.exe` | hep | `apps_dir()` |
| C28 | `plot.py:397,486,1118`; `deck.py:442` | `utils/Env/figures/{derive,layout}.py` | hep | `framework/tools/figures/` |
| C29 | `docs.py:159,165,174` | `repo_root()/docs` | hep | `hep_root()/docs` |
| C30 | `cli.py:808` | `parents[1]/"run"` | hep | `hep_root()/framework/bin/run` |
| C31 | `cli.py` (new) | — | — | `setup` (`--project`, `--git`, `--adopt`, `--name`), `where`; `build`/`make --framework` live in `framework/bin/hep` |
| C32 | `migrate.py` (new rule) | — | work | `{repo}` → `{work}` in run TOMLs (§5.3) |
| C78 | `cli.py:807` (`hep reproduce` on a `seed_type = "random"` configuration) | `--set run.<cfg>.seed_type`, the form before V98, which `apply_sets` turns into a `[run.<cfg>]` table that V98's `[run]` refuses (found 2026-10-10, not run) | — | `run.cfgs.<cfg>.seed_type` and `run.cfgs.<cfg>.manual_seed`, with a test that reproduces a random-seed point. Only if it is still so at `split/base` |
| C33 | `results.py:3` (docstring) | `sys.path.insert(0, "<repo>/utils/Env")` | hep | `from runner import results` through the `.pth` (§5.5) |
| C72 | `deck.py:101` | a deck by name under `reports_root()`; `./`, `../`, `/` taken from the working directory | work | unchanged: a deck path is the user's own file argument, like `hep overlay`'s, not a run TOML path (V13 is about run TOMLs) |
| C73 | `runner/viewer.py` | serves a deck's folder | ok | — (no root of its own) |

### 6.2 Plugins, data and scripts (`utils/Env/` → `framework/`)

| # | Site | Today | Kind | Becomes |
|---|---|---|---|---|
| C34 | `pythia/tool.toml:4,44`; `yd2rt/tool.toml:5`; `plotmerge/tool.toml:12` | `{repo}/build/App_*.exe` | hep | `{hep}/framework/Apps/App_*.exe` |
| C35 | `herwig/tool.toml:33,48` | `{repo}/build/Herwig/HerwigDefaults.rpo` | hep | `{hep}/framework/Apps/Herwig/HerwigDefaults.rpo` |
| C36 | `rivet/tool.toml:15,26,29,42`; `merge/tool.toml:13` | `{repo}/build/Rivet` | work | `{work}/build/Rivet` |
| C37 | `schema/run.toml:370` (`[prelim.commands]` notes) | "`{repo}`, `{out}`, …" | — | "`{work}`, `{hep}`, `{out}`, …"; then `make docs` |
| C38 | `yoda/backend.py:313-314`; `mpl/backend.py:102-103` | `build_root()/Rivet` | work | `work_build()/Rivet` (they may import `paths`: `PLUGINS_MAY_IMPORT`) |
| C39 | `mpl/backend.py:36`; `yoda/backend.py:43`; `stack.py:21` | their own location | ok | — (siblings move together) |
| C40 | `hep:12-13`, `:48`, `:52-62` | `root` from `HEKIT_ROOT` or `../..`; `nproc`; `make -C $root` | both | Heimdall from its own location (`framework/bin/` → `../..`); the work root from `run where --work`; `--framework`; a portable core count |
| C41 | `flags.sh` | `here`, `stack.py` beside it; `OUT` default `build/flags.mk` | ok | — (`env/`; make passes `OUT`: `forge/make/flags.mk` or the work's `build/flags.mk`) |
| C42 | `hep_env.sh:10-17,133-136,177` | `HEKIT_ROOT`, `hep_cd`, `PATH` | hep | §5.8 |
| C80 | `hep_env.sh:11,129-131,145-147,160,162` | `HEP_INSTALL=$HEP/install`; `hep_src`/`hep_build`/`hep_install`; the venv at `$HEP/.venv` | hep | `$HEP/stack`; `hep_stash`/`hep_forge`/`hep_stack`; `$HEP/env/venv` (§5.8) |
| C43 | `hepkit.py:6` (docstring) | the `sys.path` line from `modules/<P>/` | hep | "import hepkit" (§5.5) |
| C44 | `Makefile` | one file | both | `Makefile` (`src/` → `framework/Apps/`, intermediates in `forge/make/`) and `framework/work.mk` (§5.4); `Makefile:120`'s `sed -i` made portable (I15) |
| C76 | `src/Apps/Paint/Style.hh:59,110-115` (`basePath()`) | `utils/Apps/Paint/base.toml` beside `build/`, from `/proc/self/exe`, or under `$HEKIT_ROOT` | hep | `src/Apps/Paint/base.toml` under `$HEP` first, then from `/proc/self/exe` (`framework/Apps/Paint.exe` → three levels up) on Linux only (I15). Paint is plot-only: no identity changes |

### 6.3 Stack recipes (`docs/stack/` → the root, `platforms/`, `patches/`)

| # | Site | Today | Becomes |
|---|---|---|---|
| C45 | `build_stack.py:51-57` (`SETUP`), `:387-390` (`setup_text`), `:443-449` | writes `$prefix/setup.sh` (the stub: `HEKIT_ROOT`, `utils/Env/hep_env.sh`) unless one is there | gone: `setup.sh` is tracked (§5.8). `build_stack.py` writes `stack/setup_extra.sh` from `setup_extra` instead |
| C46 | `build_stack.py:43,177`; `settings.toml` `prefix`, `hekit_root` | `REPO = HERE.parent.parent`; `prefix = "~/HEP"`; `{hekit_root}` | `REPO = HERE` (the recipe sits at Heimdall's root); the prefix is `REPO` itself, and `prefix` in `settings.toml` goes; `hekit_root` goes |
| C79 | `build_stack.py:171,184,212,224,349,357,406,433` (the prefix's layout) | `src/`, `build/<pkg>`, `install/`, `.venv/`, `logs/`, `.stamps/` under the prefix | `stash/`, `forge/<pkg>/`, `stack/`, `env/venv/`, `forge/logs/`, `stack/.stamps/` |
| C47 | `build_stack.py:443` | keeps an existing `setup.sh` | gone with C45 |
| C48 | `packages.toml` `[fastjet] patch` | `utils/Env/patches/…` | `patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch` |
| C49 | `Dockerfile` (`COPY docs/stack/`, `utils/Env/patches/`, `HEKIT_ROOT=/work`); `Dockerfile.dockerignore` | the repo's layout | `platforms/container/`; the build context is Heimdall, and the image holds `/opt/heimdall` with its stack inside (targets/container.md) |
| C50 | `mac/launch.sh`, `mac/README.md`; `docs/stack/README.md`, `build_by_hand.txt` | `utils/Env/hep_env.sh`, `~/HEP`'s `src/ build/ install/` | `platforms/mac/`: `$HEP/setup.sh`, `HEP` defaulting to `~/Github/Heimdall`; the docs describe `stash/ forge/ stack/` |
| C51 | `packages.toml [python]` | the venv (`{venv}` = `$prefix/.venv`) and `python_packages` | the venv at `env/venv`; one more `pre` command writes `heimdall.pth` with `$HEP/framework` (§5.5); `python_packages` unchanged |

### 6.4 Tests

| # | Site | Becomes |
|---|---|---|
| C52 | `conftest.py:23-34` | `HEP = parents[1]`; `sys.path` gets `HEP/framework`; the scratch work in `forge/scratch/` (§5.7); `HEP_*` (with `HEP_REPORTS`); the guard without `THEIRS` |
| C53 | `pytest.ini` | unchanged |
| C54 | `test_paths.py` (whole) | rewritten for §5.2–5.3: `hep_root`, the walk-up search, `HEP_WORK`, the `tests/` skip, the `HEKIT_*` refusal, `{repo}` refused |
| C55 | `test_hepkit.py:14-20` | `HEP/framework/hepkit.py`; `Kit.hh` at `HEP/src` |
| C56 | `test_stack.py:14-35` | `HEP/env`; `forge/make/flags.mk` |
| C57 | `test_plan.py:242`; `test_yd2rt.py:11`; `test_post.py:197`; `test_paint.py:21-22,262,272`; `test_plot_stage.py:23`; `test_gates_p1.py:21`; `test_process_generators_p4.py:52` | the apps under `apps_dir()`; `base.toml` at `src/Apps/Paint/` |
| C58 | `test_modules_p4.py:19`; `test_plot.py:91`; `test_plot_stage.py:88` | module programs and plugins under the scratch work's `build/` |
| C59 | `test_gates_run_sweep.py:124` (`cwd=REPO`) | `cwd` = the scratch work |
| C60 | `test_layers.py:268` (message) | `env/stack.toml` |
| C74 | `test_layout.py:15-22` | `HEP/framework/tools/figures/layout.py` |
| C75 | `test_deck.py:32-33,170`; `test_deck_build.py:52-53,129` | `HEP_RESULTS`, `HEP_OUTPUT`, `HEP_REPORTS` |
| C61 | `test_docs.py` | `DOCS = HEP/docs`; `CODE` scans `framework/ src/ tests/` and the `Makefile`, not `modules/` (none in the repo; the fixture's modules are under `tests/`); the link test reads `CLAUDE.md` instead of `bots/BOT.md` |
| C62 | `test_stack_build.py` | the recipes at the root; the prefix layout of C79; no setup text (C45) |
| C63 | `test_imports.py` | `framework/runner/`; the "core never names a tool" check reads `framework/tools/` |
| C64 | `tests/support.py`, `tests/runner/helpers.py` | the `hep` path (`HEP/framework/bin/hep`); the environment helpers set `HEP_*` |

### 6.5 Work → framework (High-Energy's own files): parked (D31)

These are for High-Energy's lean conversion (§4.4), which is not done now. Kept, so the parked step
is complete when the user asks for it.

| # | Site | Would become |
|---|---|---|
| C65 | `configs/PhotoProduction/eic.toml:170` | `{work}/modules/PhotoProduction/delphes_jets.py` (by `hep migrate`) |
| C66 | `modules/PhotoProduction/delphes_jets.py:16` | the `sys.path` line removed |
| C67 | `modules/PhotoProduction/Inproc/Analysis.hh:68`; `configs/PhotoProduction/InProc{EIC,Zeus}.toml:23` (comments) | `$HEP/patches/…` |
| C77 | comments that cite framework paths: `Inproc/Stamp.hh:3`, `Inproc/Engines.hh:13` (`utils/PythiaRun.hh`), `Inproc/Analysis.hh:13` (`utils/Env/patches/`), `delphes_jets.py:9` (`utils/hepkit.py`), `modules/Lambda/README.md:8` (`utils/Module.hh`) | `src/PythiaRun.hh`, `$HEP/patches/`, `framework/hepkit.py`, `src/Module.hh`; shown with C65–C67 |
| C68 | comments citing old manual sections (current_plan: `Comparison/generators.toml`, `Lambda/lambda.toml`, `PhotoProduction/eic.toml`, `xx/madgraph.toml`) | left to the user, as now |

The reference point (09 S1) is run from a scratch copy of High-Energy's PhotoProduction. There,
C65 is applied by `hep migrate` to the copy only.

### 6.6 The manual (`docs/`, P4)

| # | Where | Becomes |
|---|---|---|
| C69 | 01 (layout), 02 §1 and §12, 05 §2, 06 §1, §2, §14, §15, §16, §25; `docs/reporter/`, `docs/stack/` | rewritten for Heimdall and work dirs, by 06's renames |
| C70 | 07 (the record) | new V-rows for this split (V105 onward: V102–V104 are the decks); D-rows here are cited from them |
| C71 | `docs/README.md` | the reading paths, from Heimdall's `README.md`; it lists `docs/stack/`, `docs/reporter/` and `docs/framework/` |

---

## 7. The move map

Every path `git ls-files` lists at `split/base` goes to exactly one place. The block below is data:
P1's script reads it from this page, applies it, and fails on any path matched by no rule.

**Reading a rule:**
- **`side`:** `"fw"` copies the path into Heimdall at `to`; `"work"` leaves it in High-Energy
  only.
- **First match wins.**
- **`to`:** a `to` ending in `/` receives the path minus the rule's literal prefix (everything
  before the first wildcard, up to its last `/`). Any other `to` is a file name.

```toml
# 01_Target.md §7 — High-Energy (split/base) → Heimdall. Read by P1 (04_Seed.md).
rules = [
  # framework/ and env/: what runs, and its environment
  ["utils/Env/runner/**",       "fw",   "framework/runner/"],
  ["utils/Env/hep",             "fw",   "framework/bin/hep"],
  ["utils/Env/run",             "fw",   "framework/bin/run"],
  ["utils/Env/hep_env.sh",      "fw",   "env/hep_env.sh"],
  ["utils/Env/flags.sh",        "fw",   "env/flags.sh"],
  ["utils/Env/stack.toml",      "fw",   "env/stack.toml"],
  ["utils/Env/stack.py",        "fw",   "env/stack.py"],
  ["utils/Env/schema/**",       "fw",   "framework/schema/"],
  ["utils/Env/quantities.toml", "fw",   "framework/schema/quantities.toml"],
  ["utils/Env/latex.toml",      "fw",   "framework/schema/latex.toml"],
  ["utils/Env/patches/**",      "fw",   "recipes/patches/"],
  ["utils/Env/*/**",            "fw",   "framework/tools/"],    # the 16 plugin folders
  ["utils/hepkit.py",           "fw",   "framework/hepkit.py"],
  # src/: what is compiled (today's utils/ without Env/ and hepkit.py)
  ["utils/**",                  "fw",   "src/"],                # the kits, App_*.cc, Apps/Paint/
  ["Makefile",                  "fw",   "Makefile"],            # split in P3 into Makefile and framework/work.mk
  ["pytest.ini",                "fw",   "pytest.ini"],
  # recipes/: the stack's recipes, in one folder so the root stays the entry points (2c, final)
  ["docs/stack/Dockerfile*",    "fw",   "recipes/platforms/container/"],
  ["docs/stack/mac/**",         "fw",   "recipes/platforms/mac/"],
  ["docs/stack/**",             "fw",   "recipes/"],            # build_stack.py packages.toml settings.toml README.md build_by_hand.txt
  # the manual, the agents' files
  ["docs/Untitled-1.md",        "work", ""],
  ["docs/**",                   "fw",   "docs/"],               # 01–07, README, audit_2/, reporter/, framework/
  ["bots/BOT.md",               "fw",   "CLAUDE.md"],           # rewritten in P1 for Heimdall
  ["bots/**",                   "fw",   "bots/"],
  # the tests
  ["tests/fixtures/configs/**", "fw",   "tests/fixtures/work/configs/"],
  ["tests/fixtures/README.md",  "fw",   "tests/fixtures/work/README.md"],
  ["tests/**",                  "fw",   "tests/"],
  # the rest: stays in High-Energy
  ["configs/**",                "work", ""],
  ["modules/**",                "work", ""],                    # and frozen copies → tests/fixtures/work/modules/ (P1)
  ["aux/**",                    "work", ""],
  ["_text/**",                  "work", ""],
  ["_vs/**",                    "work", ""],
  ["archive/**",                "work", ""],
  [".vscode/**",                "work", ""],
  ["generator_comparison.*",    "work", ""],
  [".gitignore",                "work", ""],
]
```

**Counts at `81253a4`:** 1578 tracked paths (P1 recounts at `split/base`). The rules were checked
against that list by P1's own script: every path matches one rule, and no two paths land on one
Heimdall path.

| Group | Paths | Goes to |
|---|---|---|
| `utils/Env/` | 69 (`runner/` 25, the 16 plugin folders 32, `schema/` 3 and two TOMLs, `hep`, `run`, `hep_env.sh`, `flags.sh`, `stack.toml`, `stack.py`, the patch) | `framework/` 64, `env/` 4, `patches/` 1 |
| `utils/` else | 14 (`hepkit.py`; 4 kits, 3 apps, `Apps/Paint/` 6) | `framework/hepkit.py`; `src/` 13 |
| `docs/stack/` | 12 | the root 3, `platforms/` 7, `docs/stack/` 2 |
| `docs/` else, except `Untitled-1.md` | 28 (pages 8, `audit_2` 1, `reporter` 5, `framework` 14) | `docs/` |
| `tests/` | 86 | `tests/` |
| `bots/` | 4 | `CLAUDE.md`, `bots/` 3 |
| `Makefile`, `pytest.ini` | 2 | the root |
| **fw total** | **215** | |
| `configs/` 25, `modules/` 18, `aux/` 1311, the rest 9 | **1363** | stays in High-Energy |

**Made new in Heimdall** (P1, P2 and P3), not moved:
- `README.md`, `.gitignore`, `setup.sh`, `pth.py`;
- `framework/work.mk`, `framework/templates/work/*`;
- `platforms/container/heimdall.def`;
- `tests/fixtures/work/{hep.toml, modules/**, datasets/zeus_eic.yoda}`.

**High-Energy is not changed** (D31). The "work" side of the map only says what Heimdall leaves
behind.

---

## 8. Before the reinstall (the user's checklist)

The fresh system is this lab PC, wiped (D16). Git holds the code. These are what it does not hold,
to copy to a disk that survives the wipe:

| What | Why | How |
|---|---|---|
| High-Energy, every branch and tag | the source of everything | `git push origin rework` (and the tags), or `git bundle create HE.bundle --all` |
| `datasets/` (`zeus_eic.yoda`, 20 kB) | not in git; the fixture uses it | copy |
| `literature/`, `cross_machine/`, `reports/` | the user's, not in git | copy |
| `~/HEP/src/*.tar*`, `*.tgz` and `~/HEP/LHAPDF-6.5.6.tar.gz` (optional, 555 MB) | saves the downloads: `build_stack.py` uses an archive already in `stash/`; 05 S2 renames them to its names | copy |
| **the reference point** (90 kB): `output/PhotoProduction/inproc_zeus/01_default/NNPDF23lo/{cards,config,provenance.json}` and `results/PhotoProduction/inproc_zeus/01_default/NNPDF23lo/` | P6 runs it again on its seed and compares (09 S1) | copy, keeping the paths under `kept/reference/` |
| `results/` (optional) | only to look at again; the comparisons in `09` use numbers recorded in these files | copy if wanted |
| `~/.claude/projects/…High-Energy/memory/` (optional) | the agents' notes about this repo | copy |

**Before the copy:**
- Round 2b recorded the lab PC's baselines into these files: the stack's versions, the PDF sets,
  one reference point's numbers.
- These files are committed and pushed with `rework`, because the baselines must survive the wipe.

On the new install, P0 brings the copies back into `~/Github/Heimdall/.setup/kept/`. The user's own
folders stay there until the user says where they go (D31: High-Energy is not touched).

---

## 9. Decisions added here

These continue README §2's table. Round 2c's D26–D33 are in README §2, and the rows below carry
their amendments.

| # | Decision |
|---|---|
| D17 | Heimdall's layout is §2's (as amended by D26): the recipes at the root, `env/ framework/ src/ docs/ bots/ tests/ patches/ platforms/`; ignored `stack/ forge/ stash/ env/venv/ framework/Apps/ .setup/`. `framework/tools/` holds every plugin folder, so the folder contract is unchanged. |
| D18 | `hep_root()` is where the running code is. A `$HEP` that disagrees with it is refused. `work_root()` is `$HEP_WORK`, or the first `hep.toml` with `[work]` walking up from the working directory. Markers under `hep_root()/tests/` are skipped. |
| D19 | `{repo}` is retired: `{hep}` and `{work}` (D28). A run TOML's `{repo}` is refused, and `hep migrate` rewrites it to `{work}`. Set `HEKIT_*` variables are refused, naming their replacements. |
| D20 | Commands are scoped (§5.2): work, Heimdall-only, or anywhere. `hep where` is new. `hep build` and `hep make` act on the work dir, and `--framework` acts on Heimdall. |
| D21 | Every build tree has its own `flags.mk` from the one probe: Heimdall's in `forge/make/`, a work dir's in its `build/`. |
| D22 | Python reaches Heimdall through the venv's `heimdall.pth`, one line, `$HEP/framework` (D29). No module or notebook writes `sys.path` lines. |
| D23 | The tests run in a persistent scratch copy of the fixture work dir, `forge/scratch/work`. The fixture carries frozen copies of the modules the tests build. |
| D24 | The move map is data (§7). P1 applies it, and fails on a path no rule matches. |
| D25 | `hep.toml` is `[work] name` and `[framework] expects`, nothing else. `expects` is warned about when it is not an ancestor of Heimdall's `HEAD`, never enforced. |

---

## 10. Risks the phases plan around

| Risk | Where it bites | Plan |
|---|---|---|
| The reinstall is Ubuntu 26.04: some `apt_packages` names may be gone or renamed (`libpcre3-dev` is a likely one: Debian has been removing PCRE 1), and Python and GCC are newer | P2 | P2 S1 checks every package with `apt-cache policy`. The ubuntu annex lists allowed renames as *allowed adjustments* (02 §7). A compiler or Python incompatibility in ROOT, Herwig or Whizard is a gate, not a quiet fix |
| A move breaks a relative assumption the grep did not see | P3 | the fast suite after every task group; C1–C80 are each a task |
| The fixture's frozen modules drift from High-Energy's | P4, later | they are test data (V52's rule): changed only with a test |
| Identities: everything reruns on the new install | P5, P6 | expected; the comparisons in `09` are by numbers within tolerances, not by identity |
| **`git clean -x` in Heimdall deletes `stack/`**, which is hours of building | any time | never run it there (D33; `CLAUDE.md`, README). `forge/` and `stash/` may be emptied by hand; `make clean` never touches the stack |
| An editor or indexer watching 20 GB of `stack/ forge/ stash/` | daily use | `files.watcherExclude` and `search.exclude` (D33) |
