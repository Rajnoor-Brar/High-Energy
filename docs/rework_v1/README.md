# rework_v1 — the framework as built, and why

A reference for the system that exists, and a case study for the next overhaul.

Written 2026-09-21, against `rework/v1` (`ddfeb40`); updated 2026-09-23. It describes the state
after the `docs/rework` plan was executed — 54 of 55 steps, 11 phases, one blocked on an unanswered
question — and the work done on top of it since (§ *After rework/v1*).

---

## What this is, and what it is not

There are now three sets of documents about the rework, and they answer different questions.

| | Question | Written |
|---|---|---|
| [`docs/rework/`](../rework/) | *What should we build?* | before, 15 design documents + 55 step files |
| [`docs/post_rework/`](../post_rework/) | *Is the result well structured?* | after, measured from the tree |
| **`docs/rework_v1/`** (this) | *What is it, why is it that way, and how would I do this again?* | after, distilled |

The design documents are a **record of intent** and in eleven places the code corrected them
(listed in [rework/README.md](../rework/README.md#where-the-design-was-wrong)). Where they disagree
with the code, the code is right. This set is written from the code.

For *using* the system see [GUIDE.md](../GUIDE.md). For *where things live* see
[MAP.md](../MAP.md). This set is for the reader who has to change it, extend it, or do the same
thing again to a different codebase.

---

## The documents

| | |
|---|---|
| **[01_Philosophy.md](01_Philosophy.md)** | The principles the whole thing follows, and what each one actually buys. Read this first; everything else is a consequence. |
| **[02_Design.md](02_Design.md)** | The architecture as built: two halves, one narrow contract, how data moves, where the boundaries are and why they are there. |
| **[03_Conventions.md](03_Conventions.md)** | Naming, folders, C++ style, Python style, config, tests. The rules you must follow to add something without breaking the shape. |
| **[04_Decisions.md](04_Decisions.md)** | The 23 decisions, what each gave up, and — the part a plan cannot have — whether it held up. |
| **[05_Process.md](05_Process.md)** | How the overhaul was actually run: audit-first, step files, logs, approval rules. The reusable method. |
| **[06_Lessons.md](06_Lessons.md)** | What the 39 findings and two blown estimates taught. What to do differently next time. |
| **[07_Glossary.md](07_Glossary.md)** | Every term, what it means here, and the alternatives — including the two renames of 2026-09-23. |

---

## The headline numbers

| | |
|---|---|
| Replaced | `utils/` at 10,404 lines + four unversioned `~/HEP` scripts |
| Built | **6,837** lines C++ (11 namespaces) + **16,853** lines Python (12 packages) |
| Tests | **32** ctest targets, **770** Python tests, 15,798 lines of test code |
| Commands | 19, one entry point (`hep`) |
| Plan | 55 steps in 11 phases; **54 done**, 1 blocked on an open question |
| Findings | **44** catalogued defects (`00/B1`–`B44`); 9 found by building the rework, **5 more** by building the Lambda example on top of it |
| Decisions | 23 logged with what each gave up |

**Two estimates were badly wrong**, and both are recorded as misses rather than smoothed over:
the Python half was budgeted at ~4,000 lines and came in at 13,261 (3.3×), and the "thin
orchestrator, heavy runner" picture inverted into a heavy orchestrator and a lean runner. See
[06_Lessons.md](06_Lessons.md).

---

## The one-paragraph version

Everything that needs **judgement** happens in Python, once per run: configuration, sweeps, seeds,
paths, supervision, plotting, provenance. Everything that touches an **event** happens in C++, in
one executable that knows nothing about configuration files. Between them is a contract narrow
enough to write down in a sentence — a resolved TOML spec in, JSON-lines status on file descriptor
3 out — which is what lets either half be tested without the other, and why `hep-run` links no
ROOT, no plotting library and no config parser.

---

## After `rework/v1`

What has changed since the tag, in order. Each is described where it belongs; this is the index.

### The Lambda example

The legacy `Lambda` module (839 lines, nine headers, four `main()`s) was rebuilt on the framework as
a worked example — and then built **a second time** as a Rivet analysis, sharing one reconstruction
header:

| | |
|---|---|
| `modules/Lambda/Reconstruction.hh` | the physics: pairing, mass window, cos θ*, greedy matching |
| `modules/Lambda/Lambda.cc` | the same, as a `Module::Base` |
| `analyses/Lambda/Lamriv.cc` | the same, as a `Rivet::Analysis` |
| `configs/Lambda/lambda.toml` | one config, seven studies |
| `tests/cxx/test_lambda.cc`, `tests/integration/test_lambda_paths.py` | 8 + 23 tests |

Both paths run in one job and write into one `analysis.yoda`, and `lambda_paths` holds them to exact
agreement — 21 histograms, floating-point tolerance, because it is one sample written twice rather
than two samples compared. See [modules/Lambda/README.md](../../modules/Lambda/README.md).

**That comparison is the point.** It found `00/B42` immediately, and nothing else would have.

### New capability

- **`[proc.export]`** — `hep proc` writes a point's histograms to `analysis.root` beside its
  `analysis.yoda`. YODA stays the record (D7/D14) and `hep-run` still links no ROOT (D15); the ROOT
  file is a derived view. Written with `uproot`, so it works without PyROOT.
- **`Phys` is usable from a Rivet plugin.** `rivet-build` now gets
  `-I utils -I modules/<project> -DHEKIT_WITH_HEPMC=1`, which is what lets an analysis and a module
  share one physics header.

### Five new findings

| | | |
|---|---|---|
| `00/B40` | a module's options cannot be swept | recorded |
| `00/B41` | `hep build --modules <project>` never worked, for any project | **fixed** |
| `00/B42` | module and Rivet histograms land in one file with different normalisation conventions | worked around + test |
| `00/B43` | an option sweep draws every variant on every curve | recorded |
| `00/B44` | editing a `.info` or `.plot` did not rebuild its copy | **fixed** |

`00/B41` and `00/B44` are the same shape as `00/B37`: a documented convention that had never been
exercised. Building a second example on top of the framework is what exercised them — which is the
argument for doing it at all.

### Two renames (2026-09-23)

`sink` → `analyzer` and `settle` → `static`, complete across C++, config, spec, tests and docs.
[07_Glossary.md §8](07_Glossary.md) records what moved and the two things worth revisiting.
