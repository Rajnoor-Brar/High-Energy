# 03 — P0: Preflight

**Goal.** Know the machine, choose its annex, have High-Energy pinned at `split/base`, and bring
back what was kept before the wipe. After P0:
- `$HEP/.setup/` exists;
- `state.toml` holds `[machine]` and `[source]`;
- `kept/` holds the user's copies.

**Reads:** [01](01_Target.md) §8 (what was kept), [02](02_Agents.md) §3 (the state).

**Writes:**
- `$HEP/.setup/`;
- the tag `split/base` in the High-Energy clone (02 §6 allows it).

Nothing else.

**Gates:** sudo, only if `git`, `python3-venv` or `curl` are missing.

---

## S1: the machine and its annex

**Preconditions:**
- The start prompt was given in `~/Github/High-Energy` (02 §11.1).
- `git -C ~/Github/High-Energy status --porcelain` prints nothing.

**Tasks:**

1. Create the state's folders:
   ```bash
   export HEP=${HEP:-$HOME/HEP}
   mkdir -p "$HEP/.setup/kept" "$HEP/.setup/verify"
   ```
2. Survey, and write `[machine]` into `$HEP/.setup/state.toml` with 02 §3.1's keys, from:
   ```bash
   . /etc/os-release && echo "$PRETTY_NAME"          # os     (macOS: sw_vers -productVersion)
   uname -m                                          # arch
   python3 -c 'import os; print(os.cpu_count())'     # cores (logical)
   awk '/MemTotal/ {printf "%d\n", $2/1048576}' /proc/meminfo      # ram_gb
   df -BG --output=avail "$HEP" | tail -1            # disk_free_gb
   sudo -n true 2>/dev/null && echo yes || echo "ask"                # sudo: "ask" means a password is needed (fine)
   curl -sI --max-time 10 https://root.cern | head -1                # network
   docker info >/dev/null 2>&1 && echo usable || { command -v docker >/dev/null && echo "installed, no group" || echo absent; }
   command -v apptainer && apptainer --version
   python3 --version; git --version
   ```
3. **Choose the annex** by the first rule that holds, and record it as `annex`:

   | When | Annex |
   |---|---|
   | the user's start prompt names one | that one |
   | macOS | `macos` |
   | Linux with `apt-get` and sudo (a password is fine) | `ubuntu` |
   | Linux without sudo | `cluster` |

   `container` is only ever chosen by the user, because it is a way of shipping `$HEP`, not a kind
   of machine.
4. Read `targets/<annex>.md`. Its **prerequisites** must hold before S2: the tools P0 to P2 need
   before the stack exists (`git`, `curl`, `python3` ≥ 3.11 with `venv`). A missing one on
   `ubuntu` is a **gate**:
   ```bash
   sudo apt-get install -y git curl python3-venv
   ```

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `python3 -c "import tomllib; m = tomllib.load(open('$HEP/.setup/state.toml','rb'))['machine']; print(len(m))"` | `12` (the keys of 02 §3.1) |
| R2 | `python3 -c 'import sys; print(sys.version_info >= (3, 11))'` | `True` |
| R3 | `df -BG --output=avail "$HEP" \| tail -1 \| tr -dc 0-9` | ≥ `60`: the stack, with everything, used 19.9 GB on the lab PC (`install` 6.0, `src` 5.6, `build` 6.8, `.venv` 1.5), plus room for results |
| R4 | `test -f docs/framework/targets/$(python3 -c "import tomllib; print(tomllib.load(open('$HEP/.setup/state.toml','rb'))['machine']['annex'])").md && echo ok` | `ok` |
| R5 | `python3 -c 'import os; print(os.cpu_count())'` and the RAM, against the lab PC before the wipe: 24 logical CPUs, 15 GB | recorded; a smaller machine is not a failure, but P2's `cores` and `root_cores` follow it |

**On failure:**
- R3 below 60: stop. This is a gate; propose `packages=core` (no Geant4 data, ~4 GB less) or
  another disk.
- R2: the annex's prerequisites.

---

## S2: the sources and the kept files

**Preconditions:** S1 `done`.

**Tasks:**

1. **Pin the revision.** In `~/Github/High-Energy`, check out the branch the plans came with
   (`rework`, unless the user said otherwise), then:
   ```bash
   git tag split/base            # 02 §6 allows this one write
   git rev-parse split/base      # → [source] revision
   git ls-files | wc -l          # → [source] tracked (1567 at 9cb907a; more if commits landed since)
   ```
   If commits landed after 9cb907a, re-run the move map's check (04 S1, task 2, with `--check`)
   before going further. A path that no rule matches is a gate, not a guess.
2. **Bring back the kept files.** Copy them from where the user put them (the start prompt's
   `<path>`) into `$HEP/.setup/kept/`, keeping their layout:
   ```
   kept/datasets/  kept/literature/  kept/cross_machine/  kept/reports/       (the user's, D13)
   kept/src/       (optional: the stack's tarballs, used by 05 S2)
   kept/memory/    (optional: the agents' notes, used by 09 S2)
   kept/reference/output/…/NNPDF23lo/{cards,config,provenance.json}
   kept/reference/results/…/NNPDF23lo/{zeus.yoda,zeus.yoda.json,zeus.root}   (01 §8; used by 09 S1)
   ```
3. Record `[source] kept` (where they came from) and what was found. A missing optional item is
   noted, not a failure.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `git -C ~/Github/High-Energy rev-parse split/base` | equals `[source] revision` |
| R2 | `git -C ~/Github/High-Energy ls-tree -r --name-only split/base docs/framework \| wc -l` | ≥ `14` (README, 01–09, the four annexes) |
| R3 | `sha256sum $HEP/.setup/kept/datasets/zeus_eic.yoda \| cut -c1-16` | `625723465b10ea69` |
| R4 | `sha256sum $HEP/.setup/kept/reference/output/PhotoProduction/inproc_zeus/01_default/NNPDF23lo/cards/pythia.point.cmnd \| cut -c1-16` | `51d0db61bc8ec901` |
| R5 | `sha256sum $HEP/.setup/kept/reference/results/PhotoProduction/inproc_zeus/01_default/NNPDF23lo/zeus.yoda \| cut -c1-16` | `0db5cc2e327680ee` |
| R6 | `du -sh $HEP/.setup/kept/literature $HEP/.setup/kept/reports` | about `98M` and `11M` (the lab PC's, 2026-10-10) |

**On failure:**
- R3–R5 differ: the copy is not the one taken before the wipe. This is a gate: the user looks.
  Without R4 and R5, 09 S1 loses its reference point, though the slow suite's gates remain.
- R2 short: the plans were pushed before 2b finished. Stop, because the phase files are the plan.
