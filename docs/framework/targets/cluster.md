# Target: a cluster, no sudo

A university cluster or a remote compute node: Linux, no sudo, maybe Apptainer, maybe environment
modules, maybe no network on the compute nodes. Only what differs from the phase files is here
(D11).

## Two ways, and which to take

| Way | When | How |
|---|---|---|
| **A. The image** (preferred) | Apptainer (or Singularity) is installed | build the image elsewhere (the [container](container.md) annex), copy the `.sif` over, run work dirs through it. P2 is replaced by the image; P3 and P4 are done where the image was built |
| B. A native user-space build | no Apptainer, and the user asks for it | `system=false`: every system package must come from environment modules or already be there. P2 S1 lists what is missing; each item is a gate |

P0 S1 records `apptainer` in `[machine]`. With it, propose A at P0's end.

## Prerequisites

- **Way A:** `apptainer` ≥ 1.1, and room for the image (about 10 GB with `packages=all`).
- **Way B:** `git`, `python3` ≥ 3.11 (`module load python/3.11` or similar), a C++17 compiler
  (GCC ≥ 11), `cmake` ≥ 3.20, and the libraries of `apt_packages` under their module names.

## System packages, overlay and launching

| | Way A | Way B |
|---|---|---|
| system packages | inside the image | modules: record the exact `module load` lines in `[choices]`, and put them in `stack/setup_extra.sh` through `settings.toml`'s `setup_extra` (`settings.toml`) |
| overlay | none | `system=false graphics=OFF`; `geant4_data=OFF` if the build node has no network (Geant4 then runs only without its datasets) |
| launching | `apptainer exec --bind <work>:<work> heimdall.sif bash -lc 'cd <work> && hep run …'` | `source $HEP/setup.sh` after the module loads |

## Running on a cluster

- **Scheduler.** There is no executor for Slurm or HTCondor (F9, "later"). Submit a job script that
  runs `hep run` inside one allocation, and size `threads` and `parallelism` to the allocation
  (`--set run.threads=$SLURM_CPUS_PER_TASK`).
- **FIFOs need a local filesystem.** Some shared filesystems refuse `mkfifo`, or are slow with it.
  Point `HEP_OUTPUT` at node-local scratch (`$TMPDIR/…`) and keep `results/` on the shared one.
- **`hep watch`** sees only runs on the same node, in the same network namespace (abstract sockets).
- **`$HEP` shared by several users:** make it read-only for them. Each user needs their own work
  dirs, and the framework's `build/` is written only by `hep build --framework`.

## Allowed adjustments (02 §7)

- Way B only: a module name for a library, recorded with its version.

Everything else is a gate.

## Known limits

- Way B has never been run. Expect a gate per missing library.
- Without network on compute nodes, the PDF sets and Geant4's data must be fetched on a login node
  (P2 S2's downloads gate says where).
