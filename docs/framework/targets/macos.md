# Target: macOS (Homebrew)

A Mac, Apple Silicon or Intel. The recipes are `platforms/mac/`: a `Brewfile`, the `mac.toml` overlay,
`build.sh` and `launch.sh`, moved from `docs/stack/mac/` (platforms/mac/README.md has every step by
hand). Only what differs from the phase files is here (D11).

## Prerequisites (P0 S1)

- **Xcode's command-line tools:** `xcode-select -p` prints a path.
- **Homebrew** (`brew --version`). A native terminal: on Apple Silicon `uname -m` is `arm64`, never
  Rosetta.
- **Homebrew's bash 5** for `hep_env.sh` (macOS's own bash is 3.2), and Python ≥ 3.11 from
  Homebrew.
- 60 GB free.

## System packages (P2 S1)

- `brew bundle --file=$HEP/platforms/mac/Brewfile` replaces apt. It includes `pandoc` and
  `poppler` for decks.
- No sudo, so no gate, but it is a download: ask with the others.
- Homebrew's own HEP formulae (`root`, `hepmc3`, `lhapdf`, `pythia`, `yoda`, `rivet`, `fastjet`)
  must not be installed (platforms/mac/README.md §5). A gate if they are.

## Overlay and launching

- **The build:** `bash $HEP/platforms/mac/build.sh packages=all cores=… root_cores=…`
  stands in for P2 S2's command. It runs `build_stack.py` with `mac.toml`, with GNU make, sed and
  coreutils first on `PATH`.
- **Launching:** `platforms/mac/launch.sh` opens a bash 5 with `$HEP/setup.sh` loaded, or runs one
  command in it. `stack/setup_extra.sh`, written from `mac.toml`'s `setup_extra` and sourced by
  `setup.sh`, adds `DYLD_LIBRARY_PATH` and the GNU tools.

## What P3 made portable (I15, D11)

| Spot | On macOS |
|---|---|
| `runner/events.py` (the watch socket) | a socket file `hep-watch-<pid>.sock` in `${XDG_RUNTIME_DIR:-$TMPDIR}/hep-watch-<uid>/`. This is the one place where runtime state touches the disk (the user's rule of 2026-10-03 cannot hold without abstract sockets) |
| Paint's `basePath()` (C76) | `$HEP/src/Apps/Paint/base.toml`; `setup.sh` exports `HEP` |
| `bin/hep`'s core count | `os.cpu_count()` |
| the Makefile's `sed -i` | a temporary file and `mv` |

## Rows that differ (P2 S3)

| Row | On macOS |
|---|---|
| R13 | `libonnxruntime.dylib`, not `.so` |
| R16 | the same file count, under `$HEP_INSTALL/fastjet/include/siscone` |
| R20 | Homebrew's versions; recorded |

Everything else is as on Ubuntu. That includes the versions of every HEP package, which are the lab
PC's.

## Allowed adjustments (02 §7)

- A Homebrew formula renamed upstream (`brew info <old>` says so): the new name, recorded.

Everything else is a gate, and above all any new line in `mac.toml`.

## Known limits

- **Not yet run on a Mac.** The recipes follow the Linux build, which the lab PC proved. Their dry
  run is tested; the real build is not. Expect gates.
- **macOS drops `DYLD_LIBRARY_PATH`** whenever one of its own programs starts (System Integrity
  Protection). The stack does not rely on it: absolute install names and rpaths (platforms/mac/README.md
  §4).
- **The test suite on macOS:** some integration tests use Linux tools (`/proc`). A test that cannot
  run there must skip with that reason, never fail silently. P3 S3 lists them when the target is
  `macos`.
