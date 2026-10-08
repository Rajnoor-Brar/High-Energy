# The framework in `$HEP`: round 1

This is the round-1 document of a two-round plan. Round 2 writes the plan files that AI agents follow
on a **fresh system**:
- to build `$HEP` as the one home of the software stack **and** of the framework and its
  environment;
- to create **work directories**: any number, independent of each other, each holding only configs,
  modules, projects and what they produce.

This page fixes what round 2 must not reopen:
- the decisions (§2);
- the target layout (§3);
- the file set (§4);
- how the agents coordinate (§5);
- the couplings to undo (§6);
- round 2's brief (§7).

Nothing on the lab PC changes in either round: no code, no config, no `~/HEP`. The plans are
executed on the new machine.

Written 2026-10-08 against `rework` at `31817f8`.

---

## 1. Where things stand

Today one checkout, `~/Github/High-Energy`, is both framework and work
([06 §1](../06_Internals.md#1-repository-layout)):

| Side | Paths |
|---|---|
| framework | `utils/`: the runner, the tool folders, the C++ kits and apps, `hep`, `hep_env.sh`, `stack.toml`; `docs/stack/` (building the stack); the manual `docs/01`–`07`; `tests/`; `Makefile` |
| work | `configs/`, `modules/`, `build/`, `output/`, `results/`, `datasets/` |
| neither | `aux/`, `literature/`, `cross_machine/`, `_text/`, `_vs/`, `archive/`, `reports/`, `.vscode/`, `generator_comparison.*` |

`~/HEP` holds the source-built stack (`src/ build/ install/ .venv/`). Its `setup.sh` is a 9-line
stub that sources the checkout's `utils/Env/hep_env.sh` through `HEKIT_ROOT`. Making a second,
independent workspace therefore means cloning the whole framework again. The checkout is also the
only way to the environment.

**Portability.** The runner is standard-library Python (plus `tomli_w`), so it runs on every Linux
target: Ubuntu, a cluster node, a container. Those differ only in how the stack and its system
packages arrive. Two parts of the framework are not plain Python:

- **The compiled apps:** App_Pythia, App_PythiaCheck, App_yd2rt and Paint. They are built per
  machine, against that machine's stack, by one `hep build`.
- **Five Linux-only spots, which block macOS:**
  - `runner/events.py:17,188` uses abstract sockets and `/proc/net/unix`, so `hep run` does not
    start on a Mac ([stack/mac §5](../stack/mac/README.md#5-known-limits));
  - Paint's `Style.hh:112` reads `/proc/self/exe`;
  - `utils/Env/hep:48` calls `nproc`;
  - `Makefile:120` uses GNU `sed -i`;
  - `hep_env.sh` sets `LD_LIBRARY_PATH` and needs bash 5.

Fixing these is a framework step (P3), not a per-target workaround.

---

## 2. Decisions

The user's answers of 2026-10-08:
- the framework becomes its own repo with fresh history;
- the plans cover all four targets;
- a work dir is found by a marker file, searched upward from the working directory;
- the agents run through and stop at gates;
- `hep setup <directory>` makes a work dir.

Round 2 details these decisions. It does not reopen them.

| # | Decision |
|---|---|
| D1 | **`$HEP` is the machine's home.** It holds the stack (`src/ build/ install/ .venv/ logs/ .stamps/`), the framework repo, the framework's compiled apps and `setup.sh` (`load_hep`). There is one per machine. A second prefix is allowed, and work dirs are not bound to one. |
| D2 | **The framework is a new git repo with fresh history**, at `$HEP/<fw>/`, seeded from High-Energy at a pinned revision. The import commit names that revision. High-Energy becomes the read-only archive: the record's citations (`git show c5cbaa3:…`, `rework/v1-final`) stay valid there. |
| D3 | **A work dir is marked by `hep.toml`** at its root. `hep` finds it by walking up from the working directory, as git does, and `$HEP_WORK` overrides the search. Outside a work dir, work commands refuse and point to `hep setup`. Framework commands work anywhere: `hep explain`, `hep status --stack`, building the framework, `hep setup`. |
| D4 | **Work dirs are independent.** Each has its own `configs/ modules/ datasets/ build/ output/ results/ reports/`, and may have its own git repo. No path or import crosses work dirs, and they share only `$HEP`. V94's cross-project imports stay valid within a work dir. |
| D5 | **The framework's apps are compiled once per `$HEP`** and shared: App_*, Paint, Herwig's `HerwigDefaults.rpo` and the flag cache (`flags.mk`). A work dir builds only its own module programs and Rivet plugins, against `$HEP/<fw>/include` and the shared flags. |
| D6 | **One environment entry.** `$HEP/setup.sh` sources `$HEP/<fw>/env/hep_env.sh`, with no outside checkout. The `HEKIT_*` variables become `HEP_*`: `HEP_FW`, `HEP_WORK`, `HEP_OUTPUT`, `HEP_RESULTS`, `HEP_CONFIGS`. This is the rename K15 ([current_plan](../../bots/current_plan.md)), done here. |
| D7 | **`{repo}` splits in two:** `{fw}` (the framework's apps, Herwig's repository) and `{work}` (`build/Rivet`, the module programs). A leading `./` in a run TOML means the work root, which restates V13. |
| D8 | **Provenance records two git states**, the framework's and the work dir's, and the `$HEP` prefix. The identity rules are unchanged. The shared apps' `exe_sha256` is the same in every work dir on one machine. |
| D9 | **The framework's tests run against a frozen fixture work dir** inside the framework repo (`tests/fixtures/work/`, which has its own `hep.toml`). They never touch a real work dir, and V52's guard stays. |
| D10 | **`docs/stack/` moves into the framework as `stack/`**: `build_stack.py`, `packages.toml`, `settings.toml`, `patches/`, `mac/`, and `container/` (the Dockerfile and an Apptainer definition). Its `setup.sh` points at `$HEP/<fw>`. Bootstrap: clone `<fw>` into `$HEP` first (that needs only git and python3), then build the stack from it. |
| D11 | **One framework for every target.** Portability fixes are framework code (P3). The annexes `targets/*.md` hold only differences: system packages, the stack overlay, launching. |
| D12 | **Three agents:** an orchestrator, a background builder and an independent verifier, with a per-machine state in `$HEP/.setup/` and named gates (§5). |
| D13 | **Not migrated:** `output/`, `results/`, `build/`, `aux/`, `literature/`, `cross_machine/`, `_text/`, `_vs/`, `archive/`, `reports/`, `generator_comparison.*` and `.vscode/`. They stay in High-Energy. The work dir template may carry an optional `.vscode/c_cpp_properties.json` pointing at `$HEP/<fw>/include`. |
| D14 | **`hep setup <directory>`** creates an empty, initialised work dir: what the framework requires, and the key folders (§3.1). It is the one supported way to make a work dir, and it also makes D9's fixture work dir. |

**Left for round 2 to ask:**
- the framework's name, `<fw>` on this page;
- where the first work dir goes, and what it is called.

---

## 3. The target

```
$HEP/                              one per machine (default ~/HEP)
  setup.sh                         load_hep → <fw>/env/hep_env.sh
  .venv/  src/ build/ install/ logs/ .stamps/          the stack, as build_stack.py makes it today
  .setup/state.toml, log.md        this machine's agent state and log (not in git; §5)
  <fw>/                            git: the framework
    bin/hep, bin/run               env/hep_env.sh, env/flags.sh
    runner/  tools/<tool>/  backends/{yoda,mpl}/  figures/
    schema/  quantities.toml  latex.toml  stack.toml  stack.py
    include/                       Status.hh Kit.hh Module.hh PythiaRun.hh hepkit.py (on the venv's path by a .pth)
    apps/                          App_Pythia.cc App_PythiaCheck.cc App_yd2rt.cc Paint/
    Makefile                       the apps, the C++ tests, schema, docs → <fw>/build/ (+ flags.mk, Herwig/)
    make/work.mk                   the module and Rivet rules, which a work dir's one-line Makefile includes
    stack/                         build_stack.py packages.toml settings.toml patches/ mac/ container/
    templates/work/                what `hep setup <dir>` lays down
    docs/                          the manual 01–07 (rewritten for the split); docs/framework/ (these plans)
    tests/                         runner/ integration/ cxx/ fixtures/work/ reference/
    CLAUDE.md                      the framework's agent rules (from bots/BOT.md)

<work>/                            any number, anywhere; made by `hep setup <work>`
  hep.toml                         the marker: name; [framework] expects = "<rev>" (warned, never enforced)
  Makefile                         include $(HEP_FW)/make/work.mk   (so `make modules/P/X.exe` still works)
  configs/ modules/ datasets/ results/ output/ reports/ build/      the key folders, per project inside
  .gitignore  README.md  CLAUDE.md the work dir's agent rules (configs are the user's; tests never write results)
```

The directory names inside `<fw>` are a sketch. Round 2's `01_Target.md` fixes them, together with
the move map.

### 3.1 `hep setup <directory>`

**What it makes**, from `<fw>/templates/work/` (a new file is a template edit, never a code change):
- the key folders `configs/ datasets/ modules/ results/ output/ reports/ build/`;
- `hep.toml`, which holds the work dir's name and the framework revision it was made with
  (`[framework] expects`);
- the one-line `Makefile`;
- a `.gitignore` for `build/`, `output/`, `results/` and the large files in `datasets/` and
  `reports/`;
- `README.md` (what each folder is for);
- `CLAUDE.md` (the work dir's agent rules).

**Options:**
- `--project <P>` also makes `configs/<P>/` and `modules/<P>/`, with a commented starter run TOML
  and base card that `hep check` accepts;
- `--git` runs `git init` and makes the first commit.

**Safety:**
- A missing or empty directory is set up.
- An existing work dir is completed, never overwritten: the command adds only what is missing and
  lists it.
- A non-empty directory that is not a work dir is refused, with a hint.
- Nothing is written outside `<directory>`.

**Verification rows** (round 2 writes them into P3's step):

| Row | Expected |
|---|---|
| a fresh directory | its tree matches the template (counts of files and folders) |
| a second `hep setup` on it | 0 files added |
| a non-empty foreign directory | refused, exit 2 |
| `--project Toy`, then `hep check Toy/<starter>` | passes |
| `hep build` in the new work dir | clean, 0 targets |
| `hep` from a subfolder of it | resolves this work dir |

---

## 4. The file set round 2 writes

| File | Phase | Content |
|---|---|---|
| `README.md` | — | this page (round 1) |
| `01_Target.md` | — | both trees in full; **the seam**: the variables, the two roots, the marker search, placeholders, includes, hepkit, provenance, tests; **the move map** (every `git ls-files` path → its new home, or "stays in High-Energy"); the D-rows extended |
| `02_Agents.md` | — | the coordination scheme of §5 in full, with the orchestrator's start prompt |
| `03_Preflight.md` | P0 | survey the machine (OS, arch, cores, RAM, disk, sudo, network, docker/apptainer, python ≥ 3.11); pick the annex; bring High-Energy at a pinned revision (a clone after a push the user approves, or a `git bundle` moved by hand); create `$HEP/.setup/` |
| `04_Seed.md` | P1 | create `$HEP/<fw>` from the move map: mechanical moves only, the import commit, `git diff --stat` counts against the map |
| `05_Stack.md` | P2 | `stack/build_stack.py` with the annex's overlay, **in the background** (hours) while P3 proceeds; then versions, the FastJet patch, `import ROOT`/`pythia8`/`yoda`, the 21 PDF sets |
| `06_Seam.md` | P3 | the code changes:<br>• paths: two roots, the marker search<br>• placeholders<br>• the Makefile split<br>• the environment<br>• `hep`'s resolution<br>• **`hep setup <dir>` as its own step** (template, command, tests)<br>• the `HEP_*` rename<br>• provenance<br>• hepkit importable<br>• tests on the fixture work dir<br>• `docs.py`/`test_docs`<br>• the macOS spots of §1 |
| `07_Framework.md` | P4 | `hep build` (the apps); `make test`, then the slow suite, with pass counts against the lab PC's baseline; `make docs`; the manual rewritten for the split (01 layout, 02 §1 and §12, 05 §2, 06 §1, §2, §14 and §15) |
| `08_Workdirs.md` | P5 | `hep setup` for each work dir; the first one migrated from High-Energy (`configs/`, `modules/`, `datasets/`), then `hep build`, `hep check` on every config and a small run; a second, empty work dir with a toy project; checks that the two are independent |
| `09_Verify.md` | P6 | the physics gates (`tests/reference`); one small PhotoProduction point against the lab PC's numbers (σ, counts, YODA sums, within stated tolerances); handover: the agent rules, the final report, publishing the framework repo (a gate) |
| `targets/ubuntu.md`, `cluster.md`, `container.md`, `macos.md` | annexes | **differences only**, under four headings (below) |

The annexes cover:
- **where the system packages come from:** apt; none, with Apptainer or environment modules; the
  image; the Brewfile;
- **the overlay TOML;**
- **launching;**
- **known limits:**
  - on a cluster: FIFOs on a shared filesystem, and no sudo;
  - in a container: abstract sockets are per network namespace;
  - on macOS: bash 5, and `DYLD_LIBRARY_PATH`.

**Step format.** Each phase has 2–3 substantial steps. Each step gives:
- its id and goal;
- **preconditions:** the earlier steps done, plus probe commands;
- **tasks:** exact commands, or edits by file:line;
- the **gates** it touches;
- **verification rows:** a command and the number or text it must give;
- **on failure:** what to collect, and when to stop.

**Logs are per machine,** in `$HEP/.setup/log.md`, not in the plan files. The same plans serve the
new machine, a cluster and, later, the lab PC after its OS upgrade. Their logs must not collide in
git.

---

## 5. How the agents coordinate

### Roles

| Role | Does |
|---|---|
| **Orchestrator** (the main session) | reads this page, then 01, then 02, then the state; picks the next step; works inline by default. It is the only one that writes `$HEP/.setup/state.toml`, and the only one that talks to the user |
| **Builder** (background) | the long builds only: the stack (P2) and the slow suite. It runs them with a monitor and reports on exit |
| **Verifier** (a fresh context, read-only) | re-runs a phase's verification rows and the tests once the orchestrator calls the phase done, and reports the numbers. A phase is done only when its verifier agrees |

### State

`state.toml` holds, for each step:
- its status: `todo`, `running`, `done`, `failed` or `blocked`;
- its verification numbers, and when they were taken.

It also holds this machine's choices (the annex, cores, packages, the pinned revision) and the
approvals given at gates.

The stack's stamps (`$HEP/.stamps/`) stay authoritative for packages. **Resuming** means: read the
state, then re-run the current step's preconditions.

### Gates

At each of these the orchestrator stops and asks the user:
- sudo or apt;
- downloads: the list and its size, approved once per phase (the stack's tarballs, plus about 4 GB
  of Geant4 data);
- joining the docker group (the user's own action);
- any deletion outside `$HEP/{src,build}`;
- any write to the High-Energy source, which is read-only;
- pushing or publishing a repo or an image;
- a verification row that fails twice;
- anything the plan files do not decide.

### Concurrency and reports

**Concurrency:**
- one stack build at a time;
- one pytest session at a time;
- P3's edits may proceed while P2 builds;
- tests that need the stack wait for P2.

**Reports:** a short one at every gate and at every phase's end, saying what is done, its numbers,
and what is next.

### Rules carried over

From [BOT.md](../../bots/BOT.md) and the working agreements:
- stage commits by path;
- tests write only their scratch;
- `encoding="utf-8"` on every text read and write;
- read a tool's ledger rows ([07 §3](../07_Record.md#3-the-knowledge-ledger)) before touching it;
- the user's configs are theirs.

---

## 6. The couplings to undo

Every row was checked by grep on 2026-10-08. Round 2 re-verifies the rows and extends them.

| # | Where | Today | Becomes |
|---|---|---|---|
| I1 | `utils/Env/runner/paths.py:23-70` | one root, found by the markers `configs, modules, utils/Env` or by `HEKIT_ROOT`; `results_root`, `output_root`, `configs_root` and `build_root` all hang from it | `fw_root()` (the runner's own location, or `HEP_FW`) and `work_root()` (the marker search, or `HEP_WORK`) |
| I2 | `paths.py:77-86`, `ROOTS` | `executable` → `build/<P>`, `data` → `datasets/` | the work root |
| I3 | framework files read through `repo_root()`: `labels.py:22`, `quantities.py:31,73,272`, `schema.py:33`, `plot.py:127,168,397,486,1117`, `docs.py:81,159`, `cli.py:678`, `config.py:847`, `tools.py:326` | the repo | the framework root |
| I4 | the apps through `build_root()`: `plot.py:292,328` (App_yd2rt), `plot.py:1083,1236` (Paint) | `build/` | the framework's build |
| I5 | Rivet through `build_root()`: `hepfiles.py:73`, `yoda/backend.py:313`, `mpl/backend.py:102` | `build/Rivet` | the work build |
| I6 | `{repo}` in the tool folders | `pythia/tool.toml:4,44`, `yd2rt:5`, `plotmerge:12`, `herwig:33,48` (apps, Herwig's repository); `rivet:15,26,29,42`, `merge:13` (`build/Rivet`) | `{fw}` for the first group, `{work}` for the second; the contexts in `execute.py:294` and `tools.py:215,264,671,928,994,1030,1046,1099,1324` follow, and so does `schema/run.toml:370` (`[prelim.commands]`) |
| I7 | `record.py:234-241` | `git_state()` of one repo | two states (D8) |
| I8 | `Makefile` | one file: `-I utils`; the rules for apps, modules, Rivet, `tests/cxx`, Herwig, flags, schema and docs | `<fw>/Makefile` and `make/work.mk` |
| I9 | `utils/Env/hep` | root from `HEKIT_ROOT` or `../..`; `make -C $root`; `nproc` | framework and work resolution; `hep setup` (D14); a portable core count |
| I10 | `utils/Env/hep_env.sh:10-17,133-136,177` | `HEKIT_ROOT` default; `utils/Env` on `PATH`; `hep_cd` | `$HEP/<fw>/bin`; `hep_cd` within the current work dir |
| I11 | `~/HEP/setup.sh`; `docs/stack/build_stack.py:52-55,177,443`; `settings.toml`'s `hekit_root`; `packages.toml`'s FastJet patch path; the `Dockerfile` (`COPY` paths, `HEKIT_ROOT=/work`); `mac/launch.sh` | the stack points at a checkout | all inside the framework repo; `setup.sh` written for `$HEP/<fw>` |
| I12 | `tests/conftest.py` (`REPO`, `sys.path`, `SCRATCH`, `FIXTURES`, the guard's `OURS`/`THEIRS`), `pytest.ini`, `tests/support.py`, `tests/runner/helpers.py`, `test_paths.py` | one repo | the fixture work dir; scratch under the framework's build |
| I13 | work → framework by path: `modules/PhotoProduction/delphes_jets.py:16` (`sys.path` `parents[2]/utils`); `modules/PhotoProduction/Inproc/Analysis.hh:68` and the comments at `configs/PhotoProduction/InProc{EIC,Zeus}.toml:23` (all three cite `utils/Env/patches`) | paths into the checkout | hepkit through the venv; the citations repointed in P5's migration (the user's files: shown first, applied with approval) |
| I14 | the manual and `tests/runner/test_docs.py` | `utils/…` paths throughout | rewritten in P4; `make docs` |
| I15 | Linux-only: `events.py:17,188-191`, `utils/Apps/Paint/Style.hh:112`, `hep:48`, `Makefile:120`, `hep_env.sh` | — | portable, in P3 |
| I16 | `HEKIT_ROOT`, `HEKIT_RESULTS`, `HEKIT_OUTPUT`, `HEKIT_CONFIGS` (K15); F14 (v1's `hekit` in the venv) | — | renamed (D6); absent from a fresh venv |
| I17 | transport | the local `rework` is 125 commits ahead of `origin/rework`, last pushed 2026-09-26 | P0 needs a push (a gate: publishing) or a `git bundle` |

---

## 7. Round 2's brief

Round 2 runs only on the user's order. It may write `docs/framework/` and `bots/current_plan.md`,
and nothing else: no code, configs or `~/HEP`.

**2a: `01_Target.md` and `02_Agents.md`.**
- Re-verify §6 by grep and extend it to a full classification of every `repo_root()`,
  `build_root()` and `{repo}` use.
- Build the move map from `git ls-files`, so that every tracked path is assigned.
- Ask the two open questions: the framework's name, and the first work dir.
- **Stop for the user's review.**

**2b: the phase files `03`–`09` and the four annexes.**
- Every row of §6 lands in a named step's tasks.
- `hep setup` gets its own P3 step (template, command, tests), and P5 uses it for every work dir.
- Every step has at least one verification row with a number.
- Record the lab PC's baselines read-only, from what is already recorded, with no rebuild and no
  long test:
  - `hep status --stack`;
  - the latest pass counts;
  - `build/flags.mk`'s `FOUND`;
  - the number of PDF sets;
  - one small reference point's σ, counts and YODA sums.
