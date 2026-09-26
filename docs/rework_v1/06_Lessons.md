# 06 — Lessons

What this overhaul actually taught, as distinct from what it planned. Ordered by how much the next
one would gain from knowing it.

---

## 1. Enforce the layering, or you do not have one

This is the finding, and everything else is smaller.

| | C++ (`utils/`) | Python (`hekit`) |
|---|---|---|
| Lines | 6,837 | 16,853 |
| Declared layering | yes, and **the CMake link graph enforces it** | **none** |
| Module-level cycles | **2** | **4** |
| Cycles incl. deferred imports | 2 | **9** |

Same author, same period, same care. The difference is that one half's rank is expressed as
`target_link_libraries(hekit_Module INTERFACE hekit_Results hekit_Phys hekit_ML)` — a statement the
build checks every time — and the other half's rank was never written down at all.

The two C++ violations are instructive: they come from **9 lines** of pure value types
(`Analyzer::Needs`, `Analyzer::Output`) sitting in the namespace of the thing they *describe* rather than in
one both sides can see. Even with enforcement, the leak found the one shape the enforcement did not
cover — a type, not a dependency.

**For next time.** Write the rank down for *every* half of the system, in the place people look, and
add a test that parses imports and asserts it. On the Python side that is an AST walk of about 30
lines; `tests/python/env/test_housekeeping.py` already does one for a different rule.

---

## 2. Per-run work is most of a toolkit

The design assumed a thin orchestrator over a heavy runner. The result is the opposite:

| | Budgeted | Actual |
|---|---|---|
| Python (per-run, non-comment) | ~4,000 | **13,261** |
| C++ (per-event, non-comment) | 3,150 | 4,659 |

The rule — *C++ where an event is touched, Python where a file, process or person is touched* — was
correct. The **volume** estimate that followed from it was wrong by 3.3×, because almost everything
a person interacts with is per-run: configs, sweeps, supervision, terminal, plots, fits, provenance,
housekeeping, scaffolds.

**For next time.** When splitting a system by execution frequency, size the halves by *surface area*
(how many things a user can ask for) rather than by how central they feel. The event loop is the
heart and it is 20% of the code.

---

## 3. Some defects can only be found by running

Nine of 39 findings were discovered during construction, and three of those changed the
architecture:

| Finding | What reading could not have told you |
|---|---|
| `00/B31` | FastJet keeps clustering state in **process-wide statics**, and this build has `FASTJET_HAVE_LIMITED_THREAD_SAFETY` undefined. A race changes the jets rather than crashing. |
| `00/B32` | `PythiaParallel` runs the event callback on worker threads in **both** modes; `processAsync = off` only adds a mutex. An analyzer throw would have unwound through `std::thread` into `std::terminate`. |
| Delphes/FIFO | Delphes sizes its input and skips anything of length zero, which a FIFO always is. |

Each forced a real design change — concurrency became a property of the analyzer, both sources catch at
the thread boundary, and the stage model gained phases.

**For next time.** Budget for a "the design was wrong" list and write it as you go. Eleven entries
out of a 15-document design is roughly 20%; plan the schedule for that, not for zero.

---

## 4. A silently-ignored input is the worst failure mode

The same shape recurred four separate times:

| | What it did |
|---|---|
| `00/B5` | Reference data matched **by name** drew ZEUS's `d08-x01-y01` over a different observable. Nothing complained. |
| `00/B14` | Configs declared analysis options the analysis does not take. The scan produced identical curves. Nothing complained. |
| `00/B37` | The `Requires: ONNX` convention had **never been run** and its include path was wrong. |
| `LegendXPos` | Parsed into `settings` by the mpl backend and then never used — `loc="best"` is hardcoded. Still open. |

In every case the system did something plausible instead of refusing. The fixes share a shape:
**require the explicit statement, and refuse the convenient inference.** `[plot.data].map` is
mandatory and name matching was removed; `hep plot --suggest-data-map` offers a name-matched map as
a *suggestion the user must paste*, which is the difference between a convenience and a defect.

**For next time.** Anywhere the system infers a correspondence — names, paths, units, bins — ask
what happens when the inference is wrong. If the answer is "a plausible wrong answer", make it
explicit or make it loud.

---

## 5. Test the convention, not just the code

`tests/integration/test_onnx_plugin.py` builds a probe plugin through `rivet-build`, loads it,
**and checks that the old flags still fail**. That second half is what stops `00/B37` from
returning.

The same instinct: `hep config reference` generates the config documentation from the schema, and a
test fails if the committed file is stale — so there is no second place to update. `test_docs.py`
resolves every relative link in the documentation.

**For next time.** A test that asserts the current behaviour protects the behaviour. A test that
asserts the *broken* alternative still breaks protects the reason.

---

## 6. Caches need to be keyed on everything they depend on

`00/B38`: `hep doctor` cached its report keyed only on the install root. Every check it makes
resolves through `PATH` and `PYTHONPATH`, so a probe run in a stripped shell found almost nothing —
and that answer was handed back to a normal shell for the next 24 hours.

Found by running the portability check and watching it break an unrelated test. Fixed with an
`env_key` over install root, `PATH` and `PYTHONPATH`, and verified rich → stripped → rich.

**For next time.** For any cache, list what the cached computation *reads*. If the key does not
cover all of it, the cache is a correctness bug waiting for an unusual environment.

---

## 7. Deferral is a decision when it names its trigger

D23 deferred per-candidate derived tables and is the model:

- options **costed at the time** (Parquet needs an uninstalled dependency; RNTuple needs none;
  writing tables from the event loop would contradict D15);
- the reason the door stays open **demonstrated, not asserted** — exact replay means any table can
  be built later from stores that already exist;
- a **trigger** named: the first ML training dataset.

Compare with `[plot].merge = "yodamerge"`, which is in the schema, is validated, has half an
implementation — and **no owning step**. It passes validation and silently gives overlay behaviour.
That is the failure mode of a deferral with no trigger: it becomes a feature that appears to exist.

---

## 8. Two things that were cheap and paid disproportionately

**Check names against the installed toolchain before adopting them** (D16). One afternoon reading
headers; caught Delphes' global `class Event` and X11's `#define Status int` before a line was
written.

**Move the old tools into the repository before porting** (D18). It is what made bin-for-bin
comparison possible, and it is why the plot pipeline could be honestly described as "a port, not a
redesign".

Both are front-loaded, low-glamour, and would be the first things cut under schedule pressure.

---

## 9. What to do differently

| | |
|---|---|
| **Declare and test the Python layering from step one** | Not at the end. Four cycles exist because there was never a moment where adding one failed. |
| **Give the pipeline object a name early** | Five commands hand-roll `load_config → select_points → build → Layout.of` and have already drifted (`hep compare` passes `overlay` but not `style`). A `Session` carrying config → selection → plan → layout would have prevented it *and* made `run → proc → plot` visibly a pipeline. |
| **Split a package the moment it serves two layers** | `results/` fuses layout (lowest), judgement (near-top) and housekeeping. It is the junction behind three of the four cycles. |
| **Size the per-run half by surface area** | §2. |
| **Re-audit before tagging, not after** | `00/B39` was found after `rework/v1`. Handling it was clean, but finding it a day earlier would have been cleaner. |

---

## 10. What to revisit as this grows

- **`run ⇄ term`** — a genuine mutual dependency, left alone deliberately: the supervisor drives the
  dashboard and the dashboard reads the supervisor's model. Revisit when a **second front end**
  appears (a web view, a log-only mode); at that point the shared state model has two consumers and
  must come out.
- **`adapters/` at 2,062 lines and five generators** — fine now. At eight or ten, the per-tool
  modules want a `generators/` sub-package and the prepare cache wants to be its own thing.
- **A `Session` object's scope** — the moment it gains a method that *performs* an action rather
  than deriving a value, it has become a service and should be split.
- **Any layering test that needs an exception list** — the exception is the finding.
- **D23's trigger** — the first ML training dataset.
- **Q6** — Herwig, the one step of 55 not done.
