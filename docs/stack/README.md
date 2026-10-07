# The HEP stack: building it on another machine

`build_stack.sh` builds, from source, the software stack the framework runs on: the one the lab PC
has in `~/HEP` (Ubuntu 24.04, GCC 13), with the same versions, the same features and the fixes its
build needed. It runs on a Linux machine with apt, or in a Docker container.

| File | Is |
|---|---|
| [build_stack.sh](build_stack.sh) | the build: its settings at the top, then one short function per package |
| [Dockerfile](Dockerfile) (+ `Dockerfile.dockerignore`) | the same build in an Ubuntu 24.04 image |

The framework's own view of the stack (each library's flags and version) is
`utils/Env/stack.toml`; the shell environment is `utils/Env/hep_env.sh`
([06 §15.3](../06_Internals.md#153-the-flag-cache)).

---

## 1. Quick start

**On a machine** (sudo for the system packages, or `SYSTEM_DEPS=0` if they are installed):

```bash
bash docs/stack/build_stack.sh --dry-run              # every command, nothing run
bash docs/stack/build_stack.sh                        # the core stack into ~/HEP (hours: ROOT alone is 1–2 h)
bash docs/stack/build_stack.sh PACKAGES=all           # and Sherpa, MadGraph, Whizard, ONNX Runtime, Geant4
source ~/HEP/setup.sh                                 # then, in this repository: hep build
```

A setting is any variable at the top of the script, given as `VAR=value` on the command line or in
the environment (`HEP_PREFIX=/opt/hep JOBS=8`).

**In Docker** (from the repository root):

```bash
docker build -f docs/stack/Dockerfile -t hep-stack .
docker build -f docs/stack/Dockerfile --build-arg PACKAGES=all --build-arg ROOT_JOBS=2 -t hep-stack:all .
docker run --rm -it -v "$PWD":/work -w /work hep-stack
```

The image is headless (`GRAPHICS=OFF`) and keeps the stack in `/opt/hep`. Its environment is the
repository's `hep_env.sh`, so a shell loads it when the repository is mounted at `/work`.

**Resuming.** A step that finishes is stamped (`$HEP_PREFIX/.stamps/<step>-<version>`) and skipped
next time, so the same command resumes after a failure, a reboot or a Ctrl-C. A changed version is a
new stamp, so it builds; delete a stamp to redo its step. A step unpacks its sources afresh each
time, so a half-done build never leaks into the next try. A tarball already in `$HEP_PREFIX/src` is
used as it is, so a machine without network can build from copied tarballs.

**Logs.** Each step writes `$HEP_PREFIX/logs/<step>.log`. A failure stops the build at once, prints
the last 30 lines and names the log.

**setup.sh.** At the end the script writes `$HEP_PREFIX/setup.sh`, the lab PC's stub: it sets `HEP`,
`HEP_INSTALL` and `HEKIT_ROOT` (this checkout) and sources `utils/Env/hep_env.sh`. A `setup.sh`
already there is kept.

---

## 2. The packages

In build order. `core` is the first group; `all` adds the second. `PACKAGES` may also name packages,
which are built in this order whatever order they are given in. A package needs what it builds
against: installed already, or named in the same run.

| Package | Version | Built with | For |
|---|---|---|---|
| `python` | your `python3` | a venv in `$HEP_PREFIX/.venv`, `PYTHON_PACKAGES` | every Python binding; the framework's `tomli_w`, `rich`, `uproot`, Pillow, matplotlib, pytest |
| `lhapdf` | 6.5.6 | autotools | PDFs for Pythia8, Herwig, Sherpa, Whizard, MadGraph |
| `hepmc3` | 3.3.1 | CMake | the event format between the tools |
| `fastjet` | 3.5.0 + fjcontrib 1.104 | autotools, `--enable-allcxxplugins`, the SISCone patch | jets for Rivet, Pythia8, Sherpa, Whizard and module programs |
| `root` | 6.40.04 | CMake, `builtin_xrootd`, `ROOT_JOBS` | App_yd2rt, Paint, Delphes, module programs |
| `yoda` | 2.1.3 | autotools | Rivet's histograms; the plot backends |
| `rivet` | 4.1.3 | autotools | the analyses |
| `pythia8` | 8.317 | its configure, with ROOT's and Rivet's plugins | App_Pythia, InprocJets |
| `herwig` | 7.3.0 + ThePEG 2.3.0 | autotools, both into `install/herwig7` | the `herwig` tool |
| `delphes` | 3.5.1 | CMake | the `delphes` tool |
| `pdfsets` | `PDF_SETS` | `lhapdf install` | the sets the configs and the tests use (the lab PC's 21) |
| `sherpa` | 3.0.5 | CMake | the `sherpa` tool |
| `madgraph` | 3.7.3 | unpacked into `install/madgraph`, configured | the `madgraph` tool |
| `whizard` | 3.1.8 | autotools, OCaml | the `whizard` tool |
| `onnxruntime` | 1.29.0 | the released binary (x64 or aarch64) | `// requires: onnx` |
| `geant4` | 11.4.2 | CMake, MT, GDML, datasets | `// requires: geant4` |

The installs go to `$HEP_PREFIX/install/<dir>`, under the directory names `hep_env.sh` expects:
`LHAPDF hepmc3 fastjet root yoda rivet pythia8 herwig7 delphes sherpa madgraph whizard onnxruntime
geant4`. More Python packages (scipy, pandas, scikit-learn, pyhf, …) go into `PYTHON_PACKAGES`.

---

## 3. What makes the builds work together

Each of these was hit on the lab PC; the script does what is in the right column.

| Package | Problem | What the script does |
|---|---|---|
| all | ROOT, Rivet, Pythia8 and the module programs pass C++ types across libraries: mixed standards are ABI trouble | one standard for everything: `CXXFLAGS="-O2 -std=c++17"` for every build, and `CMAKE_CXX_STANDARD=17` |
| all | the build of one package needs the ones before it on its paths | the venv first on `PATH`, and every install on `PATH`, `LD_LIBRARY_PATH` and `PYTHONPATH`, as `setup.sh` gives them later |
| HepMC3 | `pyHepMC3` built but not installed; `GenEvent` missing from it | `-DHEPMC3_Python_SITEARCH<XY>=<venv site-packages>` (`HEPMC3_PYTHON_INSTALL_DIR` is ignored), and `-fno-lto`: LTO strips the pybind11 symbols |
| FastJet | several Rivets in one process (InprocJets, `rivet_threads`) cluster SISCone jets with one shared random state: other jets, or a FastJet internal error (L16, L29) | applies `utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch` (`FASTJET_PATCH`): the state is per thread, and one thread draws exactly what it drew before |
| fjcontrib | `make install` gives only static contrib libraries | `make fragile-shared-install` as well: `libfastjetcontribfragile.so`, as the lab PC has it |
| ROOT | 6.40.00's `rootcling_stage1` fails to link (`clang::CodeGenerator::GetModule()`) | pinned to 6.40.04, which fixes that regression |
| ROOT | parallel compilation of its LLVM/Cling OOM-kills `cc1plus`, and the truncated objects then fail later links with errors that look unrelated | `ROOT_JOBS`: one job per 3 GB of RAM (5 on 15 GB); every other package at `JOBS` |
| ROOT | `-DPYTHON_EXECUTABLE`, `-Dglew`, `-Dpython3` are ignored by 6.40 | `-DPython3_EXECUTABLE=<venv>` (FindPython3), `-Dpyroot=ON` |
| ROOT | an external xrootd 6.x is untested against ROOT 6.40, and ROOT does not read `XROOTD_ROOT_DIR` | `-Dxrootd=ON -Dbuiltin_xrootd=ON`, `-Ddavix=OFF` |
| ROOT | the features the framework and the lab PC use | `mathmore roofit tmva fftw3 sqlite xml gdml http imt ssl vdt` on; `x11 opengl webgui asimage` follow `GRAPHICS` |
| Pythia8 | its Rivet and ROOT plugins exist only if it is built after them | built after ROOT and Rivet, `--with-root --with-rivet` when they are there |
| ThePEG | `--with-hepmc` alone looks for HepMC2 | `--with-hepmcversion=3` |
| Herwig | `make install` writes `HerwigDefaults.rpo`, which needs CT14lo/CT14nlo | `lhapdf install CT14lo CT14nlo` first, `LHAPDF_DATA_PATH` set |
| Delphes | DelphesPythia8 is built only when Pythia8 is found | `PYTHIA8=<install>` in the environment, `-DROOT_DIR=<root>/cmake` |
| Sherpa | its `_DIR` options are spelled per package (`HepMC3_DIR`, `RIVET_DIR`, `FASTJET_DIR`, `LHAPDF_DIR`) | as Sherpa spells them; `HepMC3_DIR` is the CMake config directory |
| Whizard | HepMC3 is `--enable-hepmc --with-hepmc` (no `*hepmc3` options); O'Mega needs OCaml | so; `ocaml ocaml-findlib libgc-dev` are system packages |
| MadGraph | not built: a tree that finds LHAPDF and Pythia8 through its configuration file | unpacked into `install/madgraph`; `lhapdf`, `pythia8_path` and `automatic_html_opening = False` set |
| Python | pip wheels of FastJet or HepMC3 do not match the stack's symbols | every compiled HEP library is built here; pip installs only pure-Python and ML packages |

---

## 4. System packages

The `system` step (`SYSTEM_DEPS=1`) installs `APT_PACKAGES` with apt-get, through sudo when not
root. The list, by what needs it:

- **build:** `build-essential gfortran cmake git curl ca-certificates patch pkg-config libtool autoconf automake`
- **Python:** `python3-venv python3-dev`
- **ROOT:** `libxml2-dev libfftw3-dev libsqlite3-dev libx11-dev libxpm-dev libxft-dev libxext-dev
  liblzma-dev libpcre3-dev libglew-dev libgif-dev libftgl-dev libgraphviz-dev libcurl4-openssl-dev
  uuid-dev libkrb5-dev libssl-dev`
- **ThePEG, Herwig:** `libgsl-dev libboost-all-dev`
- **LHAPDF:** `libyaml-cpp-dev`
- **Sherpa:** `libzip-dev libbz2-dev`
- **Whizard:** `ocaml ocaml-findlib libgc-dev`
- **Geant4:** `libxerces-c-dev libgl1-mesa-dev libglu1-mesa-dev libxmu-dev libxi-dev`
- **the framework itself:** `libtomlplusplus-dev libzstd-dev zlib1g-dev` (Paint, App_Pythia, the
  module kit) and `texlive-latex-base texlive-latex-extra` (pdflatex, for sheet figures)

On a distribution without apt, install the same packages under its names and run with
`SYSTEM_DEPS=0`.

---

## 5. Settings

All are at the top of the script, each with its default and a comment. The ones most often changed:

| Setting | Default | |
|---|---|---|
| `HEP_PREFIX` | `$HOME/HEP` | where everything goes |
| `PACKAGES` | `core` | `core`, `all`, or names |
| `JOBS` / `ROOT_JOBS` | `nproc` / RAM ÷ 3 GB | build parallelism |
| `<NAME>_VERSION`, `<NAME>_URL` | the lab PC's | a version, and where its tarball is (the table in the script; `$v` in a URL is the version) |
| `GRAPHICS` | `ON` | ROOT's and Geant4's graphics, for a desktop; `OFF` for a server or container |
| `GEANT4_DATA` | `ON` | Geant4's datasets, ~4 GB downloaded during its build |
| `ROOT_EXTRA` | none | more ROOT CMake arguments |
| `PDF_SETS`, `PYTHON_PACKAGES` | the lab PC's | what `pdfsets` and `python` install |
| `HEKIT_ROOT` | this checkout | the repository `setup.sh` loads `hep_env.sh` from |
| `SYSTEM_DEPS`, `DRY_RUN` | `1`, `0` | the apt step; look first |

---

## 6. After the build

```bash
source ~/HEP/setup.sh                 # or $HEP_PREFIX/setup.sh
hep status --stack                    # each package's version
hep build && make test                # the framework against the new stack
```

**What is not checked here.**
- The script ran end to end in a dry run, and for real for FastJet with its patch and fjcontrib,
  offline from local tarballs.
- The full stack was built on the lab PC by hand, with these flags; the script has not yet built the
  whole stack in one go, nor has the Dockerfile been built.
- Expect the first full run on a new machine to need small fixes, which the log names.

**Known caveats.**
- **MadGraph and ONNX Runtime** rename releases often. When a download 404s, set `MADGRAPH_URL` or
  `ONNXRUNTIME_URL` from their download pages.
- **Delphes 3.5.1 and ROOT 6.40** work together on the lab PC, but upstream has not released
  against 6.40. A dictionary (`rootcling`) failure there is Delphes', not this script's.
- **Geant4's datasets** need network during its build. A timeout is retried by rerunning.
- **Rebuilt binaries change identities.** A point that ran with the old App_Pythia, App_yd2rt or a
  Rivet plugin reruns once the framework is rebuilt against a new stack (06 §27).
- **Not built here:** CMSSW and Key4hep, which come from CVMFS in an el9 apptainer container. Never
  mix their environment with this stack's in one shell. A standalone xrootd is not built either:
  ROOT builds its own.
