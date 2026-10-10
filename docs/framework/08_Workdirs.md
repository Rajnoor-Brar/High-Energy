# 08 — P5: The work dirs

**Goal.**
- **S1:** Top-Quark, `~/Github/Top-Quark`, is made fresh by Heimdall with the generic starter, then
  built, checked and run (D32, 01 §4.3). It is a test: the user decides later what Top-Quark
  becomes.
- **S2:** a throwaway second work dir shows that work dirs are independent (D4).

High-Energy is left alone (D31). Its conversion into a lean work dir is parked in the appendix and
runs only on the user's word.

**Reads:** 01 §4 and §5.

**Writes:**
- `~/Github/Top-Quark`;
- the throwaway work dir, under `$HEP/.setup/verify/P5/`;
- nothing in Heimdall outside `forge/scratch/` and `.setup/`.

**Gates:** none. Pushing Top-Quark anywhere is the user's choice, asked in P6.

---

## S1: Top-Quark

**Preconditions:**
- P4 is verified, or waiting only at its S2 R2 gate.
- `source $HEP/setup.sh`.
- `~/Github/Top-Quark` does not exist.

**Tasks:**

1. **Make it:**
   ```bash
   hep setup ~/Github/Top-Quark --project Starter --git
   ```
   This writes 01 §4.1's files and folders, `configs/Starter/starter.{toml,cmnd}` and
   `modules/Starter/`, and makes one commit.
2. **Build and check:**
   ```bash
   cd ~/Github/Top-Quark && hep build && hep check
   ```
   `hep build` has nothing to compile (no modules yet), but writes the work dir's `build/flags.mk`.
3. **Stamp, then run the starter:**
   ```bash
   touch $HEP/.setup/verify/P5/stamp
   cd ~/Github/Top-Quark && hep run Starter/starter --plain
   ```
   That is 2 points of 500 events: Pythia → Rivet (`MC_JETS`) → yd2rt, then the pages.

**Verification** (in `~/Github/Top-Quark`):

| # | Command | Expected |
|---|---|---|
| R1 | `cd configs/Starter && hep where --work` | `<home>/Github/Top-Quark` |
| R2 | `git ls-files \| sort \| tr '\n' ' '` | `.gitignore .vscode/settings.json CLAUDE.md Makefile README.md configs/Starter/starter.cmnd configs/Starter/starter.toml hep.toml` |
| R3 | `git log --oneline \| wc -l` | `1` |
| R4 | `hep check; echo "exit $?"` | `exit 0` |
| R5 | `hep status Starter/starter \| grep -c complete` | `2` (both points complete) |
| R6 | `ls results/Starter/*/*/plots/root/*.pdf 2>/dev/null \| wc -l` | ≥ `1` |
| R7 | `python3 -c "import json,glob; d=json.load(open(glob.glob('output/Starter/*/*/*/provenance.json')[0])); print(d['work']['name'], d['git']['heimdall']['revision'] == '$(git -C $HEP rev-parse HEAD)')"` | `Top-Quark True` |
| R8 | `find $HEP -newer $HEP/.setup/verify/P5/stamp -not -path "$HEP/.setup/*" -not -path "$HEP/forge/scratch/*" -not -path '*/__pycache__*' \| wc -l` | `0` (the run wrote nothing into Heimdall but Python's bytecode caches) |
| R9 | `git status --porcelain \| wc -l` | `0` (`build/ output/ results/` are ignored) |

**On failure:**
- **R4:** the starter no longer fits the schema. 06 S2 says: fix the template's starter, not the
  schema. This is a change in Heimdall, so commit it, and run `hep setup` again on a fresh folder.
- **R5:** read the point's log (`output/Starter/…/logs/`) and 02 §5.2.

---

## S2: a second work dir, and independence

**Preconditions:** S1 `done`.

**Tasks:**

1. **Make a throwaway work dir, outside every other:**
   ```bash
   T=$HEP/.setup/verify/P5/second && hep setup $T --project Second
   ```
2. **Run its starter:** `touch $HEP/.setup/verify/P5/stamp2 && cd $T && hep run Second/second --plain`.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `cd $T/configs && hep where --work` | `$T` |
| R2 | `cd ~/Github/Top-Quark && hep ls \| grep -c Second` | `0` (Top-Quark does not see the second's configs) |
| R3 | `cd $T && hep ls \| grep -c Starter` | `0` (and the other way round) |
| R4 | `find ~/Github/Top-Quark -newer $HEP/.setup/verify/P5/stamp2 -not -path '*/.git/*' \| wc -l` | `0` (the second's run wrote nothing in Top-Quark) |
| R5 | `cd $T && hep status Second/second \| grep -c complete` | `2` |
| R6 | `HEP_WORK=$T hep where --work` (from `~/Github/Top-Quark`) | `$T`: the variable wins over the search |

**After the rows pass:** the second work dir stays in `verify/P5/` as the record of the check. It
is deleted only on the user's word.

---

## Appendix: High-Energy as a work dir (parked, D31)

**Not part of P5.** The user left High-Energy alone (2026-10-10). The steps below run only when the
user asks for them; then they are a phase of their own, with these gates: the diffs to the user's
files (shown first), and the push of `work`.

**Preconditions:**
- Heimdall is verified (P0–P6).
- `git -C ~/Github/High-Energy status --porcelain` is empty.

**Tasks:**

1. **The branch:**
   ```bash
   cd ~/Github/High-Energy && git switch -c work split/base
   ```
2. **The framework leaves.** Every path the move map sends to Heimdall:
   ```bash
   python3 $HEP/.setup/movemap.py --src ~/Github/High-Energy --list fw | xargs -d '\n' git rm -q --
   ```
3. **The user's untracked files come back** (D13): `datasets/ literature/ cross_machine/ reports/`
   from `$HEP/.setup/kept/`, copied into the clone. They stay untracked, as before.
4. **Adopt:**
   ```bash
   hep setup --adopt ~/Github/High-Energy
   ```
   - This adds `hep.toml` (`name = "High-Energy"`), `Makefile`, `README.md`, `CLAUDE.md`,
     `.vscode/settings.json` if absent, and the missing folders (`results/ output/ build/`).
   - It prints the template's `.gitignore` lines that High-Energy's `.gitignore` lacks. Add those
     to `.gitignore` by hand, and keep every existing line.
5. **The user's files** (C65–C67, C77). Show the diffs, then ask (a **gate**):
   - `hep migrate` (C65): `{repo}` → `{work}`;
   - `modules/PhotoProduction/delphes_jets.py:16` loses its `sys.path` line (C66);
   - `Inproc/Analysis.hh:68` and `configs/PhotoProduction/InProc{EIC,Zeus}.toml:23` name
     `$HEP/patches/…` (C67);
   - the comments of C77 name `src/…`, `framework/hepkit.py` and `$HEP/patches/`.

   On a yes: `hep migrate --apply` and the edits.
6. **Commit by path:**
   - the removals are staged by `git rm`;
   - `git add hep.toml Makefile README.md CLAUDE.md .gitignore`, plus each file changed in task 5;
   - message: `work: High-Energy as a Heimdall work dir (the framework is Heimdall, from split/base <sha>)`.
7. **Build and check:** `cd ~/Github/High-Energy && hep build && hep check`.
8. **The push** of `work` is a gate.

**Verification** (in `~/Github/High-Energy`):

| # | Command | Expected |
|---|---|---|
| R1 | `hep where --work` | `<home>/Github/High-Energy` |
| R2 | `git ls-files \| wc -l` | the map's "work" count plus the files `--adopt` added and were committed (`hep.toml`, `Makefile`, `README.md`, `CLAUDE.md`; `.vscode/settings.json` only if High-Energy had none) |
| R3 | `ls -d utils tests bots docs/stack docs/framework 2>/dev/null \| wc -l` | `0` |
| R4 | `ls build/*/*.exe build/Rivet/*.so \| wc -l` | `5` (Lambda/Lambda.exe, PhotoProduction/InprocJets.exe, Rivet_photo_eic.so, Rivet_Lamriv.so, Rivet_particle_spectra.so) |
| R5 | `hep check; echo "exit $?"` | `exit 0` |
| R6 | `git status --porcelain \| wc -l` | `0` |
