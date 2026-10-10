# 05 — P2: The stack

**Goal.** Build the software stack into Heimdall itself, with every package the lab PC had
(`packages=all`). The places (D27) are:
- `stash/` for the downloads;
- `forge/` for the build trees and logs;
- `stack/` for the installs;
- `env/venv/` for the Python environment.

The steps:
- **S1:** re-point the recipes at Heimdall's root and its folders, and install the system packages.
- **S2:** the build, in the background, for hours. P3 proceeds meanwhile (02 §8).
- **S3:** check the result against the lab PC's numbers.

**Reads:**
- `docs/stack/README.md`: its §3 says why each flag is there;
- the annex `targets/<annex>.md`: the system packages and the allowed adjustments;
- 01 §5.8 and §6.2–6.3 (C42, C45–C51, C79, C80).

**Writes:**
- `$HEP/{stash,forge,stack}` and `$HEP/env/venv`;
- commits in Heimdall: the recipes and the environment (S1).

**Gates:**
- sudo, for the system packages;
- downloads (S2, once);
- a package that fails twice.

---

## S1: the recipes and the environment re-pointed, the system packages

**Preconditions:**
- P1 is verified.
- `git -C $HEP status --porcelain` is empty.

**Tasks:**

1. **The recipes** (C45–C51, C79), in `$HEP`:
   - `build_stack.py:43`: `REPO = HERE`. The recipe now sits at Heimdall's root, so `{repo}` is
     Heimdall.
   - **The prefix is Heimdall itself.** `settings.toml`'s `prefix` key and its comment go, and
     `build_stack.py` takes `REPO` as the prefix. `hekit_root` goes from `settings.toml` and from
     the context (`build_stack.py:177`).
   - **The layout** (C79), at `build_stack.py:171,184,212,224,349,357,406,433`:

     | Was, under the prefix | Becomes |
     |---|---|
     | `src/` (archives and sources) | `stash/` |
     | `build/<pkg>` | `forge/<pkg>/` |
     | `install/` | `stack/` |
     | `.venv/` | `env/venv/` |
     | `logs/` | `forge/logs/` |
     | `.stamps/` | `stack/.stamps/` |

   - **`setup.sh` is no longer written** (C45, C47).
     - `SETUP` (`:51-57`), `setup_text()` (`:387-390`) and the write at `:443-449` go.
     - In their place, `build_stack.py` writes `stack/setup_extra.sh` from `settings.toml`'s
       `setup_extra` lines: empty on Ubuntu; the `DYLD_LIBRARY_PATH` and GNU-tools lines with
       `platforms/mac/mac.toml`.
     - The run still ends by printing `done: source <HEP>/setup.sh`.
   - `packages.toml` `[fastjet] patch`: `patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch` (C48).
   - **The venv's `.pth`** (C51, 01 §5.5). Add `pth.py` at the root:
     ```python
     #!/usr/bin/env python3
     """pth.py HEP: the venv's heimdall.pth, so `import hepkit` and `from runner import results` work (01 §5.5)."""
     import site, sys
     from pathlib import Path
     Path(site.getsitepackages()[0], "heimdall.pth").write_text(f"{sys.argv[1]}/framework\n", encoding="utf-8")
     ```
     Then append to `[python] pre` in `packages.toml`: `"{venv}/bin/python {repo}/pth.py {repo}"`.
   - `platforms/container/Dockerfile`, `Dockerfile.dockerignore` and the new `heimdall.def` (C49):
     the [container](targets/container.md) annex holds the full texts.
   - `platforms/mac/launch.sh`, `platforms/mac/README.md`, `docs/stack/README.md`,
     `docs/stack/build_by_hand.txt` (C50): `docs/stack/` → the root and `platforms/`; `~/HEP` →
     `~/Github/Heimdall`; `src/ build/ install/ .venv` → `stash/ forge/ stack/ env/venv`.
2. **The environment** (C42, C80), `env/hep_env.sh`, done now so that `setup.sh` works from the
   first build. By 01 §5.8's table:
   - `:10-17`: `HEP` defaults to the folder above `env/`; `HEP_INSTALL` to `$HEP/stack`.
     `HEKIT_ROOT` is gone; if it is set, print "HEKIT_ROOT is retired: HEP" and unset it.
   - `:129-131`, `:145-147`: `hep_stash`, `hep_forge`, `hep_stack`.
   - `:133-136`, `hep_cd`: `cd "$(hep where --work)/${2:-configs}/$1"`, which works once P3 has
     `hep where`.
   - `:160`, `:162`: the venv at `$HEP/env/venv`.
   - `:177`: `_hep_prepend PATH "$HEP/framework/bin"`.
   - `hep_help`'s text to match.
3. **`setup.sh`** (written in P1) is checked against 01 §5.8. Nothing more to do.
4. **Commit** in Heimdall: `P2.S1: the recipes at the root; stash/ forge/ stack/ env/venv; the environment`.
5. **The system packages** (the annex). On `ubuntu`:
   ```bash
   python3 -c "import tomllib; print(*tomllib.load(open('$HEP/settings.toml','rb'))['apt_packages'])" | tr ' ' '\n' > $HEP/.setup/apt.txt
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
| R1 | `grep -rn 'HEKIT\|hekit_root\|HEP_FW\|utils/Env\|docs/stack\|/install\b\|\.venv' $HEP/build_stack.py $HEP/packages.toml $HEP/settings.toml $HEP/env \| grep -v 'retired' \| wc -l` | `0` |
| R2 | `cd $HEP && python3 build_stack.py --dry-run packages=all system=false > .setup/build.sh && bash -n .setup/build.sh && echo ok` | `ok` |
| R3 | `grep -c "$HEP/stash/\|$HEP/forge/\|$HEP/stack/" $HEP/.setup/build.sh` | ≥ `50` (every package's paths in the new places) |
| R4 | `grep -c "$HEP/patches/fastjet" $HEP/.setup/build.sh` | ≥ `1` |
| R5 | `for p in $(cat $HEP/.setup/apt.txt); do dpkg -s $p >/dev/null 2>&1 \|\| echo $p; done \| wc -l` | `0` (after the adjustments, which are recorded) |
| R6 | `wc -l < $HEP/.setup/apt.txt` | `51` at 9cb907a (± the recorded adjustments) |

**On failure:**
- R2 or R3: an edit broke the recipe. `git diff` it.
- R5: an install failed. Collect apt's output; this is a gate.

---

## S2: the build (background)

**Preconditions:** S1 `done`.

**Tasks:**

1. **Kept tarballs** (01 §8, optional). Copy them from `$HEP/.setup/kept/stash/` into `$HEP/stash/`
   under the names `build_stack.py` looks for, `<package>-<release><ending>`. An archive already
   there is used as it is, which saves about 555 MB of downloads:

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
   at most `cores` (`docs/stack/README.md` §1). On the lab PC (24 threads, 15 GB) that is 20 and 5.
   Record both in `[choices]`. The command line wins over `settings.toml`, whatever its local edits
   say.
3. **The downloads gate.** List what is still to fetch: the archives not in `stash/` (from the dry
   run), Geant4's datasets (about 4 GB, during its build), the 21 PDF sets, and the pip packages.
   Give the total, and ask once.
4. **Start the build** as the builder (02 §2):
   ```bash
   cd $HEP && nohup python3 build_stack.py packages=all system=false \
       cores=<cores> root_cores=<root_cores> > .setup/stack.log 2>&1 &
   ```
   - Watch `stack.log`: one line per package ("<name>: done in N min"), and a failure's last 30
     lines.
   - On a failure: 02 §5.2. **Resuming** is the same command; the stamps in `stack/.stamps/` skip
     what is done (`docs/stack/README.md` §1).
   - Expected time: ROOT alone takes 1–2 h; everything takes about 4–5 h at these cores.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `ls $HEP/stack/.stamps \| wc -l` | `18` (python lhapdf hepmc3 fastjet fjcontrib root yoda rivet pythia8 thepeg herwig delphes sherpa madgraph whizard onnxruntime geant4 pdfsets) |
| R2 | `tail -1 $HEP/.setup/stack.log` | `done: source <HEP>/setup.sh` |
| R3 | `ls $HEP/stack \| wc -l` | ≥ `14` (the install folders) |
| R4 | `grep -c 'failed' $HEP/.setup/stack.log` | `0` |
| R5 | `git -C $HEP status --porcelain \| wc -l` | `0` (everything the build wrote is ignored) |

**On failure:**
- A package that fails twice is a gate (02 §5.2), with its log tail (`forge/logs/<pkg>.log`) and
  the probable cause. The known suspects on a newer Ubuntu are in the annex: a GCC or Python too
  new for ROOT, ThePEG, Herwig or Whizard.

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
| R18 | `cat $(python -c "import site; print(site.getsitepackages()[0])")/heimdall.pth` | `<HEP>/framework`, expanded |
| R19 | `echo $HEP_INSTALL; du -sh $HEP/stack \| cut -f1` | `<HEP>/stack`, and about `6.0G` |
| R20 | `which python` | `<HEP>/env/venv/bin/python` |
| R21 | `pkg-config --modversion tomlplusplus libzstd zlib` | the system's: `3.4.0 1.5.5 1.3` on 24.04; newer on a newer Ubuntu. Recorded, not compared |

**On failure:**
- R16 = 0: the patch was not applied, and InprocJets' `rivet_threads > 1` will refuse. Collect
  `$HEP/forge/logs/fastjet.log`.
- R17: name the module that fails, and check its install's Python directory against `hep_env.sh`'s
  `PYTHONPATH` lines.
