# 01 — Philosophy

The principles the framework follows. Each one is stated, then justified by what it actually bought
— because a principle that cannot name what it paid for is decoration.

---

## 1. Put the boundary where the cost changes, not where the topic changes

The split is **not** "physics in C++, tooling in Python". It is:

> **C++** where an *event* is touched — generation, sinks, Rivet plugins, custom modules, inference.
> **Python** where a *file, process or person* is touched — configs, native cards, subprocesses,
> the terminal, plots, provenance.
> **Shell** only where the *calling shell* must change — environment and `cd` helpers.

The distinction that matters is **per-event versus per-run**. A 10M-event run calls Python a few
hundred times, once per chunk; it calls C++ ten million times. Anything whose cost is paid once can
be written in whichever language makes it clearest, and that is almost never C++.

**What it bought.** Strict TOML validation, subprocess supervision with a signal ladder, a live
dashboard and YODA plotting are each roughly a tenth of the code in Python. The previous all-C++
direction is why the old `utils/` was 10,404 lines and most of it was not physics.

**What it cost.** Two languages, two test suites, and one protocol to keep in sync. The protocol
turned out to be the cheap part (see §3).

---

## 2. Make the invalid state unrepresentable, not merely undocumented

Wherever a rule could be enforced by a *type* instead of a convention, it was.

The clearest case is the **scaling contract**. Histogram fills must carry raw weights during the
run, and scaling must happen exactly once at the end when σ and Σw are known. That could have been
a comment. Instead:

- `Results::Worker` has **no `scale()`**
- `Results::Final` has **no `fill()`**

so "scaled during the run" and "scaled twice" are not mistakes you can make. The rule is the shape
of the types.

The same instinct elsewhere:

- **Concurrency is a property of the sink**, not a global flag. A sink answers `Serial`, `Locked` or
  `Sharded`; `Run::Loop` asks every sink and decides. You cannot configure a run into a race.
- **Partial output has a different name.** An interrupted run writes `analysis.partial.yoda`, never
  a truncated `analysis.yoda`, so a partial result cannot be mistaken for a complete one (D22).
- **Module identity is the filename.** `ToyJets.cc` → `libhekit_ToyJets.so` → `HEKIT_MODULE("ToyJets", …)`
  → `[[sinks.module]].name = "ToyJets"`. The config and the build cannot drift.

**What it bought.** Three of the nine findings discovered during construction were *prevented from
recurring* by a type change rather than a test.

---

## 3. One narrow contract, written down, with a version

`hep` writes a **resolved spec** — every value already decided, no defaults left to interpret — and
reads a **status stream** of JSON lines on file descriptor 3. Nothing else crosses.

Three properties make it work:

- **Resolved means resolved.** `threads = 0` meaning "hardware concurrency" is turned into an
  integer in Python and never passed on. `hep-run` has no defaults to disagree about.
- **The message set is closed but extensible.** Nine kinds; an unknown kind is logged and ignored,
  so the protocol can grow without breaking an older reader.
- **stdout is not the channel.** Structured status goes to fd 3; stdout and stderr stay available
  for tool chatter, which means a generator's noise can never corrupt the protocol.

**What it bought.** The audit looked specifically for duplicated logic across the language boundary
and found **none**: `run/status.py` (275 lines) and C++ `Status/` (469 lines) are two halves of one
contract, not two implementations of one idea. A narrow interface is the thing that made a
two-language codebase cost less than a one-language one.

---

## 4. Everything optional is actually optional

Pythia is the only hard requirement. Rivet, HepMC3, ONNX and Delphes are `AUTO` — on when found,
off when not — and **a build with all of them off still produces a working `hep-run`**. That is a
tested property, not an aspiration.

**What it bought.** Portability was verified rather than hoped for (P10-S03), and the discipline
kept the dependency graph honest: a feature that cannot be switched off is a feature that has
leaked into the core.

**Where it is not yet true.** The module build is guarded on `HEKIT_WITH_RIVET` and links
`Rivet::Rivet`, though `Sink::Modules`, `utils/Module/` and `modules/` contain zero Rivet includes
and YODA is unconditionally required. The reasoning in the comment is right and the condition is
wrong. Recorded here because a principle with one unnoticed exception is how principles die.

---

## 5. The tool you already trust keeps working

**Physics lives in the native card, never in TOML.** A Pythia setting belongs in the `.cmnd`, a
Sherpa setting in its YAML, a Whizard setting in SINDARIN. TOML carries run control, wiring,
overrides and sweeps.

The base card is never modified. A generated **point card** carries what the plan decided, and how
the two combine is each tool's own dialect:

| Tool | Combination | Why |
|---|---|---|
| Pythia | append; last wins | flat `.cmnd`, later settings override |
| Sherpa | YAML **deep merge**, written whole | a path into a tree, and the card on disk must be the card that ran |
| Whizard | point card **first**, then include the base | SINDARIN is a *script*; assignments take effect when executed |
| MadGraph | renders a *Pythia* card | it hands over a matrix element, not events |

**What it bought.** No cross-generator "same physics" abstraction was attempted, and D3 records
that as a deliberate loss. The alternative — a TOML dialect that means the same thing to four
generators — is a research project that would have to be re-verified against every tool release.

---

## 6. A finding is a permanent record, not a fixed bug

Every defect found is catalogued as `00/Bn` with three columns: **what**, **evidence** (file and
line), **what was done**. Thirty-nine of them. Nine were found by *building*, not by reading.

They are cited from the code at the point they constrain it. `Phys::deltaPhi` carries `00/B35`;
`Sink::Modules` carries `00/B31` and `00/B36`; the ONNX include path carries `00/B37`.

**What it bought.** When P10-S01's verification row said "the grep for finding citations should be
empty", the row was recognised as wrong rather than satisfied — deleting the citations would have
deleted the record of *why the code is shaped as it is*. The row was replaced by an AST check and
the reasoning recorded. A codebase where the comments explain the shape is one where the next
overhaul starts from evidence.

Two findings are recorded and **not** fixed (`00/B39`, the MadGraph browser; and `00/B31`'s
consequence that `photo_eic` can never shard). Recording without fixing is a legitimate outcome and
keeping the tag honest was worth more than the one-line change.

---

## 7. Replacement before removal

Nothing was deleted until its replacement passed a comparison against it. The old tools
(`rivpyth`, `ydplt`, `ydmrg`, `generator.cc`) were **moved into the repository first** (D18), then
hotfixed for physics-relevant bugs (D19), then kept in use until golden and real-study comparisons
passed, then retired.

**What it bought.** The plot pipeline could be ported bin-for-bin against the tool it replaced,
because both existed at once. The transform layer is explicitly "a port and not a redesign", and
its tests compared the two implementations while the old one still existed.

**The order matters.** Hotfixing *before* capturing golden fixtures would have made the fixtures
agree with the new behaviour by construction; the fixtures were captured first and the expected
deltas written down.

---

## 8. Say the number, including when it is bad

Two estimates were wrong by a large factor. Both are recorded as misses with the reason, not
adjusted after the fact:

- the Python half was budgeted at ~4,000 lines and is **13,261** — 3.3×;
- the design's picture of a thin orchestrator over a heavy runner **inverted**.

Two verification rows were found to be untestable as written and were replaced by the question they
meant, with the substitution argued in the step's Log rather than quietly performed:

- *"parameters within 1σ"* — flaky by construction for five parameters and one seed (~30% failure);
  replaced by |pull| < 3 plus a 20-seed pull-RMS test.
- *"the grep is empty"* — see §6.

**What it bought.** The step Logs are usable as evidence by the next person, which is the only
reason a retrospective like this one can be written at all.

---

## 9. What was deliberately refused

A philosophy is defined as much by what it rejects. These were considered and declined **with a
reason on record**:

| Refused | Why |
|---|---|
| A DAG/workflow engine | Stage chains are a closed list. A general engine is a second product. |
| Physics in TOML | §5. |
| ROOT as a results format | YODA only (D7, D14). ROOT is for *processing* — fits, RDataFrame — and `hep-run` does not link it (D15). |
| Nested `hekit::…` namespaces | Flat PascalCase facades (D16). |
| A single-language codebase | §1 — both directions scored worse (55 and 67 against 87 out of 90). |
| In-process Delphes | Its global `class Event` and ROOT state clash; external process instead. |
| Per-candidate derived tables | Deferred **with evidence** (D23): exact replay means any table can be built later from stores that already exist. |

The last row is the pattern worth copying: a deferral that names its trigger and shows why the
option stays open is a decision, not a postponement.
