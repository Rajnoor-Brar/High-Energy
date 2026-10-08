# 02 — How the agents work

The protocol every agent follows while carrying out the phase files on a machine:
- who does what;
- where progress is kept;
- how a step is run and verified;
- when to stop and ask;
- how to report.

It is written for Claude Code, the user's tool, but nothing in it depends on Claude Code: a person
can follow the same files by hand. [README](README.md) §5 is the summary; this page is the rule.

---

## 1. Starting on a fresh machine

The fresh machine is the lab PC, reinstalled (D16). The user does four things by hand, before any
agent starts:

1. Install the OS, `git`, `python3` (3.11 or newer) and Claude Code.
2. Put the files kept before the wipe (01 §8) somewhere readable, such as a mounted disk.
3. Clone High-Energy and check out the branch these plans were pushed with:
   ```bash
   git clone https://github.com/Rajnoor-Brar/High-Energy.git ~/Github/High-Energy
   cd ~/Github/High-Energy && git checkout rework        # or: git clone HE.bundle …
   ```
4. Start Claude Code in `~/Github/High-Energy` and give it the start prompt (§11.1).

Everything after that is the orchestrator's.

**Where the plans are read from:**
- in P0 and P1, from the High-Energy clone (`docs/framework/`);
- from P1's end, from `$HEP/HEimdall/docs/framework/`, which is identical at that point.

The deviations of §7 are committed there, so the next machine gets them.

---

## 2. Roles

| Role | Is | Does | Never |
|---|---|---|---|
| **Orchestrator** | the main session | reads the plans and the state; runs steps inline; starts the long jobs; asks at gates; writes `state.toml` and `log.md`; reports | marks a phase done without the verifier; works past a gate unanswered |
| **Builder** | a background process the orchestrator starts and watches (in Claude Code: a background shell plus a monitor on its log) | the long jobs only: the stack build (P2) and the slow test suite (P4) | runs anything interactive; asks for sudo; it inherits no approvals |
| **Verifier** | a fresh agent with no shared context (in Claude Code: a subagent), read-only | re-runs a phase's verification rows exactly as written and returns the table of §5.3 | edits, builds or deletes; "fixes" a failing row; reads the orchestrator's log to decide a row |

**Talking to the user:**
- Only the orchestrator talks to the user.
- The verifier's table is relayed as it came back, and never summarised into a pass that was not
  there.

**Why a separate verifier:** the agent that did the work is the worst judge of it. v1's lesson (06
§2.1) is that what was written down and checked held, and the rest did not.

---

## 3. Where progress is kept

Everything per machine is in `$HEP/.setup/`, which is never in git:

| File | Holds | Written by |
|---|---|---|
| `state.toml` | each step's status and numbers; the machine; the choices; the gates; the deviations | the orchestrator only |
| `log.md` | one entry per event, newest last | the orchestrator only |
| `kept/` | the files kept before the wipe, copied in by P0 | P0 |
| `verify/<phase>/` | the verifier's scratch and its tables | the verifier |
| `movemap.py`, … | small scripts a step writes (the move map's applier) | the step that needs them |

P0's first action creates `$HEP/.setup/`. `$HEP` is `~/HEP` unless the user's start prompt names
another prefix.

### 3.1 `state.toml`

```toml
# $HEP/.setup/state.toml — HEimdall's setup on this machine. Written only by the orchestrator (02 §3).

[machine]                       # P0.S1
host = "Lab_PC"
os = "Ubuntu 26.04 LTS"
arch = "x86_64"
cores = 24                      # logical CPUs
ram_gb = 31
disk_free_gb = 412              # where $HEP is
sudo = true
network = true
docker = "absent"               # "usable", "installed, no group", "absent"; apptainer likewise
python = "3.13.2"
annex = "ubuntu"                # targets/<annex>.md

[source]                        # P0.S2
repo = "/home/rajnoor/Github/High-Energy"
branch = "rework"
revision = "…"                  # tagged split/base
kept = "/media/…/kept"          # where the user's copies were

[choices]                       # the plan's defaults, or what the user said
hep = "/home/rajnoor/HEP"
packages = "core"
cores = 20
root_cores = 10

[step."P2.S2"]
status = "done"                 # todo | running | done | failed | blocked
started = 2026-10-20T09:12:00Z
finished = 2026-10-20T12:47:31Z
rows = { "R1" = "ROOT 6.40.04", "R2" = 21 }    # each verification row's number or text
verified = "P2"                 # the phase whose verifier passed it (set at the phase's end)
note = ""

[[gate]]
step = "P2.S1"
asked = 2026-10-20T09:01:10Z
what = "sudo apt-get install: 61 packages, 1.2 GB"
answer = "yes"                  # the user's words, short

[[deviation]]
step = "P2.S1"
planned = "apt: libpcre3-dev"
did = "apt: libpcre2-dev (libpcre3-dev has no candidate on 26.04)"
allowed_by = "targets/ubuntu.md §allowed adjustments"
folded = ""                     # the HEimdall commit that put it into the plan files, once done
```

**Resuming:**
- Read `state.toml`, then take the first step that is not `done`.
- Re-run that step's **preconditions**. They decide whether its partial work is reusable: the
  stack's stamps make P2 resumable on their own (stack/README §1).
- A `running` step found on resume means the session died. Treat it as `failed`, collect what is
  there (§5.2), and run it again.

### 3.2 `log.md`

One line per event, plus at most a few lines of detail, so the whole story fits on a screen:

```
2026-10-20 09:01  P2.S1  GATE   sudo apt-get install (61 packages, 1.2 GB) — asked
2026-10-20 09:03  P2.S1  GATE   answered: yes
2026-10-20 09:12  P2.S2  START  build_stack.py packages=core cores=20 root_cores=10 (background)
2026-10-20 12:47  P2.S2  DONE   14 packages stamped; R1 ROOT 6.40.04; R2 21 PDF sets
2026-10-20 12:50  P2     VERIFY 7/7 rows pass (verify/P2/table.md)
```

---

## 4. The step loop

The orchestrator repeats, until P6 is verified:

1. **Pick** the next step: the first `todo` (or `failed`) step whose phase's earlier steps are
   `done`. P3 may start while P2's build runs (§8). Anything else is in order.
2. **Preconditions:** run them. One that fails means "not yet": report which, and either wait (a
   build still running) or go back to the step that should have made it true.
3. **Gates:** if the step's tasks touch a gate (§6), ask before the first such task and wait.
4. **Tasks:** do them as written, in order. Commands are copied, not paraphrased. Edits are made at
   the file:line the step names; when the line has moved, find it by the quoted text, not by
   guessing.
5. **Commit** (HEimdall from P1 on; High-Energy's `work` branch in P5): stage by path, never `-a`.
   The message is `P<n>.S<m>: <what>`, with the attribution line the session is configured for.
6. **Verify:** run the step's rows (§5) and record each number in `state.toml`.
7. **Record** `done`, with a log line. Then go to 1.

At a phase's last step, the verifier runs the whole phase (§5.3). The phase report (§9) goes out
only after it.

---

## 5. Verification

### 5.1 A row

Every step ends with rows of this shape (the phase files use it):

| # | Command | Expected |
|---|---|---|
| R1 | `root-config --version` | `6.40.04` |
| R2 | `lhapdf list --installed \| wc -l` | `21` |
| R3 | `hep where --work` (from `~/Github/High-Energy/configs`) | `/home/<user>/Github/High-Energy`, exit 0 |

**The rules:**
- The **command** is exact and runs from a stated directory, with `load_hep` done unless the row
  says otherwise.
- The **expected** value is a number, an exact text, or a stated tolerance (`σ within 3 % of
  12.4 nb`). "Works" or "looks right" is never expected.
- A row that cannot be run (a tool missing) is a **fail**, not a skip. Only a phase file may mark a
  row optional, and only with its reason.

### 5.2 A failing row

1. Collect: the command, its full output (to `verify/<phase>/` or the log), and the relevant log
   tails: `$HEP/logs/<package>.log`, pytest's summary.
2. If the cause is plainly transient, run it once more: a network timeout, or a download the
   annex's caveats list (MadGraph and ONNX Runtime URLs, Geant4 data).
3. A row that fails twice is a **gate**: report the two outputs and the probable cause, propose the
   fix, and wait.
4. Never change the expected value, the command or the plan file to make a row pass. If the plan is
   wrong, that is a deviation (§7), asked for or allowed by an annex.

### 5.3 The verifier's pass

At a phase's end, the orchestrator starts the verifier with the prompt in §11.2 and the phase file's
name. The verifier:
- **runs** every row of every step of that phase, exactly as written, from a clean shell
  (`load_hep` only);
- **writes** to `verify/<phase>/` and to the scratch the rows name (the tests' `build/scratch/`),
  and nowhere else;
- **returns** a table: `# · command · expected · got · pass/fail`;
- **adds** anything it noticed that no row covers, as a separate list;
- **changes** nothing.

**The phase is `verified`** when every row passes. Otherwise the failing rows go back through §5.2,
and the verifier runs again afterwards.

---

## 6. Gates

At a gate the orchestrator stops, asks in the form below, and waits. An approval covers that one
gate instance, never the next one of the same kind.

| Gate | Typically in |
|---|---|
| `sudo`, or any system package install or removal | P0, P2 (annex: system packages) |
| a download, with its list and total size (asked once per phase: the stack's tarballs; Geant4's ~4 GB of data) | P2 |
| a change to the user's account or groups (joining the docker group is the user's own action) | container annex |
| a deletion outside `$HEP/{src,build}` and `$HEP/.setup/verify` | any |
| a write to the High-Energy clone, except P5's commits on branch `work` | any |
| a change to the content of `configs/` or `modules/` (P5's diffs C65–C67, shown first) | P5 |
| `git push`, publishing a repo or an image anywhere | P5, P6 |
| a verification row failing twice | any |
| anything the plan files do not decide, or decide in a way that cannot be done here | any |

**The form:**

```
GATE P2.S1 — sudo apt-get install: 61 packages, about 1.2 GB (the list: $HEP/.setup/log.md, 09:01).
Why: the stack's system packages (stack/settings.toml apt_packages; targets/ubuntu.md).
If no: P2 cannot start; P3 can proceed meanwhile.
Approve? yes / no / change …
```

---

## 7. Deviations

When the machine differs from what a plan says, the orchestrator may make a **deviation**, but only
when:
- an annex lists it as an **allowed adjustment** (for example, an apt package renamed on a newer
  Ubuntu); or
- it is a plain mistake in a plan's command (a wrong path, a typo) whose fix changes nothing else.

Everything else is a gate.

**Every deviation:**
- is recorded in `state.toml` (`[[deviation]]`) and in the log;
- is named in the phase report;
- is folded back into the plan files in `$HEP/HEimdall/docs/framework/`, by a commit at the end of
  its phase, so that the next machine does not hit it.

---

## 8. Concurrency and the machine

**The rules:**
- **One stack build at a time.** ROOT's compilers need about 3 GB each (`root_cores`).
- **One pytest session at a time.** The basetemp `build/scratch/pytest` is wiped per session.
- **P2 and P3 overlap.** P3 needs only HEimdall's code. While P2 builds, P3 may run the unit tests
  that need no stack, and must not compile against the stack. The rest of P3's tests wait for P2.
- **During the build**, the orchestrator keeps CPU-heavy work off the machine: no parallel compiles
  and no slow suite. `cores` in the build was chosen with that in mind (`[choices]`).
- **The slow suite (P4)** runs as the builder, in the background, after the fast suite passes.

**Cores and RAM:** P0 records them. P2 chooses `cores` and `root_cores` from them, by
`stack/README`'s rules (one ROOT compiler per 3 GB). The choice is written to `[choices]` before
the build starts.

---

## 9. Reports

**At a phase's end**, after the verifier:

```
P2 done — verified 7/7 (verify/P2/table.md).
  ROOT 6.40.04 · Pythia 8.317 · Rivet 4.1.3 · YODA 2.1.3 · HepMC3 3.3.1 · FastJet 3.5.0 (patched) · 21 PDF sets
  deviations: 1 (libpcre3-dev → libpcre2-dev; annex-allowed; folded in a1b2c3d)
  took 3 h 35 min; 38 GB under $HEP
Next: P4.S1 (P3 verified at 11:20). No gate pending.
```

**At a gate:** §6's form. **When stopped** for any other reason: what was being done, what is known,
what is needed. Nothing else is said between reports, except to answer the user.

---

## 10. Rules carried over

These come from High-Energy's `bots/BOT.md` and the working agreements, and become HEimdall's
`CLAUDE.md` in P1.

- **Commits:**
  - stage named paths, never `git commit -a`;
  - one commit per step;
  - never push without the gate.
- **Tests** write only their scratch (`build/scratch/`). They never read or write a real work dir's
  `configs/`, `modules/` or `results/`. The fixtures and `tests/reference/` are never regenerated.
- **Text files** are read and written with `encoding="utf-8"` (L17: reading a YODA file resets the
  locale).
- **Before touching a tool's code or folder**, read its rows in the knowledge ledger
  (`docs/07_Record.md` §3).
- **The user's files are the user's.** `configs/` and `modules/` change only through P5's listed,
  shown and approved diffs.
- **The manual** stays generated where it is generated: after a schema `doc`/`notes`, `base.toml`
  comment or CLI help change, run `make docs` (and `make schema`) in HEimdall.
- **Plans are not code.** An agent following these files changes code only as a step's tasks say.
  Ideas found on the way go to `bots/intent.md`, not into the code.

---

## 11. Prompts

### 11.1 Start (the user gives it to the first session)

```
You are the orchestrator for setting up HEimdall on this machine, following the plan files in
docs/framework/ of this repository (High-Energy).

Read, in order: docs/framework/README.md, 01_Target.md, 02_Agents.md. Then read
$HEP/.setup/state.toml if it exists ($HEP is ~/HEP unless I say otherwise here).

Follow 02_Agents.md exactly: run the next step whose preconditions hold; stop at every gate of
02 §6 and ask me in its form; record every step in state.toml and log.md; have the verifier check
each phase before you report it done; never change a plan, a command or an expected value to make
a check pass — record a deviation (02 §7) or ask.

The files I kept before the reinstall are at: <path>.
Begin with P0 (03_Preflight.md), or resume where the state says.
```

### 11.2 The verifier (the orchestrator starts it at a phase's end)

```
You are the verifier for phase <P> of HEimdall's setup. You are read-only: do not edit, build,
install, commit or delete anything. You may write only to $HEP/.setup/verify/<P>/ and to the
scratch locations a row itself names.

Read $HEP/HEimdall/docs/framework/02_Agents.md §5 and the phase file <file>. Open a fresh shell,
run `source $HEP/setup.sh`, then run every verification row of every step of <P> exactly as written,
from the directory it states. Do not read $HEP/.setup/log.md or state.toml to decide a row.

Return a table: row · command · expected · got · pass/fail, and save it as
$HEP/.setup/verify/<P>/table.md. Then list anything you noticed that no row covers. Fix nothing.
```

### 11.3 Resume (any later session)

```
Resume HEimdall's setup as its orchestrator: read $HEP/HEimdall/docs/framework/README.md,
01_Target.md and 02_Agents.md (or docs/framework/ in ~/Github/High-Energy if HEimdall does not
exist yet), then $HEP/.setup/state.toml and the end of log.md, and continue by 02 §4.
```

---

## 12. The phases at a glance

The step names are 2b's to write. This table fixes their order, what overlaps, and the gates each
phase is expected to meet.

| Phase | File | Does | Background | Gates expected |
|---|---|---|---|---|
| P0 | `03_Preflight.md` | survey the machine and choose the annex; `$HEP/.setup/`; tag `split/base`; bring back `kept/` | — | sudo, if `git` or `python3-venv` are missing |
| P1 | `04_Seed.md` | `$HEP/HEimdall` from the move map (01 §7), the fixture work dir, `CLAUDE.md`; the import commit | — | none (writes only `$HEP`) |
| P2 | `05_Stack.md` | system packages; `stack/build_stack.py` with the annex's overlay; the stack's checks | the build | sudo/apt, downloads |
| P3 | `06_Seam.md` | C1–C64: the roots, the placeholders, the rename, the build split, the environment, `hep setup`/`hep where`, provenance, the tests, portability | — (overlaps P2) | none |
| P4 | `07_Framework.md` | `hep build --framework`; the fast suite, then the slow one, against the baselines; `make docs`; the manual rewritten (C69–C71) | the slow suite | none |
| P5 | `08_Workdirs.md` | High-Energy made lean on `work` (01 §4.3, C65–C67); a toy work dir by `hep setup --project`; independence | — | the user's file diffs; push of `work` |
| P6 | `09_Verify.md` | the physics gates; the baselines compared; handover (`CLAUDE.md`s, the final report, memory); publishing HEimdall | — | push / publish |
