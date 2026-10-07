# The HEP stack: building it on another machine

`build_stack.sh` builds, from source, the software stack the framework runs on: the one the lab PC
has in `~/HEP` (Ubuntu 24.04, GCC 13), with the same versions, the same features and the fixes its
build needed. It runs on a Linux machine or in a Docker container. Every choice is a variable.

| File | Is |
|---|---|
| [build_stack.sh](build_stack.sh) | the build: system packages, then each package in order, stamped, logged, resumable |
| [stack.conf](stack.conf) | every setting with its default, for `--config` |
| [Dockerfile](Dockerfile) (+ `Dockerfile.dockerignore`) | the same build in an Ubuntu 24.04 image |

The framework's own view of the stack (each library's flags and version) is
`utils/Env/stack.toml`; the shell environment is `utils/Env/hep_env.sh`
([06 §15.3](../06_Internals.md#153-the-flag-cache)).

---

## 1. Quick start

**On a machine** (sudo for the system packages, or `SYSTEM_DEPS=skip` if they are installed):

```bash
bash docs/stack/build_stack.sh --list                 # what it would build, and what is built already
bash docs/stack/build_stack.sh --dry-run              # every command, nothing run
bash docs/stack/build_stack.sh                        # the core stack into ~/HEP (hours: ROOT alone is 1–2 h)
bash docs/stack/build_stack.sh PACKAGES=all           # and Sherpa, MadGraph, Whizard, ONNX Runtime, Geant4
source ~/HEP/setup.sh                                 # then, in this repository: hep build
```

A setting is given as `VAR=value` (`HEP_PREFIX=/opt/hep JOBS=8`), from the environment, or from a
file (`--config my.conf`, a copy of `stack.conf`); a command-line value wins.

**In Docker** (from the repository root):

```bash
docker build -f docs/stack/Dockerfile -t hep-stack .
docker build -f docs/stack/Dockerfile --build-arg PACKAGES=all --build-arg ROOT_JOBS=2 -t hep-stack:all .
docker run --rm -it -v "$PWD":/work -w /work hep-stack
```

The image is headless by default (`ROOT_GRAPHICS=OFF`, `GEANT4_X11=OFF`); its stack is in
`/opt/hep`, loaded by every shell.

**Resuming.** Each package that finishes is stamped (`$HEP_PREFIX/.stamps/<package>-<version>`) and
skipped next time, so the same command resumes after a failure, a reboot or a Ctrl-C. A changed
version is a new stamp, so it builds; `FORCE="root"` rebuilds a package anyway. A tarball already in
`$HEP_PREFIX/src` is used as it is, so a machine without network can build from copied tarballs.

**Logs.** Each package writes `$HEP_PREFIX/logs/<package>.log`. A failure stops the build at once,
prints the last 40 lines and names the log; nothing after it is built.

---

## 2. The packages

In build order. `core` is the first group; `all` adds the second. `PACKAGES` may also list packages
by name. Each package's needs are checked before anything runs: a package needs what it builds
against either installed or built earlier in the same run.

| Package | Version | Needs | Built with | Why |
|---|---|---|---|---|
| `venv` | your `python3` | — | a venv in `$HEP_PREFIX/.venv`, `PYTHON_PACKAGES` | every Python binding lands here; the framework's `tomli_w`, `rich`, `uproot`, Pillow, matplotlib, pytest |
| `lhapdf` | 6.5.6 | venv | autotools, `PYTHON=<venv>` | PDFs for Pythia8, Herwig, Sherpa, Whizard, MadGraph |
| `herwig_pdfs` | CT14lo, CT14nlo | lhapdf | `lhapdf install` | Herwig's default settings read them: without them its `make install` cannot write its repository (L15) |
| `hepmc3` | 3.3.1 | venv | CMake | the event format between the tools |
| `fastjet` | 3.5.0 + fjcontrib 1.104 | — | autotools, `--enable-allcxxplugins`; the SISCone patch | jets for Rivet, Pythia8, Sherpa, Whizard and module programs |
| `root` | 6.40.04 | venv | CMake, `builtin_xrootd`, few jobs | App_yd2rt, Paint, Delphes, module programs |
| `yoda` | 2.1.3 | venv | autotools | Rivet's histograms; the plot backends |
| `rivet` | 4.1.3 | venv, hepmc3, yoda, fastjet | autotools | the analyses |
| `pythia8` | 8.317 | venv, lhapdf, hepmc3, fastjet (root, rivet when there) | its configure | App_Pythia, InprocJets |
| `herwig` | 7.3.0 + ThePEG 2.3.0 | lhapdf, herwig_pdfs, hepmc3, fastjet | autotools, both into `install/herwig7` | the `herwig` tool |
| `delphes` | 3.5.1 | root | CMake | the `delphes` tool |
| `pdfsets` | `PDF_SETS` | lhapdf | `lhapdf install` | the sets the configs and the tests use (the lab PC's 21) |
| `sherpa` | 3.0.5 | hepmc3, lhapdf, rivet, fastjet | CMake | the `sherpa` tool |
| `madgraph` | 3.7.3 | lhapdf, pythia8 | unpacked, configured | the `madgraph` tool |
| `whizard` | 3.1.8 | hepmc3, fastjet, lhapdf, pythia8 | autotools, OCaml | the `whizard` tool |
| `onnxruntime` | 1.29.0 | — | the released binary (x64 or aarch64) | `// requires: onnx` |
| `geant4` | 11.4.2 | — | CMake, MT, GDML, datasets | `// requires: geant4` |
| `pyextras` | `PYTHON_EXTRAS` | venv | pip | the analysis and ML packages (scikit-HEP, xgboost, pyhf, onnx) |
| `xrootd` | 6.1.1 | — | CMake | not in `all`: a standalone client/server only, since ROOT builds its own |

The installs go to `$HEP_PREFIX/install/<dir>` with the directory names `utils/Env/hep_env.sh`
expects: `LHAPDF hepmc3 fastjet root yoda rivet pythia8 herwig7 delphes sherpa madgraph whizard
onnxruntime geant4`.

---

## 3. What makes the builds work together

Each of these was hit on the lab PC; the script does what is in the right column.

| Package | Problem | What the script does |
|---|---|---|
| all | ROOT, Rivet, Pythia8 and the module programs pass C++ types across libraries: mixed standards are ABI trouble | one standard for everything, `CXX_STD=17` (`-std=c++17`, `CMAKE_CXX_STANDARD=17`) |
| HepMC3 | `pyHepMC3` built but not installed; `GenEvent` missing from it | `-DHEPMC3_Python_SITEARCH<XY>=<venv site-packages>` (`HEPMC3_PYTHON_INSTALL_DIR` is ignored), and `-fno-lto`: LTO strips the pybind11 symbols |
| FastJet | several Rivets in one process (InprocJets, `rivet_threads`) cluster SISCone jets with one shared random state: other jets, or a FastJet internal error (L16, L29) | applies `utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch` (`FASTJET_SISCONE_PATCH=1`): the state is per thread, and one thread draws exactly what it drew before |
| fjcontrib | `make install` gives only static contrib libraries | `make fragile-shared-install` as well: `libfastjetcontribfragile.so`, as the lab PC has it, for programs that link the contribs dynamically |
| ROOT | 6.40.00's `rootcling_stage1` fails to link (`clang::CodeGenerator::GetModule()`) | pinned to 6.40.04, which fixes that regression |
| ROOT | parallel compilation of its LLVM/Cling OOM-kills `cc1plus`, and the truncated objects then fail later links with errors that look unrelated | `ROOT_JOBS=auto`: one job per 3 GB of RAM (5 on 15 GB), every other package at `JOBS` |
| ROOT | `-DPYTHON_EXECUTABLE`, `-Dglew`, `-Dpython3` are ignored by 6.40 | `-DPython3_EXECUTABLE=<venv>` (FindPython3), `-Dpyroot=ON` |
| ROOT | an external xrootd 6.x is untested against ROOT 6.40, and ROOT does not read `XROOTD_ROOT_DIR` | `-Dxrootd=ON -Dbuiltin_xrootd=ON`, `-Ddavix=OFF` |
| ROOT | the features the framework and the lab PC use | `mathmore roofit tmva fftw3 sqlite xml gdml http imt ssl vdt` on; `x11 opengl webgui asimage` follow `ROOT_GRAPHICS` |
| Pythia8 | its Rivet and ROOT plugins exist only if it is built after them | built after ROOT and Rivet, `--with-root --with-rivet` |
| ThePEG | `--with-hepmc` alone looks for HepMC2 | `--with-hepmcversion=3` |
| Herwig | `make install` writes `HerwigDefaults.rpo`, which needs CT14lo/CT14nlo | `herwig_pdfs` first, and `LHAPDF_DATA_PATH` set for the install |
| Delphes | DelphesPythia8 is built only when Pythia8 is found | `PYTHIA8=<install>` in the environment, `-DROOT_DIR=<root>/cmake` |
| Sherpa | its `_DIR` options are spelled per package (`HepMC3_DIR`, `RIVET_DIR`, `FASTJET_DIR`, `LHAPDF_DIR`) | as Sherpa spells them; `HepMC3_DIR` is the CMake config directory |
| Whizard | HepMC3 is `--enable-hepmc --with-hepmc` (no `*hepmc3` options); O'Mega needs OCaml | so; `ocaml ocaml-findlib libgc-dev` are system packages |
| MadGraph | not built: a tree that finds LHAPDF and Pythia8 through its configuration file | copied to `install/madgraph`, `lhapdf`, `pythia8_path` and `automatic_html_opening = False` set |
| Python | pip wheels of FastJet or HepMC3 do not match the stack's symbols | every compiled HEP library is built here; pip installs only pure-Python and ML packages |

---

## 4. System packages

`SYSTEM_DEPS=auto` installs them with apt (Ubuntu, Debian) or dnf (Fedora, RHEL family), through
sudo when not root. The apt list, the reference:

- **build:** `build-essential gfortran cmake git wget curl patch rsync pkg-config libtool autoconf automake`
- **Python:** `python3-venv python3-dev`
- **ROOT:** `libxml2-dev libfftw3-dev libsqlite3-dev libx11-dev libxpm-dev libxft-dev libxext-dev
  liblzma-dev libpcre3-dev libglew-dev libgif-dev libftgl-dev libgraphviz-dev libcurl4-openssl-dev
  uuid-dev libkrb5-dev libssl-dev`
- **ThePEG, Herwig:** `libgsl-dev libboost-all-dev`
- **LHAPDF:** `libyaml-cpp-dev`
- **Sherpa:** `libzip-dev libbz2-dev`
- **Whizard:** `ocaml ocaml-findlib libgc-dev`
- **ONNX Runtime:** `libgomp1`
- **Geant4:** `libxerces-c-dev libgl1-mesa-dev libglu1-mesa-dev libxmu-dev libxi-dev`
- **the framework itself:** `libtomlplusplus-dev libzstd-dev zlib1g-dev` (Paint, App_Pythia, the
  module kit) and `texlive-latex-base texlive-latex-extra` (pdflatex, for sheet figures)

The dnf list has the same packages under Fedora's names. It is untested: on another distribution,
read the failure, install what is missing, and rerun with `SYSTEM_DEPS=skip`.

---

## 5. Settings

[stack.conf](stack.conf) lists every one with its default. The ones most often changed:

| Setting | Default | |
|---|---|---|
| `HEP_PREFIX` | `$HOME/HEP` | where everything goes |
| `PACKAGES` | `core` | `core`, `all`, or names |
| `JOBS` / `ROOT_JOBS` | `nproc` / `auto` | build parallelism |
| `<NAME>_VERSION`, `<NAME>_URL` | the lab PC's | a version, and where its tarball is |
| `ROOT_GRAPHICS`, `GEANT4_X11` | `ON` | graphics, for a desktop; `OFF` for a server or container |
| `GEANT4_DATA` | `ON` | Geant4's datasets, ~4 GB downloaded during its build |
| `PDF_SETS` | the lab PC's 21 | what `pdfsets` installs |
| `PYTHON_PACKAGES`, `PYTHON_EXTRAS` | see stack.conf | the venv's packages |
| `SETUP_STYLE` | `auto` | `repo`: `setup.sh` sources this repository's `utils/Env/hep_env.sh` (the lab PC's way, with `hep_status`, `quit`, …); `standalone`: the paths, the venv and the data variables only |
| `SYSTEM_DEPS`, `SUDO` | `auto` | the OS packages, and how they are installed |
| `DRY_RUN`, `FORCE`, `KEEP_BUILD` | `0`, none, `1` | look first; rebuild some; keep or remove build trees |

---

## 6. After the build

```bash
source ~/HEP/setup.sh                 # or $HEP_PREFIX/setup.sh
hep status --stack                    # each package's version (SETUP_STYLE=repo)
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
- **Geant4's datasets** need network during its `make`. A timeout is retried by rerunning.
- **Rebuilt binaries change identities.** A point that ran with the old App_Pythia, App_yd2rt or a
  Rivet plugin reruns once the framework is rebuilt against a new stack (06 §27).
- **Not built here:** CMSSW and Key4hep, which come from CVMFS in an el9 apptainer container. Never
  mix their environment with this stack's in one shell.
