# The HEP stack: building it on another machine

`build_stack.py` builds, from source, the software stack the framework runs on: the one the lab PC
has in `~/HEP` (Ubuntu 24.04, GCC 13), with the same versions, the same features and the fixes its
build needed. It runs on a Linux machine with apt, or in a Docker container. It needs only `python3`
(3.11+, or older with `tomli`): its standard library, no other packages.

| File | Is |
|---|---|
| [packages.toml](packages.toml) | each package: release, tarball, how it is built, what it needs |
| [settings.toml](settings.toml) | the run's settings, each with its default: prefix, jobs, features, the apt, pip and PDF lists |
| [build_stack.py](build_stack.py) | the engine: reads both, then fetches, builds, stamps and logs |
| [Dockerfile](Dockerfile) (+ `Dockerfile.dockerignore`) | the same build in an Ubuntu 24.04 image |

The data says what is built; the engine knows only five steps (fetch, unpack, configure or cmake,
install, stamp) and four kinds of package. A version bump, a new flag or a new package is a TOML
edit, never a code change.

The framework's own view of the stack (each library's flags and version) is
`utils/Env/stack.toml`; the shell environment is `utils/Env/hep_env.sh`
([06 §15.3](../06_Internals.md#153-the-flag-cache)).

---

## 1. Quick start

**On a machine** (sudo for the system packages, or `system=false` if they are installed):

```bash
python3 docs/stack/build_stack.py --list                 # each package: release, state, what this run builds
python3 docs/stack/build_stack.py                        # the core stack into ~/HEP (hours: ROOT alone is 1–2 h)
python3 docs/stack/build_stack.py packages=all           # and Sherpa, MadGraph, Whizard, ONNX Runtime, Geant4
source ~/HEP/setup.sh                                    # then, in this repository: hep build
```

**Settings.** Any key of `settings.toml` is `key=value` on the command line (`prefix=/opt/hep
jobs=8 graphics=OFF`); any key of a package is `<package>.<key>=value` (`root.release=6.40.06`,
`madgraph.url=…`, `fastjet.patch=` for none). For many changes, `--config my.toml`: a TOML file with
settings and `[package]` tables, which change packages or add new ones. The command line wins.

**Choosing packages.** `packages = "core"` (the default), `"all"`, or names (`packages="rivet
pythia8"`). What a named package needs is added when it is not installed; they are always built in
`packages.toml`'s order.

**A bash script instead.** `--dry-run` prints the whole build as a plain bash script, so it can be
read first, or saved and run where you want plain commands (`--dry-run > build.sh; bash build.sh`).
It is the same commands, without stamps or logs: run it on a fresh prefix.

**In Docker** (from the repository root):

```bash
docker build -f docs/stack/Dockerfile -t hep-stack .
docker build -f docs/stack/Dockerfile --build-arg PACKAGES=all --build-arg ROOT_JOBS=2 -t hep-stack:all .
docker run --rm -it -v "$PWD":/work -w /work hep-stack
```

The image is headless (`graphics=OFF`) and keeps the stack in `/opt/hep`. Its environment is the
repository's `hep_env.sh`, so a shell loads it when the repository is mounted at `/work`.

**Resuming.** A package that finishes is stamped (`$prefix/.stamps/<name>-<release>`) and skipped
next time, so the same command resumes after a failure, a reboot or a Ctrl-C. A changed release is a
new stamp, so it builds; delete a stamp to redo its package. A package's source is unpacked afresh
each time, so a half-done build never leaks into the next try.

**Downloads.** Every tarball the run needs is fetched first, four at a time, before anything is
built: a dead link stops the run in its first minute, not after ROOT. A tarball already in
`$prefix/src/<name>-<release>.<ext>` is used as it is, so a machine without network can build from
copied tarballs.

**Logs.** Each package writes `$prefix/logs/<name>.log`. A failure stops the build at once, prints
the last 30 lines and names the log.

**setup.sh.** At the end the run writes `$prefix/setup.sh`, the lab PC's stub: it sets `HEP`,
`HEP_INSTALL` and `HEKIT_ROOT` (this checkout) and sources `utils/Env/hep_env.sh`. A `setup.sh`
already there is kept.

---

## 2. The packages

`packages.toml`'s header documents every key. In its order (the build order), `core` first:

| Package | Release | Kind | For |
|---|---|---|---|
| `python` | your `python3` | a venv in `$prefix/.venv`, `python_packages` | every Python binding; the framework's `tomli_w`, `rich`, `uproot`, Pillow, matplotlib, pytest |
| `lhapdf` | 6.5.6 | autotools | PDFs for Pythia8, Herwig, Sherpa, Whizard, MadGraph |
| `hepmc3` | 3.3.1 | CMake | the event format between the tools |
| `fastjet` | 3.5.0 | autotools, the SISCone patch | jets for Rivet, Pythia8, Sherpa, Whizard and module programs |
| `fjcontrib` | 1.104 | autotools, into FastJet's prefix | the contribs; `libfastjetcontribfragile.so`, which Rivet links |
| `root` | 6.40.04 | CMake, `builtin_xrootd`, `root_jobs` | App_yd2rt, Paint, Delphes, module programs |
| `yoda` | 2.1.3 | autotools | Rivet's histograms; the plot backends |
| `rivet` | 4.1.3 | autotools | the analyses |
| `pythia8` | 8.317 | its configure, with ROOT's and Rivet's plugins | App_Pythia, InprocJets |
| `thepeg` | 2.3.0 | autotools, into `install/herwig7` | Herwig's event framework |
| `herwig` | 7.3.0 | autotools, into `install/herwig7` | the `herwig` tool |
| `delphes` | 3.5.1 | CMake | the `delphes` tool |
| `sherpa` | 3.0.5 | CMake (extra) | the `sherpa` tool |
| `madgraph` | 3.7.3 | unpacked into `install/madgraph`, configured (extra) | the `madgraph` tool |
| `whizard` | 3.1.8 | autotools, OCaml (extra) | the `whizard` tool |
| `onnxruntime` | 1.29.0 | the released binary, x64 or aarch64 (extra) | `// requires: onnx` |
| `geant4` | 11.4.2 | CMake, MT, GDML, datasets (extra) | `// requires: geant4` |
| `pdfsets` | `pdf_sets` | `lhapdf install` | the sets the configs and the tests use (the lab PC's 21) |

The installs go to `$prefix/install/<dir>`, under the directory names `hep_env.sh` expects:
`LHAPDF hepmc3 fastjet root yoda rivet pythia8 herwig7 delphes sherpa madgraph whizard onnxruntime
geant4`. More Python packages (scipy, pandas, scikit-learn, pyhf, …) go into `python_packages`.

**A new package** is a table in `packages.toml`, or in a `--config` file:

```toml
[mytool]
release = "1.2"
url     = "https://example.org/mytool-{release}.tar.gz"
kind    = "cmake"
needs   = ["root", "hepmc3"]
args    = ["-DWITH_ROOT={inst}/root"]
```

---

## 3. What makes the builds work together

Each of these was hit on the lab PC; the TOML files do what is in the right column.

| Package | Problem | What is done |
|---|---|---|
| all | ROOT, Rivet, Pythia8 and the module programs pass C++ types across libraries: mixed standards are ABI trouble | one standard for everything: `CXXFLAGS="-O2 -std=c++17"` for every build, and `CMAKE_CXX_STANDARD=17` |
| all | the build of one package needs the ones before it on its paths | the venv first on `PATH`, and every install on `PATH`, `LD_LIBRARY_PATH` and `PYTHONPATH`, as `setup.sh` gives them later (`settings.toml [env]` for the rest) |
| HepMC3 | `pyHepMC3` built but not installed; `GenEvent` missing from it | `-DHEPMC3_Python_SITEARCH<XY>=<venv site-packages>` (`HEPMC3_PYTHON_INSTALL_DIR` is ignored), and `-fno-lto`: LTO strips the pybind11 symbols |
| FastJet | several Rivets in one process (InprocJets, `rivet_threads`) cluster SISCone jets with one shared random state: other jets, or a FastJet internal error (L16, L29) | `fastjet.patch`: `utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch`, the state per thread; one thread draws exactly what it drew before |
| fjcontrib | `make install` gives only static contrib libraries | `make fragile-shared-install` as well: `libfastjetcontribfragile.so`, as the lab PC has it |
| ROOT | 6.40.00's `rootcling_stage1` fails to link (`clang::CodeGenerator::GetModule()`) | pinned to 6.40.04, which fixes that regression |
| ROOT | parallel compilation of its LLVM/Cling OOM-kills `cc1plus`, and the truncated objects then fail later links with errors that look unrelated | `root_jobs`: one job per 3 GB of RAM (5 on 15 GB); every other package at `jobs` |
| ROOT | `-DPYTHON_EXECUTABLE`, `-Dglew`, `-Dpython3` are ignored by 6.40 | `-DPython3_EXECUTABLE=<venv>` (FindPython3), `-Dpyroot=ON` |
| ROOT | an external xrootd 6.x is untested against ROOT 6.40, and ROOT does not read `XROOTD_ROOT_DIR` | `-Dxrootd=ON -Dbuiltin_xrootd=ON`, `-Ddavix=OFF` |
| ROOT | the features the framework and the lab PC use | `mathmore roofit tmva fftw3 sqlite xml gdml http imt ssl vdt` on; `x11 opengl webgui asimage` follow `graphics` |
| Pythia8 | its Rivet and ROOT plugins exist only if it is built after them | after ROOT and Rivet; `optional` adds `--with-root --with-rivet` when they are there |
| ThePEG | `--with-hepmc` alone looks for HepMC2 | `--with-hepmcversion=3` |
| Herwig | `make install` writes `HerwigDefaults.rpo`, which needs CT14lo/CT14nlo | `lhapdf install CT14lo CT14nlo` first, `LHAPDF_DATA_PATH` set |
| Delphes | DelphesPythia8 is built only when Pythia8 is found | `PYTHIA8=<install>` in its environment, `-DROOT_DIR=<root>/cmake` |
| Sherpa | its `_DIR` options are spelled per package (`HepMC3_DIR`, `RIVET_DIR`, `FASTJET_DIR`, `LHAPDF_DIR`) | as Sherpa spells them; `HepMC3_DIR` is the CMake config directory |
| Whizard | HepMC3 is `--enable-hepmc --with-hepmc` (no `*hepmc3` options); O'Mega needs OCaml | so; `ocaml ocaml-findlib libgc-dev` are system packages |
| MadGraph | not built: a tree that finds LHAPDF and Pythia8 through its configuration file | unpacked into `install/madgraph`; `lhapdf`, `pythia8_path` and `automatic_html_opening = False` set |
| Python | pip wheels of FastJet or HepMC3 do not match the stack's symbols | every compiled HEP library is built here; pip installs only pure-Python and ML packages |

---

## 4. System packages

With `system = true` (the default), the run first installs `settings.toml`'s `apt_packages` with
apt-get, through sudo when not root (its password is asked before anything is logged), and stamps
`system`. The list is grouped there by what needs each package: the build tools, Python, ROOT,
ThePEG and Herwig, LHAPDF, Sherpa, Whizard (OCaml), Geant4, and the framework itself (toml++,
zstd, zlib for Paint, App_Pythia and the module kit; pdflatex for sheet figures).

On a distribution without apt, install the same packages under its names and run with
`system=false`.

---

## 5. After the build

```bash
source ~/HEP/setup.sh                 # or $prefix/setup.sh
hep status --stack                    # each package's version
hep build && make test                # the framework against the new stack
```

**What is checked.**
- `tests/runner/test_stack_build.py`: the plans (order, added needs, overrides, `--config`,
  refusals) and the full dry run, which must be valid bash and write nothing.
- For real: FastJet with its patch and fjcontrib, offline from local tarballs, both through the
  engine and through its `--dry-run` script.
- Not yet: the whole stack in one run, the Dockerfile, and the downloader against the live sites.
  The full stack was built on the lab PC by hand, with these flags. Expect the first full run on a
  new machine to need small fixes, which the log names.

**Known caveats.**
- **MadGraph and ONNX Runtime** rename releases often. When a download 404s, set `madgraph.url` or
  `onnxruntime.url` from their download pages.
- **Delphes 3.5.1 and ROOT 6.40** work together on the lab PC, but upstream has not released
  against 6.40. A dictionary (`rootcling`) failure there is Delphes', not this build's.
- **Geant4's datasets** need network during its build. A timeout is retried by rerunning.
- **Rebuilt binaries change identities.** A point that ran with the old App_Pythia, App_yd2rt or a
  Rivet plugin reruns once the framework is rebuilt against a new stack (06 §27).
- **Not built here:** CMSSW and Key4hep, which come from CVMFS in an el9 apptainer container. Never
  mix their environment with this stack's in one shell. A standalone xrootd is not built either:
  ROOT builds its own.
