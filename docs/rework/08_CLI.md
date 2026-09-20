# 08 — The `hep` command and the `~/HEP` extension layer

## 1. Code vs command: where each capability lives

Guideline 3 asks for a merit-based split between code and custom terminal commands. The criteria used:

| If the capability… | …it lives in | Because |
|---|---|---|
| touches events | C++ (`hep-run`, modules, plugins) | speed |
| composes tools, files and processes | Python (`hekit`), exposed as a `hep` subcommand | strictness, testability, one place |
| must change the *calling shell* (env vars, cwd, venv) | shell function in `env/hep_env.sh` (sourced by `~/HEP/setup.sh`) | a child process cannot change its parent |
| is a one-liner over an existing tool with no project logic | shell alias or function, or nothing | not worth code |
| is used interactively *and* by scripts | a `hep` subcommand, with `--json` output where useful | scriptable and pretty |

## 2. Command tree

```
hep run      CONFIG [--study S] [--pin Q=V]… [--across …] [--overlay Q] [INDEX…]
             [--events N] [--threads N] [--set key=val]… [--rerun] [--detach] [--plain] [--check]
hep plan     CONFIG [same selectors]  [--explain KEY] [--check]  [--json]
                 dry run: points, groups, pages, names, hashes, stage chains; --check adds card preflight
hep plot     CONFIG [same selectors]  [--backend mkhtml|mpl] [--points|--pages] [--open]
hep compare  CONFIG [same selectors]  [--ref data|POINT]
hep watch    [RUN|latest]
hep runs     [--active] [--last N]
hep show     POINT|RUN               provenance + changed settings + σ table + warnings
hep events   CONFIG|POINT|STORE [--from FILE] [-n N] [--tree|--final|--hard]
hep store    ls [PROJECT] | info STORE | verify STORE      HepMC3 event stores (11)
hep proc     CONFIG [same selectors] [--only NAME] [--backend auto|minuit2|roofit|scipy]   fits / RDF (12)
hep analyses [PATTERN] [--options]   Rivet analyses with .info summaries
hep studies  CONFIG                  list [study.*] with descriptions and point counts

hep config   init PROJECT | reference | migrate FILE | validate FILE
hep pdf      check CONFIG | install SET… | list [PATTERN]
hep build    [TARGET…] [--analyses PROJECT] [--modules PROJECT] [--clean]    (wraps cmake)
hep bench    CONFIG [--events 2000] [--json]     sink cost → concurrency recommendation
hep doctor   [--json|--brief]                    tool versions, Python imports, capabilities, env sanity
hep clean    CONFIG [--cache] [--events] [--plots] [--orphans] [--all]
                    [--older-than DAYS] [--dry-run] [--yes]
hep new      analysis|module|project NAME [--project NAME] [--into DIR]
```

**Mapping from today's commands:**

| Today | New |
|---|---|
| `rivpyth` | `hep run` |
| `rivpyth -p` | `hep plan` |
| `ydplt` | `hep plot --points` |
| `ydmrg` | `hep plot` (pages) |
| `hep_status` | `hep doctor` (the shell function becomes a thin alias) |
| `rivet-mkanalysis` + manual `.info`/`.plot` edits | `hep new analysis` — a plugin that **compiles as it stands**, with its `.info`; likewise `hep new module` (the four verbs and the scaling contract already obeyed) and `hep new project` (a config `hep plan` accepts, plus a base card). Nothing is ever overwritten |
| `make folder/x.so` | `hep build --analyses PhotoProduction` |
| `probe`-style re-reading of stored events | `[generator] tool = "store"` + `hep run` (replay), `hep store …` |
| ROOT macros / Paint for fits and plots | `hep proc` (fits, RDF) + `hep plot` |

**Transition path for the old tools (D18, D19):**
1. **P0-S03:** `rivpyth`, `ydplt`, `ydmrg` and `rivpyth_common.py` move into the repo under `tools/` and are put on `PATH` by `env/hep_env.sh`. The `~/HEP` copies are renamed `*.moved`.
2. **P0-S05:** they get the physics-relevant hotfixes (00/B2–B5, B20, B21) and stay the working tools.
3. **P4-S06:** once `hep run/plot` pass the golden and real-study comparisons, `tools/` moves to `legacy/tools/`, and the `~/HEP/*.moved` files are removed.

**Framework:** `click`, which is already installed. It gives nested groups and shell completion (`_HEP_COMPLETE=bash_source hep`).
- **Completion covers:**
  - study names (read from the config);
  - quantity names for `--pin` / `--across`;
  - point names for `show` and `watch`.
- `argparse` was considered. It is rejected for the lack of dynamic completion and the boilerplate needed for nested groups.

**Global options:**
- `--project-root`;
- `-v/-q`;
- `--plain`;
- `--json` (on read-only commands, for scripting and remote agents).

## 3. The shell layer: `env/hep_env.sh` + `~/HEP/setup.sh` stub

It stays a shell script, but the real content moves into the repo as **`env/hep_env.sh`** (versioned, P0-S02).
- `~/HEP/setup.sh` becomes a stub: it sets `HEP`, `HEP_INSTALL` and `HEKIT_ROOT`, then sources `$HEKIT_ROOT/env/hep_env.sh`.
- The previous file is kept as `setup.sh.pre-rework`.

Changes:

| Change | Why |
|---|---|
| Add `$HEP_INSTALL/root/lib` and `$HEP_INSTALL/pythia8/lib` to `PYTHONPATH` | `import ROOT` and `import pythia8` currently fail (00 F10) |
| Drop the hard-coded `RIVET_ANALYSIS_PATH=:~/Github/High-Energy/output/PhotoProduction` | `hep` sets plugin paths per run from `[rivet].paths`. The leading `:` also adds the CWD by accident. |
| `export HEKIT_ROOT=~/Github/High-Energy` (overridable) | `hep` works from any directory |
| `pip install -e $HEKIT_ROOT/utils/python` once (`hep_bootstrap`) | `hep` is then on `PATH` inside the venv. Versioned code, no copies in `~/HEP`. |
| Enable completion: `eval "$(_HEP_COMPLETE=bash_source hep)"` (cached to a file) | tab completion |
| `hep_status` → `hep doctor --brief` (keep the name as an alias) | one implementation |
| Keep `quit` (without it unsetting itself), `hep_refresh`, `hep_src`, `hep_build`, `hep_install`, `hep_help` | shell-only by nature |
| Make `_hep_prepend` idempotent (`case ":${!1}:"`) and never create empty path elements | `hep_refresh` duplicated every path, and empty elements mean the CWD (00 §4.6) |
| Add `$HEKIT_ROOT/tools` to `PATH` while the old tools are in use (P0-S03 → P4-S06) | the versioned `rivpyth`/`ydplt`/`ydmrg` |
| Add `hep_cd PROJECT` → `cd $HEKIT_ROOT/{configs,results}/PROJECT` | shell-only (changes the cwd) |
| Don't print the status banner on every source; print the one-line tool summary cached by `hep doctor` | faster shell start-up (the version probes of Herwig and Sherpa are slow) |

**Implemented in P0-S02:**
- `quit` removes only the elements recorded in `_HEP_ADDED`.
- `hep_refresh` re-sources `$HEP_SETUP`, the file that loaded the environment.

**Implemented in P1-S01:**
- Completion: `_hep_load_completion` caches `_HEP_COMPLETE=bash_source hep` in
  `${XDG_CACHE_HOME:-~/.cache}/hekit/hep-complete.bash` and regenerates it only when the `hep` entry point is
  newer. Interactive shells only, so sourcing stays at ~20 ms.
- Still deferred: `hep_bootstrap` (the editable install is a one-off), the `hep doctor --brief` alias and the
  cached one-line tool summary (P1-S07).

**After the move, `~/HEP` contains:**
- `setup.sh` (stub) and `setup.sh.pre-rework`;
- `install/`, `build/`, `src/`, `.venv/`;
- a machine file symlink (`~/.config/hekit/machine.toml`).

It no longer contains project code, which resolves the "orchestration unversioned" finding.

## 4. `hep doctor`

```
hep doctor
  toolchain   LHAPDF 6.5.6 · HepMC3 3.3.1 · FastJet 3.5.0 · ROOT 6.40.04 · YODA 2.1.3
              Pythia 8.317 · Rivet 4.1.3 · Herwig 7.3.0/ThePEG 2.3.0 · Sherpa 3.0.5
              Whizard 3.1.8 · MadGraph ✓ · Delphes ✓ · ONNX Runtime ✓
  python      yoda ✓ rivet ✓ lhapdf ✓ pyHepMC3 ✓ uproot ✓ onnxruntime ✓
              ROOT ✗ (not on PYTHONPATH: add $HEP_INSTALL/root/lib)
              pythia8 ✗ (add $HEP_INSTALL/pythia8/lib)   fastjet – (not built; optional)
              rich ✗ (pip install rich — live dashboard disabled)
  hep-run     built 2026-09-17 · components: rivet store(gz,zstd) modules onnx · delphes(external) ✓
  generators  pythia ✓ · sherpa ✓ (hepmc3, rivet) · whizard ✓ (hepmc3)
              herwig ⚠ run-only: ThePEG lacks HepMC/Rivet (rebuild --with-hepmc --with-rivet)
              madgraph ✓ (→ pythia shower)
  data        LHAPDF_DATA_PATH ✓ · <n> PDF sets installed        (mock-up; values illustrative)
  env         RIVET_ANALYSIS_PATH has an empty entry (adds CWD) ⚠
```

- `--json` is used by `hep plan` for capability checks.
- Results are cached for 24 h in `~/.cache/hekit/doctor.json`. The cache is invalidated when `$HEP_INSTALL` changes.
