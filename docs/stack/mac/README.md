# The HEP stack on macOS

The same build as on Linux ([../README.md](../README.md)), with Homebrew for the system packages and
Apple's clang as the compiler. On Apple Silicon or Intel. The build is `build_stack.py` with one
overlay, `mac.toml`; nothing in `packages.toml` is copied.

| File | Is |
|---|---|
| [Brewfile](Brewfile) | what the stack needs from Homebrew (the macOS counterpart of `apt_packages`) |
| [mac.toml](mac.toml) | what the build does differently on macOS, as a `--config` overlay |
| [build.sh](build.sh) | checks the machine, runs `brew bundle`, then `build_stack.py --config mac.toml` |
| [launch.sh](launch.sh) | a bash with the stack loaded, or one command in it, from any shell (zsh included) |

---

## 1. By hand, once

0. **A native terminal.** On an Apple Silicon Mac, `uname -m` must print `arm64`: a Terminal set to
   "Open using Rosetta" builds x86_64 against an arm64 Homebrew, and `build.sh` refuses it.
1. **Xcode's command-line tools** (the compiler, `make`, the SDK; about 1 GB; full Xcode is not
   needed):
   ```bash
   xcode-select --install
   ```
   A dialog asks to install them. When it is done, `xcode-select -p` prints a path.
2. **Homebrew**, from [brew.sh](https://brew.sh): paste its install line into Terminal (it asks for
   your password), then run the two `echo … >> ~/.zprofile` and `eval …` lines it prints at the end,
   so new terminals have `brew`. Check in a new terminal:
   ```bash
   brew --version
   ```
3. **This repository**, if it is not on the Mac yet:
   ```bash
   git clone <the High-Energy repository's URL> ~/Github/High-Energy
   cd ~/Github/High-Energy
   ```
4. **Optional: pdflatex** for the sheet figures (about 100 MB; asks for your password):
   ```bash
   brew install --cask basictex
   ```
   Or uncomment `cask "basictex"` in the Brewfile.
5. **Disk and time:** about 20 GB free; the core stack takes hours (ROOT alone 1–2 h). Keep the Mac
   plugged in; `caffeinate` below keeps it awake.

---

## 2. Build

From the repository's root:

```bash
bash docs/stack/mac/build.sh --dry-run > ~/hep-build.sh     # look first: the whole build as bash; nothing installed
caffeinate -i bash docs/stack/mac/build.sh                  # Homebrew's packages, then the core stack into ~/HEP
caffeinate -i bash docs/stack/mac/build.sh packages=all     # and Sherpa, MadGraph, Whizard, ONNX Runtime, Geant4
```

`build.sh` checks the machine (macOS, Xcode's tools, not Rosetta, Homebrew), runs `brew bundle`
(skip it with `BREW_BUNDLE=0`), puts GNU make, sed and coreutils first on `PATH`, picks Homebrew's
Python 3.11+, and runs `build_stack.py` with `mac.toml`. Every `build_stack.py` argument passes
through and wins over `mac.toml`: `cores=8`, `prefix=/opt/hep`, `root.release=6.40.06`,
`packages="rivet pythia8"`. Stamps, logs (`~/HEP/logs/<package>.log`), resuming and `--list` are as
on Linux ([../README.md §1](../README.md#1-quick-start)).

---

## 3. Launch

```bash
docs/stack/mac/launch.sh                       # a bash with ~/HEP/setup.sh loaded (hep_status shows the stack)
docs/stack/mac/launch.sh root -l               # one command in that environment
HEP=/opt/hep docs/stack/mac/launch.sh          # another prefix
```

The environment (`utils/Env/hep_env.sh`) is bash, and macOS's login shell is zsh, with a bash 3.2:
`launch.sh` runs Homebrew's bash 5 with your `~/.bashrc` and `setup.sh`. Inside a bash already,
`source ~/HEP/setup.sh` does the same. For a zsh shortcut, in `~/.zshrc`:

```bash
alias load_hep="$HOME/Github/High-Energy/docs/stack/mac/launch.sh"
```

Then, in the launched shell, the framework against the new stack:

```bash
hep build && make test
```

---

## 4. What mac.toml changes

| What | Linux | macOS |
|---|---|---|
| system packages | `apt-get install apt_packages` | `system = false`; `brew bundle` (Brewfile), by build.sh |
| compiler search paths | the system's | Homebrew's: `CPPFLAGS`, `LDFLAGS`, `CMAKE_PREFIX_PATH`, `BOOST_ROOT` (ThePEG and Herwig find Boost and GSL there) |
| OpenSSL | the system's | Homebrew's keg-only `openssl@3`: `OPENSSL_ROOT_DIR` for ROOT and its builtin xrootd |
| ROOT's graphics | X11, OpenGL, web GUI, AfterImage | `graphics = "OFF"` (no X11), then `root.extra`: Cocoa, OpenGL, web GUI, AfterImage |
| Geant4's viewer | OpenGL/X11 | none (`graphics = "OFF"`) |
| libraries found by | `LD_LIBRARY_PATH` | absolute install names: libtool's own (LHAPDF, YODA, Rivet, ThePEG, Herwig, Whizard) and `CMAKE_INSTALL_NAME_DIR` for HepMC3, Delphes, Geant4; rpaths from `root-config`, `fastjet-config`, `pythia8-config`; `DYLD_LIBRARY_PATH` as well |
| fjcontrib's shared library | `libfastjetcontribfragile.so` | `.dylib` (the `{dylib}` placeholder) |
| ONNX Runtime | `onnxruntime-linux-<arch>` | `onnxruntime-osx-<arm64 or x86_64>` |
| setup.sh | the stub | the stub, then `DYLD_LIBRARY_PATH` and GNU make, sed, coreutils first on `PATH` (`setup_extra`) |

---

## 5. Known limits

- **Not yet run on a Mac.** The files follow the Linux build, which the lab PC proved, and macOS's
  conventions. Their dry run is tested (`tests/runner/test_stack_build.py`); the real build is not.
  Expect the first run to need small fixes: the log names them, and a fix is a `mac.toml` line.
- **`hep run` does not start on macOS yet.** Its watch socket (`utils/Env/runner/events.py`) uses
  Linux's abstract socket namespace, which macOS does not have. The stack, `hep build`, `make`, ROOT,
  Rivet and the generators are not affected.
- **DYLD_LIBRARY_PATH** is dropped by macOS (System Integrity Protection) whenever one of Apple's own
  programs starts, `/usr/bin/env` and `/bin/sh` among them, and so for most scripts. The stack does
  not rely on it: its libraries carry absolute install names or rpaths (the table above).
- **No Homebrew HEP formulae alongside:** Homebrew's own `root`, `hepmc3`, `lhapdf`, `pythia`,
  `yoda`, `rivet` or `fastjet` would sit on the build's search paths ahead of the stack's. Remove
  them first (`brew uninstall root`, …).
- `hep_status` shows ONNX Runtime as missing on macOS (it looks for `libonnxruntime.so`); the library
  is there as `.dylib`.
