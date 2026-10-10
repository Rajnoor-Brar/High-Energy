# 05 — P2: The stack

**Goal.** Build the software stack into `$HEP` from HEimdall's own recipes, with every package the
lab PC had (`packages=all`), and write `$HEP/setup.sh` for HEimdall.
- **S1:** re-point the recipes at their new home, and install the system packages.
- **S2:** the build, in the background, for hours. P3 proceeds meanwhile (02 §8).
- **S3:** check the result against the lab PC's numbers.

**Reads:**
- `stack/README.md` (moved from `docs/stack/`): its §3 says why each flag is there;
- the annex `targets/<annex>.md`: the system packages and the allowed adjustments;
- 01 §5.8 and §6.3 (C42, C45–C51).

**Writes:**
- `$HEP/{src,build,install,logs,.stamps,.venv}` and `$HEP/setup.sh`;
- commits in HEimdall: the recipes (S1).

**Gates:**
- sudo, for the system packages;
- downloads (S2, once);
- a package that fails twice.

---

## S1: the recipes re-pointed, the system packages

**Preconditions:**
- P1 is verified.
- `git -C $HEP/HEimdall status --porcelain` is empty.

**Tasks:**

1. **The recipes** (C45–C51), in `$HEP/HEimdall`:
   - `stack/build_stack.py:43`: `REPO = HERE.parent`. The recipe now sits in `HEimdall/stack/`,
     so `{repo}` is HEimdall.
   - `stack/build_stack.py:51-57`, the `SETUP` text, becomes:
     ```python
     SETUP = """#!/bin/bash
     # {prefix}/setup.sh: source it once per session (alias load_hep). Written by HEimdall's stack/build_stack.py.
     export HEP={prefix}
     export HEP_INSTALL=$HEP/install
     export HEP_FW=${{HEP_FW:-$HEP/HEimdall}}
     source "$HEP_FW/env/hep_env.sh"
     """
     ```
   - `stack/build_stack.py:177`: drop `"hekit_root"` from the context. In `stack/settings.toml`,
     drop the `hekit_root` key and its comment.
   - `stack/packages.toml` `[fastjet] patch`: `stack/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch`.
   - **The venv's `.pth`** (C51, 01 §5.5). Add `stack/pth.py`:
     ```python
     #!/usr/bin/env python3
     """stack/pth.py PREFIX: the venv's heimdall.pth, so `import hepkit` and `from runner import results` work (01 §5.5)."""
     import site, sys
     from pathlib import Path
     prefix = Path(sys.argv[1])
     Path(site.getsitepackages()[0], "heimdall.pth").write_text(f"{prefix}/HEimdall\n{prefix}/HEimdall/kit\n", encoding="utf-8")
     ```
     Then append to `[python] pre` in `packages.toml`: `"{venv}/bin/python {repo}/stack/pth.py {prefix}"`.
   - `stack/container/Dockerfile`, `Dockerfile.dockerignore` and the new `heimdall.def` (C49): the
     build context is HEimdall, the prefix is `/opt/hep` with `/opt/hep/HEimdall` inside, and
     `HEKIT_ROOT=/work` goes. The [container](targets/container.md) annex holds the full texts.
   - `stack/mac/launch.sh`, `stack/mac/README.md`, `stack/README.md` (C50): `docs/stack/` →
     `stack/`, `utils/Env/hep_env.sh` → `$HEP_FW/env/hep_env.sh`.
2. **The environment entry** (C42), `env/hep_env.sh`, done now so that `setup.sh` works from the
   first build:
   - `:10-17`: `HEP_FW` defaults to `$HEP/HEimdall`, and `HEKIT_ROOT` is gone. If `HEKIT_ROOT`
     is set, print "HEKIT_ROOT is retired: HEP_FW" and unset it;
   - `:177`: `_hep_prepend PATH "$HEP_FW/bin"`;
   - `:133-136`, `hep_cd`: `cd "$(hep where --work)/${2:-configs}/$1"`, which works once P3 has
     `hep where`;
   - `hep_help`'s text to match.
3. **Commit** in HEimdall: `P2.S1: the stack recipes and setup.sh for $HEP/HEimdall`.
4. **The system packages** (the annex). On `ubuntu`:
   ```bash
   python3 -c "import tomllib; print(*tomllib.load(open('$HEP/HEimdall/stack/settings.toml','rb'))['apt_packages'])" | tr ' ' '\n' > $HEP/.setup/apt.txt
   for p in $(cat $HEP/.setup/apt.txt); do
     c=$(apt-cache policy "$p" | awk '/Candidate:/ {print $2}'); [ -z "$c" ] || [ "$c" = "(none)" ] && echo "missing: $p"
   done
   ```
   - Each missing package goes through the annex's **allowed adjustments** (02 §7). Anything not
     covered there is a gate.
   - Then the **gate**: `sudo apt-get install -y --no-install-recommends $(cat $HEP/.setup/apt.txt)`,
     with the count and apt's "Need to get" size.
   - The build itself then runs with `system=false`. The builder never asks for sudo (02 §2).

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `grep -rn 'HEKIT\|hekit_root\|utils/Env\|docs/stack' $HEP/HEimdall/stack $HEP/HEimdall/env \| grep -v 'retired' \| wc -l` | `0` |
| R2 | `python3 $HEP/HEimdall/stack/build_stack.py --dry-run prefix=$HEP packages=all system=false > $HEP/.setup/build.sh && bash -n $HEP/.setup/build.sh && echo ok` | `ok` |
| R3 | `grep -c 'HEP_FW' $HEP/.setup/build.sh` | ≥ `2` (the setup text) |
| R4 | `grep -c 'stack/patches/fastjet' $HEP/.setup/build.sh` | ≥ `1` |
| R5 | `for p in $(cat $HEP/.setup/apt.txt); do dpkg -s $p >/dev/null 2>&1 \|\| echo $p; done \| wc -l` | `0` (after the adjustments, which are recorded) |
| R6 | `wc -l < $HEP/.setup/apt.txt` | `51` at 9cb907a (± the recorded adjustments) |

**On failure:**
- R2: the edit broke the recipe. `git diff` it.
- R5: an install failed. Collect apt's output; this is a gate.

---

## S2: the build (background)

**Preconditions:** S1 `done`.

**Tasks:**

1. **Kept tarballs** (01 §8, optional). Copy them into `$HEP/src/` under the names `build_stack.py`
   looks for, `<package>-<release><ending>`. A tarball already there is used as it is, which saves
   about 555 MB of downloads:

   | Kept (the lab PC's name) | As |
   |---|---|
   | `LHAPDF-6.5.6.tar.gz` | `lhapdf-6.5.6.tar.gz` |
   | `HepMC3-3.3.1.tar.gz` | `hepmc3-3.3.1.tar.gz` |
   | `fastjet-3.5.0.tar.gz`, `fjcontrib-1.104.tar.gz` | the same |
   | `root_v6.40.04.source.tar.gz` | `root-6.40.04.tar.gz` |
   | `downloads?f=YODA-2.1.3.tar.gz` | `yoda-2.1.3.tar.gz` |
   | `Rivet-4.1.3.tar.gz` | `rivet-4.1.3.tar.gz` |
   | `pythia8317.tgz` | `pythia8-8317.tgz` |
   | `ThePEG-2.3.0.tar.bz2`, `Herwig-7.3.0.tar.bz2` | `thepeg-2.3.0.tar.bz2`, `herwig-7.3.0.tar.bz2` |
   | `Delphes-3.5.1.tar.gz` | `delphes-3.5.1.tar.gz` |
   | `sherpa-3.0.5.tar.gz`, `whizard-3.1.8.tar.gz`, `geant4-11.4.2.tar.gz` | the same |
   | `MG5_aMC_v3.7.3.tar.gz` | `madgraph-3.7.3.tar.gz` |
   | `onnxruntime-linux-x64-1.29.0.tgz` | `onnxruntime-1.29.0.tgz` |

   The `.tar.gz` copies of ThePEG and Herwig, and MadGraph 3.5.7, are not used. The names come
   from `build_stack.py`'s `tarball()`; `python3 build_stack.py --dry-run` shows each download it
   would still make.
2. **Cores.** `cores` = logical CPUs − 4, which leaves room for P3. `root_cores` = RAM in GB ÷ 3,
   at most `cores` (stack/README §1). On the lab PC (24 threads, 15 GB) that is 20 and 5. Record
   both in `[choices]`. The command line wins over `settings.toml`, whatever its local edits say.
3. **The downloads gate.** List what is still to fetch: the tarballs not in `$HEP/src` (from the
   dry run), Geant4's datasets (about 4 GB, during its build), the 21 PDF sets, and the pip
   packages. Give the total, and ask once.
4. **Start the build** as the builder (02 §2):
   ```bash
   cd $HEP && nohup python3 $HEP/HEimdall/stack/build_stack.py prefix=$HEP packages=all system=false \
       cores=<cores> root_cores=<root_cores> > $HEP/.setup/stack.log 2>&1 &
   ```
   - Watch `stack.log`: one line per package ("<name>: done in N min"), and a failure's last 30
     lines.
   - On a failure: 02 §5.2. **Resuming** is the same command; the stamps skip what is done
     (stack/README §1).
   - Expected time: ROOT alone takes 1–2 h; everything takes about 4–5 h at these cores.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `ls $HEP/.stamps \| wc -l` | `18` (python lhapdf hepmc3 fastjet fjcontrib root yoda rivet pythia8 thepeg herwig delphes sherpa madgraph whizard onnxruntime geant4 pdfsets) |
| R2 | `tail -1 $HEP/.setup/stack.log` | `done: source <HEP>/setup.sh` |
| R3 | `grep -c 'HEP_FW' $HEP/setup.sh` | `2` |
| R4 | `grep -c 'failed' $HEP/.setup/stack.log` | `0` |

**On failure:**
- A package that fails twice is a gate (02 §5.2), with its log tail and the probable cause. The
  known suspects on a newer Ubuntu are in the annex: a GCC or Python too new for ROOT, ThePEG,
  Herwig or Whizard.

---

## S3: the stack checked

**Preconditions:** S2 `done`.

Every row runs in a fresh shell after `source $HEP/setup.sh`. `hep` itself does not work until P3;
the shell's `hep_status` does. The expected values are the lab PC's of 2026-10-10 (`hep status
--stack`, `lhapdf list --installed`).

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `root-config --version` | `6.40.04` |
| R2 | `pythia8-config --version` | `8.317` |
| R3 | `rivet --version` | `rivet v4.1.3` |
| R4 | `yoda-config --version` | `2.1.3` |
| R5 | `HepMC3-config --version` | `3.03.01` |
| R6 | `fastjet-config --version` | `3.5.0` |
| R7 | `lhapdf-config --version` | `6.5.6` |
| R8 | `geant4-config --version` | `11.4.2` |
| R9 | `Herwig --version \| head -1` | contains `7.3.0` |
| R10 | `Sherpa-config --version` | `3.0.5` |
| R11 | `whizard --version \| head -1` | contains `3.1.8` |
| R12 | `grep -i version $HEP_INSTALL/madgraph/VERSION` | contains `3.7.3` |
| R13 | `test -f $HEP_INSTALL/onnxruntime/lib/libonnxruntime.so && test -x $HEP_INSTALL/delphes/bin/DelphesHepMC3 && echo ok` | `ok` |
| R14 | `lhapdf list --installed \| wc -l` | `21` |
| R15 | `lhapdf list --installed \| tr '\n' ' '` | `CT10 CT14lo CT14nlo CT18NLO CT18NNLO MSHT20nlo_as118 MSTW2008lo68cl MSTW2008lo68cl_nf3 MSTW2008lo68cl_nf4 MSTW2008lo68cl_nf4as5 MSTW2008lo90cl MSTW2008lo90cl_nf3 MSTW2008lo90cl_nf4 MSTW2008lo90cl_nf4as5 NNPDF23_lo_as_0130_qed NNPDF23_nlo_as_0119_qed NNPDF40_nlo_as_01180 PDF4LHC21_40 PDF4LHC21_40_pdfas cteq6l1 nNNPDF30_nlo_as_0118_A208_Z82` |
| R16 | `grep -rl thread_local $HEP_INSTALL/fastjet/include/siscone \| wc -l` | `1` (the SISCone patch, L29) |
| R17 | `python -c "import ROOT, pythia8, yoda, rivet, lhapdf, pyHepMC3, uproot, tomli_w, yaml; print('ok')"` | `ok` |
| R18 | `cat $(python -c "import site; print(site.getsitepackages()[0])")/heimdall.pth` | `$HEP/HEimdall` and `$HEP/HEimdall/kit`, expanded |
| R19 | `du -sh $HEP/install \| cut -f1` | about `6.0G` |
| R20 | `pkg-config --modversion tomlplusplus libzstd zlib` | the system's: `3.4.0 1.5.5 1.3` on 24.04; newer on a newer Ubuntu. Recorded, not compared |

**On failure:**
- R16 = 0: the patch was not applied, and InprocJets' `rivet_threads > 1` will refuse. Collect
  `$HEP/logs/fastjet.log`.
- R17: name the module that fails, and check its install's Python directory against `hep_env.sh`'s
  `PYTHONPATH` lines.
