# 04 — Decisions, and whether they held

The 23 decisions from [rework/10_Roadmap.md §2](../rework/10_Roadmap.md), with the column a plan
cannot have: **what happened**.

The originals are final and are not re-litigated here. This document adds outcome, not revision.

---

## 1. The scoreboard

| # | Decision | Held? | Note |
|---|---|---|---|
| D1 | Python orchestration, C++ event loop | **yes** | No cross-language duplication found. But see §3 — the ratio inverted. |
| D2 | Validation once, in Python; C++ reads a resolved spec | **yes** | `hep-run` gained exactly one user-facing flag (`--plain`), as predicted. |
| D3 | Physics in native cards, not TOML | **yes** | Four adapters, four dialects, no abstraction attempted. |
| D4 | Pythia → Rivet in-process | **yes** | |
| D5 | External generators → FIFO into `hep-run` | **mostly** | Delphes could not use a FIFO; MadGraph hands over a file. Both are documented exceptions, not failures of the rule. |
| D6 | Python `rich`, one renderer | **yes** | |
| D7 | YODA only; ROOT is not a results format | **yes** | Survived contact with `hep proc`, which is ROOT-heavy and still writes YODA. |
| D8 | HepMC3 store + replay | **yes** | Byte-identical replay demonstrated. |
| D9 | `rivet-mkhtml` + mplhep, `.plot` as the label source | **yes** | One label source, two backends. |
| D10 | CMake with optional components | **yes** | All-off build verified in P10-S03. |
| D11 | Point directories + studies, keyed by name and hash | **yes** | |
| D12 | One `hep` (click); shell only for env | **yes** | 19 commands, no standalone scripts. |
| D13 | Sharded HepMC3 + JSON index | **yes** | |
| D14 | YODA for Rivet **and** modules, one `analysis.yoda` | **yes** | Modules write into the same file, under `/<module>/<name>`. |
| D15 | ROOT for processing only; `hep-run` does not link it | **yes** | |
| D16 | House style: flat PascalCase facades | **yes** | Two toolchain clashes caught *before* adoption (`Event`, `Status`). |
| D17 | Lambda archived frozen in `legacy/` | **yes** | |
| D18 | Old tools moved into the repo **before** the port | **yes** | This is what made bin-for-bin comparison possible. |
| D19 | Hotfix physics-relevant old-tool bugs, then port | **yes** | Golden fixtures captured *before* the hotfixes. |
| D20 | PhotoProduction is a test bed | **yes** | Kept scope from drifting into physics review. |
| D21 | Identity-derived seeds, disjoint blocks | **yes** | Thread count changes partitioning, not statistics. |
| D22 | Partial outputs named differently; atomic renames | **yes** | |
| D23 | Derived tables deferred, with a named trigger | **yes** | Trigger not yet reached. |

**Twenty-two of twenty-three held.** D5 is the only one reality bent, and it bent it into a
three-phase stage model that is better than the uniform one it replaced.

---

## 2. The four that earned their keep

### D18 — move the old tools into the repository *before* porting

The cheapest decision on the list and the one that paid most. Because `rivpyth`, `ydplt`, `ydmrg`
and `generator.cc` were versioned and runnable **alongside** the new code, the plot pipeline could
be compared bin-for-bin against the tool it replaced. `plot/transform.py` says so in its docstring:
*"this is a port and not a redesign; the tests compare the two implementations bin for bin while the
old tools still exist."*

The corollary, D19, has an ordering that is easy to get backwards: **capture the golden fixtures
first, then hotfix**. Hotfixing first would have made the fixtures agree with the new behaviour by
construction and proved nothing.

### D16 — check names against the installed toolchain before adopting them

Two clashes found before a line was written: Delphes' global `class Event`, and X11's
`#define Status int`. Either would have been a confusing failure discovered mid-implementation.
Cost: one afternoon reading headers.

### D2 — resolve everything in Python

The spec `hep-run` reads has **no defaults left to interpret**. `threads = 0` meaning "hardware
concurrency" becomes an integer before it crosses. This is why the two halves cannot disagree about
what a value means, and it is the mechanism behind D1's success as much as the language split is.

### D21 — derive seeds from identity, not position

`seed + (i-1)*step` cannot promise that two different points never collide, nor that the same point
gets the same events across runs, nor that changing the thread count leaves the statistics alone.
Identity-derived disjoint blocks give all three. The cost is that a point's seed is not guessable by
hand — which turned out not to matter, because `hep plan` prints it.

---

## 3. The one that was right and mis-sized

**D1 held as a decision and failed as an estimate.**

| | Budgeted | Actual | |
|---|---|---|---|
| Python (non-comment) | ~4,000 | **13,261** | 3.3× |
| C++ (non-comment) | 3,150 | 4,659 | 1.48× |

The design's picture was a *thin orchestrator over a heavy runner*. What exists is a **heavy
orchestrator over a lean runner**. The rule ("C++ where an event is touched") is still correct —
per-event work genuinely is small once you stop reimplementing TOML parsing in C++ — but the
consequence was not foreseen: almost everything a user interacts with is per-run, and per-run work
is most of a toolkit.

Recorded as a miss in P10-S03's Log rather than rationalised. The honest reading: if the estimate
had been "13k Python, 4.7k C++", the split might have been argued differently — and it would still
have been the right answer, for different reasons than the ones given.

The second-order cost is the real one: **the Python half got the freedom without the discipline**.
The C++ half has a layering enforced by the CMake link graph and obeys it. The Python half has
neither, and has four structural cycles. See [06_Lessons.md](06_Lessons.md).

---

## 4. Deferral done properly — D23

Worth isolating as a pattern.

Per-candidate derived tables (for ML training) were **deferred with evidence**, not postponed:

- the options were costed at the time — Parquet needs a dependency that is not installed, RNTuple
  needs none, and writing tables from the event loop would contradict D15;
- the reason the option stays open was demonstrated, not asserted: **exact replay** means any table
  can be built later from stores that already exist;
- a **trigger** was named: the first ML training dataset.

A deferral that names its trigger and shows why the door stays open is a decision. One that says
"later" is a debt.

---

## 5. Open questions at `rework/v1`

| # | Question | Status |
|---|---|---|
| Q6 | Rebuild ThePEG/Herwig with HepMC + Rivet now or later? | **open** — blocks P7-S07, the Herwig adapter, the one step of 55 not done |
| Q7 | Whizard resolved photoproduction | **answered by the tool**: its manual says there is no photon structure function; `pdf_builtin_photon` throws. Direct processes only. |

Q1–Q5 were answered during execution and their answers are in the decision register at
[steps/README.md](../rework/steps/README.md#7-decision-register).

---

## 6. Things with no owning step

Small, and listed so they are not lost:

- **`[plot].merge = "yodamerge"`** is in the schema and validated (it requires a seed-only sweep),
  and the module half exists in `results/merge.py` — but **no command wires it into `hep plot`**.
  Setting it passes validation and silently gives overlay behaviour. For seed-replica merging today,
  `rivet-merge -e` is the tool.
- **`00/B39`** (MadGraph opens a browser from a supervised batch stage) is recorded and deliberately
  **not applied**, so `rework/v1` points at exactly what was measured. The fix is one line.
- **`00/B31`'s consequence**: `photo_eic` clusters jets, so it can never shard. Not a defect to fix —
  a property to know.
