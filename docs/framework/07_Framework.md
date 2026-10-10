# 07 — P4: The framework built, tested and documented

**Goal.** Heimdall, after the seam, passes everything it passed in High-Energy:
- the C++ tests and the fast suite (S1);
- the slow suite with its physics gates (S2);
- a manual that describes the split, its generated blocks current (S3).

**Reads:**
- 07 §8 of the manual (the gates' numbers), copied here as rows;
- 01 §6.6 (C69–C71).

**Writes:** Heimdall (`framework/Apps/`, `forge/`, the manual, the record), one commit per step.

**Gates:**
- a gate row that differs from its number twice (S2);
- nothing else is expected.

---

## S1: the build and the fast suite

**Preconditions:**
- P3 is verified.
- `source $HEP/setup.sh`.
- `git -C $HEP status --porcelain` is empty.

**Tasks:**

1. `hep build --framework --tests`: the apps, Herwig's repository and the C++ tests.
2. `make -C $HEP test`: runs the C++ tests, then `pytest -m "not slow"`. Collect the
   summary line and every skip with its reason (`-rs`).
3. Compare with P3 S3 R1. The counts must match: S1 adds no test.

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `ls $HEP/forge/tests/*.exe \| wc -l` | `3` (test_kit, test_module_kit, test_status) |
| R2 | `for t in $HEP/forge/tests/*.exe; do $t >/dev/null \|\| echo FAIL $t; done \| wc -l` | `0` |
| R3 | `cd $HEP && python3 -m pytest -q -m "not slow" -rs -p no:cacheprovider 2>&1 \| tail -1` | `N passed[, K skipped]`, 0 failed, 0 errors; N equal to P3 S3 R1's |
| R4 | `cd $HEP && make docs && make schema && git status --porcelain \| wc -l` | `0` (the generated blocks and the editor schema were current) |

**On failure:** a test that passed in P3 and fails now means the build changed something. Bisect by
`git -C $HEP log`. No test is ever skipped to pass the row.

---

## S2: the slow suite and the physics gates (background)

**Preconditions:** S1 `done`. Nothing else heavy runs: the slow suite uses many cores (02 §8).

**Tasks:**

1. As the builder: `cd $HEP && nohup make test-slow > $HEP/.setup/slow.log 2>&1 &`. Watch
   for its summary.
2. Read the gates' outcomes into the rows below. They are the manual's 07 §8, measured on the lab PC
   by these same tests.

**Verification:**

| # | Gate (test) | Expected |
|---|---|---|
| R1 | the whole slow suite: `tail -1 $HEP/.setup/slow.log` | `N passed`, 0 failed, 0 errors |
| R2 | App_Pythia at 1 thread against the legacy pipeline (`test_gates_p1.py`) | byte-identical YODAs (0 of 1,530 lines differ); σ = 71,422.158 pb |
| R3 | σ at 4 threads, 100k events (`test_gates_p1.py`) | Rivet's `/_XSEC` against the sidecar's: relative difference ≤ 1e-8 |
| R4 | failure injection (`test_failures.py`) | no hang, the right tool blamed, no `.complete` |
| R5 | Lambda, the module program against the Rivet analysis (`test_modules_p4.py`) | 21 histograms, 3,906 values equal |
| R6 | InprocJets against the chain (`test_modules_p4.py`) | all 17 objects equal bin for bin at 1 thread; σ equal at 4 threads |
| R7 | sharded against unsharded (`test_gates_shards.py`) | raw sums and σ equal to 1e-9 |
| R8 | four Rivets on threads against one (`test_modules_p4.py`) | every raw sum and final bin equal; σ equal |
| R9 | replicas combined (`test_gates_combine.py`), points in parallel (`test_gates_parallel.py`) | as the tests assert |
| R10 | Delphes (`test_generators_p4.py`) | the tree's entries = the sidecar's written (2,000) |

**R2 on a new compiler.** R2 compares against `tests/reference/legacy_run`, which was produced on
the lab PC with GCC 13 and its libm. A newer GCC, or a newer glibc's `libm`, can change Pythia's
floating point in the last bits, and with it the events.
- **If R2 fails while R3–R10 pass**, it is a gate. Report the number of YODA lines that differ, σ
  against 71,422.158 pb, and the largest relative bin difference. Then wait: the user decides
  whether the reference is re-recorded (a new V-row in the record) or the difference is pursued.
- Never regenerate `tests/reference/` without that decision (BOT.md, `CLAUDE.md`).

---

## S3: the manual for the split

**Preconditions:** S2 `done`, or waiting at its R2 gate. The manual does not depend on R2.

**Tasks:**

1. **The pages** (C69). Rewrite what describes the layout, the environment and the build, by 01
   §1–§5. The sections are:
   - 01 (layout);
   - 02 §1 (set up and build: `load_hep`, `hep build --framework`, `hep setup`) and §12 (a new
     project, now inside a work dir, `hep setup --project`);
   - 05 §2 (the environment, `hep build` and `make`, the variables table of 01 §5.1; the new
     commands `setup` and `where`);
   - 06 §1 (layout: Heimdall and work dirs), §2 (components, re-rooted), §14 (where files go: the
     work dir; Heimdall's `stack/ forge/ stash/`), §15 (the build: `Makefile` and
     `framework/work.mk`, per-tree flags), §16 (tool folders under `framework/tools/`), §25 (tests:
     the fixture work dir, `forge/scratch/`).

   Apply the renames of 06's table everywhere else in the pages, including `docs/framework/` (its
   links to `../stack/mac/…` become `../../platforms/mac/…`), `docs/stack/` and `docs/reporter/`.
2. **The record** (C70). Add V-rows from V105, each citing its D-rows here:

   | V-row | Covers |
   |---|---|
   | V105 | Heimdall in `$HEP` (D1, D2, D10, D17) |
   | V106 | work dirs, `hep.toml` and `hep setup` (D3, D4, D14, D18, D25) |
   | V107 | names and placeholders (D6, D7, D19; K15 closed) |
   | V108 | the build split and per-tree flags (D5, D21) |
   | V109 | Python through `heimdall.pth` (D22) |
   | V110 | tests on the fixture work dir (D9, D23) |
   | V111 | provenance with two revisions (D8) |
   | V112 | portability: the macOS spots, and the socket file there (D11) |
   | V113 | High-Energy as the first work dir (D15) |

   Add an L-row for anything P2–P4 learned the hard way (a package that needed a flag on the new
   OS, R2's outcome).
3. **The index** (C71): `docs/README.md` lists `docs/stack/`, `docs/reporter/` and `docs/framework/`,
   and its reading paths start at Heimdall's `README.md`.
4. `make docs && make schema`, then commit: `P4.S3: the manual and the record for the split
   (V105–V113)`.
5. Write the link checker the rows use, `$HEP/.setup/links.py`. Code is stripped first, as
   `test_docs.prose()` does, because a deck's `![](block)` example is not a link. It was tested on
   High-Energy's `docs/` at 9cb907a and on `docs/framework/` at 2c (0 broken):
   ```python
   #!/usr/bin/env python3
   """links.py ROOT: every relative link in every .md under ROOT that does not resolve (ignored trees left out)."""
   import re, sys
   from pathlib import Path
   root = Path(sys.argv[1])
   bad = []
   for page in sorted(root.rglob("*.md")):
       if {"build", ".git", "stack", "forge", "stash", "venv", ".setup", "Apps"} & set(page.relative_to(root).parts):
           continue
       text = page.read_text(encoding="utf-8")
       prose = re.sub(r"`[^`\n]*`", "", re.sub(r"^[ \t]*```.*?^[ \t]*```", "", text, flags=re.M | re.S))
       for target in re.findall(r"\]\(([^)\s]+)\)", prose):
           name = target.partition("#")[0]
           if name and not re.match(r"[a-z]+:", target) and not (page.parent / name).exists():
               bad.append(f"{page.relative_to(root)}: {target}")
   print(len(bad), *bad, sep="\n")
   ```

**Verification:**

| # | Command | Expected |
|---|---|---|
| R1 | `cd $HEP && grep -rn 'utils/Env\|utils/App\|utils/Status\|utils/Module\|HEKIT_' docs/0[1-6]*.md docs/README.md \| wc -l` | `0` (07, the record, keeps its history as written) |
| R2 | `cd $HEP && python3 -m pytest -q tests/runner/test_docs.py -p no:cacheprovider 2>&1 \| tail -1` | `N passed`, 0 failed |
| R3 | `python3 $HEP/.setup/links.py $HEP \| head -1` | `0`: every relative link in every page resolves, including `docs/stack/`, `platforms/`, `docs/reporter/` and `docs/framework/` |
| R4 | `grep -c '^| \*\*V1[01][0-9]\*\*' $HEP/docs/07_Record.md` | ≥ `9` (V105–V113) |
| R5 | `git -C $HEP status --porcelain \| wc -l` | `0` |
