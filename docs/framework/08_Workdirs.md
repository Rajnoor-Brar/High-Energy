# 08 — P5: The work dirs

**Goal.**
- **S1:** High-Energy becomes the first work dir, lean, on branch `work` (D15, 01 §4.3). It builds
  its modules and plugins and checks every run TOML.
- **S2:** a second, toy work dir is made by `hep setup --project`, and runs. The two are shown to
  be independent (D4).

**Reads:** 01 §4, §6.5 (C65–C67, C77), §7; `$HEP/.setup/kept/`.

**Writes:**
- the High-Energy clone: branch `work` only;
- the toy work dir, under `$HEP/.setup/verify/P5/` (a test, so not a real place for a work dir).

**Gates:**
- the diffs to the user's `configs/` and `modules/` (S1), shown before they are applied;
- the push of `work` (S1, last task).

---

## S1: High-Energy, lean

**Preconditions:**
- P4 is verified, or waiting only at its R2 gate.
- `git -C ~/Github/High-Energy status --porcelain` is empty.
- `source $HEP/setup.sh`.

**Tasks:**

1. **The branch:**
   ```bash
   cd ~/Github/High-Energy && git switch -c work split/base
   ```
2. **The framework leaves.** Every path the move map sends to HEimdall:
   ```bash
   python3 $HEP/.setup/movemap.py --src ~/Github/High-Energy --list fw | xargs -d '\n' git rm -q --
   ```
3. **The user's untracked files come back** (D13): `datasets/ literature/ cross_machine/ reports/`
   from `$HEP/.setup/kept/`, copied into the clone. They stay untracked, as before.
4. **Adopt:**
   ```bash
   hep setup --adopt ~/Github/High-Energy
   ```
   - This adds `hep.toml` (`name = "High-Energy"`), `Makefile`, `README.md`, `CLAUDE.md` and the
     missing folders (`results/ output/ build/`).
   - It prints the template's `.gitignore` lines that High-Energy's `.gitignore` lacks. Add those
     to `.gitignore` by hand, and keep every existing line (`literature/*`, `cross_machine/*`, …).
5. **The user's files** (C65–C67, C77). Show the diffs, then ask (a **gate**):
   ```bash
   hep migrate                 # the diff: {repo} → {work} (C65, eic.toml:170 at 9cb907a)
   ```
   and, as a diff:
   - `modules/PhotoProduction/delphes_jets.py:16` loses its `sys.path` line (C66);
   - `modules/PhotoProduction/Inproc/Analysis.hh:68` and `configs/PhotoProduction/InProc{EIC,Zeus}.toml:23`
     name `$HEP_FW/stack/patches/…` (C67);
   - the comments of C77 (`Stamp.hh:3`, `Engines.hh:13`, `Analysis.hh:13`, `delphes_jets.py:9`,
     `Lambda/README.md:8`) name `kit/…` and `$HEP_FW/stack/patches/` by 06's renames.

   On a yes: `hep migrate --apply` and the edits.
   - `Analysis.hh` is a message string inside InprocJets. Changing it rebuilds InprocJets, which is
     fine here because nothing has run yet on this machine.
6. **Commit by path:**
   - the removals are staged by `git rm`;
   - `git add hep.toml Makefile README.md CLAUDE.md .gitignore`, plus each file changed in task 5;
   - message: `work: High-Energy as a HEimdall work dir (the framework is HEimdall, from split/base <sha>)`.
7. **Build and check:**
   ```bash
   cd ~/Github/High-Energy && hep build && hep check
   ```
8. **The push** of `work` to `origin` is a **gate**. Ask, with what it contains; do not ask for a
   default-branch change.

**Verification** (in `~/Github/High-Energy`):

| # | Command | Expected |
|---|---|---|
| R1 | `hep where --work` | `<home>/Github/High-Energy` |
| R2 | `git ls-files \| wc -l` | M + 4, where M is P1 S1's "work" count (`hep.toml`, `Makefile`, `README.md`, `CLAUDE.md`): 1367 at 9cb907a |
| R3 | `ls -d utils tests bots docs/stack docs/framework 2>/dev/null \| wc -l` | `0` |
| R4 | `git ls-files docs` | `docs/Untitled-1.md` |
| R5 | `ls build/*/*.exe build/Rivet/*.so \| wc -l` | `5` (Lambda/Lambda.exe, PhotoProduction/InprocJets.exe, Rivet_photo_eic.so, Rivet_Lamriv.so, Rivet_particle_spectra.so) |
| R6 | `hep check; echo "exit $?"` | `exit 0` (every run TOML under `configs/*/`) |
| R7 | `grep -rn '{repo}\|utils/' configs/*/*.toml modules \| wc -l` | `0` (`configs/PhotoProduction/xx/` is the user's stash: not checked, not changed) |
| R8 | `hep run PhotoProduction/zeus_validation --plan > /dev/null; echo "exit $?"` | `exit 0` |
| R9 | `git status --porcelain \| wc -l` | `0` |

**On failure:**
- **R6:** a config the user changed after `split/base` may fail for its own reasons. Name which,
  and which C-rule. This is a gate, because configs are the user's.
- **R5 short:** the module's `// requires:` line names a library that `flags.mk` did not find
  (run `hep build --configure`).

---

## S2: a toy work dir, and independence

**Preconditions:** S1 `done`.

**Tasks:**

1. **Make it, outside every other work dir:**
   ```bash
   T=$HEP/.setup/verify/P5/toy && hep setup $T --project Toy --git
   ```
2. **Run its starter:** `cd $T && hep run Toy/toy --plain`. That is 2 points of 500 events: Pythia →
   Rivet (`MC_JETS`) → yd2rt, then the pages.
3. **Stamp, then prove independence.** Before the run, `touch $HEP/.setup/verify/P5/stamp`. After
   it, check the rows below.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `cd $T/configs && hep where --work` | `$T` |
| R2 | `cd $T && hep status Toy/toy \| grep -c complete` | `2` (both points complete) |
| R3 | `ls $T/results/Toy/*/*/plots/root/*.pdf 2>/dev/null \| wc -l` | ≥ `1` |
| R4 | `find ~/Github/High-Energy -newer $HEP/.setup/verify/P5/stamp -not -path '*/.git/*' \| wc -l` | `0` (the toy run wrote nothing into High-Energy) |
| R5 | `find $HEP -newer $HEP/.setup/verify/P5/stamp -not -path "$HEP/.setup/*" \| wc -l` | `0` (and nothing into `$HEP`, its own `verify/` apart) |
| R6 | `python3 -c "import json,glob; d=json.load(open(glob.glob('$T/output/Toy/*/*/*/provenance.json')[0])); print(d['work']['name'], d['git']['framework']['revision'] == '$(git -C $HEP/HEimdall rev-parse HEAD)')"` | `toy True` (the work dir's name, its folder's by default; and HEimdall's revision) |
| R7 | `cd ~/Github/High-Energy && hep ls \| grep -c Toy` | `0` (High-Energy does not see the toy's configs) |

**After the rows pass:** the toy stays in `verify/P5/` as the record of the check. It is deleted
only on the user's word.
