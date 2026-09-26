# 05 — How the overhaul was run

The method, as a reusable procedure. This is the part of the rework most worth copying, because it
is independent of the codebase it was applied to.

The system replaced 10,404 lines of C++ and four unversioned shell/Python scripts with 23,690 lines
across two languages, in 55 steps, without a period where nothing worked.

---

## 1. The shape

```
  audit ──► design ──► roadmap ──► step files ──► execute one at a time ──► audit again
  00       01–13      10          55 files       logs + verification       post_rework/
  ▲                                                                              │
  └──────────────────── findings feed back as citations in code ◄────────────────┘
```

Four artefacts, each with one job:

| Artefact | Job |
|---|---|
| **`00_Audit.md`** | What exists, what is wrong with it, with file-and-line evidence. 39 catalogued findings. |
| **`01`–`13`** | The design, one document per concern. Written *before* any code. |
| **`10_Roadmap.md`** | Phases, decision log, risk register, open questions. |
| **`steps/`** | 55 files, one per step, each executable by someone who has read nothing else. |

---

## 2. Audit first, and cite it forever

The audit came before the design, and it produced **evidence, not opinions**. Every finding is a
row with three columns:

| | |
|---|---|
| **What** | `Physics::particle(-211).charge3` was `+3` — the lookup resolved an antiparticle to its particle's row and handed back that row's charge |
| **Evidence** | `legacy/utils/Physics/Particles.hh:48-56` |
| **What was done** | Fixed in P8-S02: the table still keys on \|id\|, but `charge3(id)` carries the sign of the code given |

**Findings are cited from the code at the point they constrain it**, permanently. `Phys::deltaPhi`
carries `00/B35`; `Analyzer::Modules` carries `00/B31` and `00/B36`; the ONNX include path carries
`00/B37`. When a verification row later demanded that a grep for those citations be *empty*, the row
was recognised as wrong — deleting them would delete the record of why the code has its shape.

**Nine of the 39 findings were discovered by building, not by reading.** An audit gets you the
first thirty; the last nine cost a working system. Plan for them.

---

## 3. One file per step

A step file is self-contained and has a fixed anatomy:

```
# P8-S02 — Phys namespace

| Status | Kind | Phase | Depends on | Blocks | Effort | Findings / decisions | Updated |

## Goal          one paragraph
## Context       why now
## Inputs to reuse   what exists already — explicitly, to prevent rewriting
## Scope         in and out, both stated
## Design notes  links into 01–13
## Tasks         the work
## Outputs       files this step creates or changes
## Verification  rows that must pass, each producing a NUMBER
## Rollback      how to undo it
## Done when     the exit condition
## Log           ← filled during execution: measurements, deviations, surprises
```

The execution protocol, unchanged for all 55:

1. Read the step file and the design sections it links.
2. **Mirror it into a working-plan file** and mark it in-progress in *both* the step file and the index.
3. Do the work; note deviations in the **Log** as they happen.
4. Run **every** verification row; attach the numbers to the Log.
5. Update the docs the step names.
6. Mark done in *both* places.

**Why "both places" matters.** The index is what a reader sees; the file is where the detail is. A
status that lives in one place drifts. It is a small rule and it survived 55 iterations.

### The Log is the product

Everything a retrospective needs comes from the Logs: the measurements, the eleven places the design
was wrong, the two verification rows that had to be replaced, the reason a deferral was a decision.
This document could not be written without them.

---

## 4. Verification produces numbers

A verification row that can be satisfied by looking at the code is not a verification row. The rows
that worked produced measurements:

- 92 µs/event locked against 124 µs/event fully serial → justified the `Locked` concurrency mode;
- the σ combination reproduces `sigmaGen()` exactly and agrees with a serial `stat()` within
  statistics → retired a risk;
- χ²/ndf 12.5 (`L-BFGS-B`) against 0.835 (`least_squares`) → changed the fit backend;
- exact totals at 1, 4 and 20 threads → proved the scaling contract.

### Two rows were untestable as written, and were replaced

Recorded here because the *handling* is the transferable part:

**P9-S01, "fitted parameters within 1σ."** Flaky by construction: five parameters, one seed, ~30%
failure. Replaced by |pull| < 3 on each parameter plus a 20-seed pull-RMS test — which tests the
thing the row *meant* (the fit is unbiased) instead of the thing it said.

**P10-S01, "the grep for finding citations is empty."** It cannot be, and making it so would delete
the record of why the code is shaped as it is. Replaced by an AST check, and the substitute was
proven to discriminate before being accepted.

In both cases the substitution was **argued in the Log**, not quietly performed. A silently
weakened check is worse than a failing one.

---

## 5. Replacement before removal

Nothing was deleted before its replacement passed a comparison **against it**.

The ordering that is easy to get wrong:

1. Move the old tools into the repository (D18) — versioned, runnable, hotfixable.
2. **Capture golden fixtures** from them, as they are.
3. *Then* hotfix their physics-relevant bugs (D19), and write down the expected deltas.
4. Build the replacement; compare against the fixtures.
5. Retire the old tool only when the comparison passes on a real study.

Hotfixing before step 2 makes the fixtures agree with the new behaviour by construction and proves
nothing. The plot transform layer is explicitly "a port and not a redesign" for this reason, with
its tests comparing both implementations while both existed.

---

## 6. Phases end in a working state

Eleven phases, each with its own exit criteria, each ending somewhere usable. There was never a
window where the repository did not build and run.

This constrains the ordering more than it looks: it is why the CLI arrived in P1 (before most of
what it calls, with `NotImplementedYet(command, step)` as the placeholder) and why the old tools
stayed on until P4-S06.

**`NotImplementedYet` is a pattern worth stealing**: a command that is planned but absent raises an
error naming the step that will deliver it, rather than being missing from `--help`. The shape of
the finished system is visible from the first phase.

---

## 7. Approval boundaries, stated once

A small set of actions required explicit sign-off, fixed at the start:

- commits, tags, and any move of `results/`;
- edits to the working-plan files and to the installed `~/HEP` stack.

Standing approvals were granted once and then relied upon (local per-step commits, never pushed).
The value is not ceremony — it is that **the boundary was decided before the work**, so no
individual decision had to be negotiated under time pressure.

The one place this mattered most: `00/B39` was found *after* `rework/v1` was tagged. The fix is one
line. It was recorded and **not applied**, so the tag points at exactly what was measured. That is
only a clean call because the rule already existed.

---

## 8. Test safety as a rule, not a habit

> Tests and dry runs never write into `results/` or `configs/`.

Enforced by a pytest guard from the first phase, with `output/scratch/` and `HEKIT_RESULTS` as the
sanctioned destinations, and legacy tools run from a scratch CWD with symlinked inputs.

It caught a real one: my own `hep doctor --refresh` in a stripped shell poisoned the user cache and
broke an unrelated test (`00/B38`). The guard did not prevent it — a cache outside both directories
was not covered — but the *discipline* meant the breakage was legible instead of mysterious, and the
result was a fix (an `env_key` over install root, `PATH` and `PYTHONPATH`) plus a regression test.

---

## 9. Audit the result

[`post_rework/`](../post_rework/) measures the finished tree the same way `00_Audit.md` measured the
old one: sizes, both dependency graphs, cycles, duplication — **from a script over the tree, not
from reading**.

It found what a self-assessment would not have: the C++ half is clean and the Python half is not,
and the difference is enforcement rather than discipline. It also caught an overstatement in its own
first draft ("three value types, 14 lines" → verification showed two types, 9 lines), which is the
argument for measuring rather than recalling.

**Close the loop.** The audit that starts the next overhaul should be the audit that ended this one.

---

## 10. The procedure, condensed

1. **Audit with evidence.** File and line. Number the findings. Expect to find a quarter more while building.
2. **Design before code**, one document per concern, and accept that reality will correct ~20% of it.
3. **Log the decisions with what each gives up.** A decision without a cost is a preference.
4. **One self-contained file per step**, with verification rows that produce numbers.
5. **Keep the old thing running** until the new one beats it on a real comparison.
6. **Every phase ends working.**
7. **Write the Log as you go.** It is the only durable artefact of *why*.
8. **Say the number when it is bad.** Two estimates here were out by 3×, and recording that is worth
   more than either number.
9. **Measure the result, don't assess it.**
10. **Enforce the rules you can** — a layering in a link graph held; the same layering in a document
    did not exist, and the half without it has four cycles.
