# High-Energy Project (Lambda Reconstruction)

## Project Overview
This is a C++17 project for a Lambda baryon (Λ → p + π⁻) reconstruction simulation. The primary workflow involves generating events using Pythia8, storing the data in a ROOT TTree, and then running a reconstruction pass that produces histograms. 

**Main Technologies:**
- C++17
- [ROOT](https://root.cern/) framework
- [Pythia8](https://pythia.org/)
- [toml++](https://marzer.github.io/tomlplusplus/) for configuration parsing

**Architecture:**
The codebase utilizes a strict **namespace + facade pattern**. It is primarily a header-only library with executable drivers (the top-level `_*.cc` files). 
- Every namespace `Foo` has a public facade file `Foo.hh` which acts as an include aggregator.
- The actual implementation resides in a subdirectory `Foo/` (e.g., `Foo/Types.hh`, `Foo/Workers.hh`).
- Cross-namespace code must **only** include the public facade (`#include "Foo.hh"`), never a sibling's submodule directly.

## Building and Running
The build system uses GNU Make.

**Building Executables:**
```sh
make _Lambda_Data            # Builds _Lambda_Data.exe
make _Lambda_Reconstruction  # Builds _Lambda_Reconstruction.exe
make _Lambda_Parallel        # Builds _Lambda_Parallel.exe
make clean                   # Removes all generated executables
```

**Running Drivers:**
Executables can optionally accept a `.toml` configuration file argument.
```sh
./_Lambda_Data.exe [configs/Lambda_Generation.toml]
./_Lambda_Reconstruction.exe [configs/Lambda_Reconstruction.toml]
```

**Testing:**
```sh
make test  # Builds test executables and runs `tests/run_all.sh`
```

## Development Conventions
- **Process Directives:** Always consult `bots/BOT.md` for plan approval, testing protocol, code-design philosophy, and directory layout.
- **Testing Protocol:** When running tests, you must redirect output paths from `outputs/` to `outputs/test/`. Do not restore output paths to `outputs/` automatically if tests fail; wait for user instruction.
- **Bot/Agent Workflows:** Do not ask for permission to proceed after proposing a plan. Only transition to implementation when explicitly told (e.g. "Implement the plan"). Document accumulated pitfalls in `bots/lessons.md`.
- **Code Design:** Submodules should build linearly on each other, minimizing circular dependencies, and expose a minimal interface. Cross-namespace communication should ideally happen via the `Types.hh` definition of the respective module.
