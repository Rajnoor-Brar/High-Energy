# 04 — P1: Seed HEimdall

**Goal.** Create `$HEP/HEimdall` from High-Energy at `split/base`. The step is mechanical:
- every path the move map (01 §7) sends to HEimdall is copied there, from git, not from the
  working tree;
- the files 01 §3 calls new are added;
- the fixture work dir is assembled;
- one import commit names the revision (D2).

No code changes here, so nothing runs yet. The seam is P3's.

**Reads:** 01 §3, §5.7, §7; `$HEP/.setup/kept/`.

**Writes:** `$HEP/HEimdall/` and `$HEP/.setup/movemap.py`.

**Gates:** none.

---

## S1: the move map applied

**Preconditions:**
- P0 is verified.
- `git -C ~/Github/High-Energy rev-parse split/base` gives `[source] revision`.
- `$HEP/HEimdall` does not exist.

**Tasks:**

1. **Write the applier.** Copy this into `$HEP/.setup/movemap.py` exactly. It was tested against
   `9cb907a` (204 fw, 1363 work, 0 unmatched; 204 files written, with the six executables).

   ```python
   #!/usr/bin/env python3
   """$HEP/.setup/movemap.py: 01_Target.md §7's move map, applied (04 S1). Standard library only.

       movemap.py --src REPO [--rev split/base] --check        count; fail on an unmatched path or a collision
       movemap.py --src REPO [--rev split/base] --list fw|work  the paths of one side
       movemap.py --src REPO [--rev split/base] --dst DIR      write the "fw" side into DIR, from git (not the worktree)
   """
   import argparse
   import re
   import subprocess
   import sys
   import tomllib
   from pathlib import Path


   def git(src, *args):
       return subprocess.run(["git", "-C", src, *args], capture_output=True, check=True).stdout


   def rules(src, rev):
       page = git(src, "show", f"{rev}:docs/framework/01_Target.md").decode("utf-8")
       block = re.search(r"```toml\n(# 01_Target\.md §7.*?)```", page, re.S).group(1)
       return tomllib.loads(block)["rules"]


   def matches(glob, path):
       rx = "^" + re.escape(glob).replace(r"\*\*", "\0").replace(r"\*", "[^/]*").replace("\0", ".*") + "$"
       return re.match(rx, path) is not None


   def prefix(glob):
       literal = glob.split("*")[0]
       return literal[: literal.rfind("/") + 1]


   def main():
       ap = argparse.ArgumentParser()
       ap.add_argument("--src", required=True)
       ap.add_argument("--rev", default="split/base")
       ap.add_argument("--dst")
       ap.add_argument("--check", action="store_true")
       ap.add_argument("--list", choices=["fw", "work"])
       a = ap.parse_args()
       table = rules(a.src, a.rev)
       counts, dest, unmatched, plan = {"fw": 0, "work": 0}, {}, [], []
       for record in git(a.src, "ls-tree", "-r", "-z", "--full-tree", a.rev).decode("utf-8").split("\0"):
           if not record:
               continue
           meta, path = record.split("\t", 1)
           mode, _, sha = meta.split()
           rule = next((r for r in table if matches(r[0], path)), None)
           if rule is None:
               unmatched.append(path)
               continue
           glob, side, to = rule
           counts[side] += 1
           if a.list == side:
               print(path)
           if side == "fw":
               target = to + path[len(prefix(glob)):] if to.endswith("/") else to
               if target in dest:
                   sys.exit(f"collision: {path} and {dest[target]} both go to {target}")
               dest[target] = path
               plan.append((mode, sha, target))
       print(f"fw {counts['fw']}, work {counts['work']}, unmatched {len(unmatched)}", file=sys.stderr)
       for path in unmatched:
           print(f"unmatched: {path}", file=sys.stderr)
       if unmatched:
           sys.exit(1)
       if a.check or a.list or not a.dst:
           return
       for mode, sha, target in plan:
           if mode not in ("100644", "100755"):
               sys.exit(f"not a plain file (mode {mode}): {target}")
           out = Path(a.dst, target)
           out.parent.mkdir(parents=True, exist_ok=True)
           out.write_bytes(git(a.src, "cat-file", "blob", sha))
           out.chmod(0o755 if mode == "100755" else 0o644)
       print(f"wrote {len(plan)} files under {a.dst}", file=sys.stderr)


   main()
   ```

2. **Check, then apply:**
   ```bash
   python3 $HEP/.setup/movemap.py --src ~/Github/High-Energy --check          # → fw N, work M, unmatched 0
   python3 $HEP/.setup/movemap.py --src ~/Github/High-Energy --dst $HEP/HEimdall
   ```
   Record N and M in `[step."P1.S1"] rows`. An unmatched path is a gate: a new top-level folder or
   file landed after 2b. Propose a rule for it in 01 §7, and do not guess.
3. **Make the repo:**
   ```bash
   git -C $HEP/HEimdall init -b main
   ```
   Nothing is committed yet; S2 makes the one import commit.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `python3 $HEP/.setup/movemap.py --src ~/Github/High-Energy --check 2>&1 \| tail -1` | `fw N, work M, unmatched 0`, where N + M = `git -C ~/Github/High-Energy ls-files \| wc -l` at `split/base` (204 + 1363 = 1567 at 9cb907a) |
| R2 | `find $HEP/HEimdall -type f -not -path '*/.git/*' \| wc -l` | N |
| R3 | `cd $HEP/HEimdall && LC_ALL=C ls -1F \| tr '\n' ' '` | `CLAUDE.md Makefile apps/ bin/ bots/ docs/ env/ kit/ pytest.ini runner/ schema/ stack/ tests/ tools/` |
| R4 | `cd $HEP/HEimdall && find . -type f -perm -u+x -not -path './.git/*' \| sort \| tr '\n' ' '` | `./bin/hep ./bin/run ./env/flags.sh ./stack/build_stack.py ./stack/mac/build.sh ./stack/mac/launch.sh` |
| R5 | `diff <(git -C ~/Github/High-Energy show split/base:utils/Env/runner/tools.py) $HEP/HEimdall/runner/tools.py && echo same` | `same` (a file from git, not the worktree) |
| R6 | `ls $HEP/HEimdall/tools \| wc -l` | `16` (the plugin folders, 01 §3) |

**On failure:** R2 ≠ N means a write failed half-way. Delete `$HEP/HEimdall` (made in this step,
so no gate is needed) and run the step again.

---

## S2: the new files, the fixture work dir, the import commit

**Preconditions:** S1 `done`.

**Tasks:**

1. **`.gitignore`**:
   ```
   build/
   __pycache__/
   .pytest_cache/
   ```
2. **`README.md`**, about 40 lines:
   - what HEimdall is (the framework of 01 §1, in two sentences);
   - where it lives (`$HEP/HEimdall`) and how it is installed (`stack/README.md`, then `source
     $HEP/setup.sh`);
   - the folders (01 §3's table, shortened);
   - "make a work dir: `hep setup <dir>`";
   - the manual (`docs/README.md`);
   - that its history before the seeding is High-Energy's (`split/base`, with the revision).
3. **`CLAUDE.md`** comes from High-Energy's `bots/BOT.md`, which the map put there. Rewrite only:
   - **the directory table:** HEimdall's folders (01 §3) instead of the repository's;
   - **paths** in the text: `utils/Env/runner/` → `runner/`, `utils/Env/<tool>/` → `tools/<tool>/`,
     `utils/*.hh` → `kit/`;
   - **the testing rules:** tests write only `build/scratch/` (01 §5.7). The rule "never write into
     `results/` or `configs/`" becomes "never name a real work dir in a test".

   Every rule BOT.md has stays a rule.
4. **The fixture work dir** (01 §5.7). The map already put `configs/` and `README.md` there.
   - Write `tests/fixtures/work/hep.toml`:
     ```toml
     # hep.toml — the tests' work dir (01_Target.md §5.7). Frozen: changed only with the test that needs it.
     [work]
     name = "fixture"

     [framework]
     expects = ""
     ```
   - Copy the modules from git:
     ```bash
     git -C ~/Github/High-Energy archive split/base modules | tar -x -C $HEP/HEimdall/tests/fixtures/work
     ```
   - Copy the dataset from what was kept:
     ```bash
     mkdir -p $HEP/HEimdall/tests/fixtures/work/datasets
     cp $HEP/.setup/kept/datasets/zeus_eic.yoda $HEP/HEimdall/tests/fixtures/work/datasets/
     ```
   - Add one paragraph to `tests/fixtures/work/README.md`: the modules are frozen copies of
     High-Energy's `modules/` at `split/base`; the dataset is `datasets/zeus_eic.yoda` (sha256
     `625723465b10ea69…`); and the old paragraphs' `HEKIT_CONFIGS` becomes `HEP_WORK` (01 §5.7).
5. **The import commit.** Stage by path (`git add .` is allowed here only, because everything in
   the tree is this step's own), then:
   ```bash
   git -C $HEP/HEimdall add .
   git -C $HEP/HEimdall commit -m "P1: HEimdall seeded from High-Energy split/base ($(git -C ~/Github/High-Energy rev-parse split/base))" -m "<the attribution line>"
   ```
6. **From now on, read the plans from `$HEP/HEimdall/docs/framework/`** (02 §1).

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `git -C $HEP/HEimdall rev-list --count HEAD` | `1` |
| R2 | `git -C $HEP/HEimdall log -1 --format=%s \| grep -c "$(git -C ~/Github/High-Energy rev-parse split/base)"` | `1` |
| R3 | `git -C $HEP/HEimdall status --porcelain \| wc -l` | `0` |
| R4 | `find $HEP/HEimdall/tests/fixtures/work/modules -type f \| wc -l` | the number of `modules/` paths at `split/base` (`18` at 9cb907a) |
| R5 | `python3 -c "import tomllib; print(tomllib.load(open('$HEP/HEimdall/tests/fixtures/work/hep.toml','rb'))['work']['name'])"` | `fixture` |
| R6 | `git -C $HEP/HEimdall ls-files \| wc -l` | N + 3 (`.gitignore`, `README.md`, `hep.toml`) + R4 + 1 (the dataset) |
| R7 | `grep -c 'utils/Env' $HEP/HEimdall/CLAUDE.md` | `0` |
| R8 | `diff -r ~/Github/High-Energy/docs/framework $HEP/HEimdall/docs/framework && echo same` | `same` (if the clone is still at `split/base`) |

**On failure:**
- R6 off by a few: list the difference with `git ls-files` against the map's `--list fw` and the
  new files. Do not commit a fix-up silently; amend the import commit (it is still the only one).
