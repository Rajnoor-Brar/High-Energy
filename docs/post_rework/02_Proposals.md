# 02 — Proposals

Six changes, ranked by value per unit of disruption. Each says what it costs, what it breaks, and
what it does *not* fix. Nothing here has been applied.

The ordering matters: **P1 and P2 are worth doing on their own merits and are nearly free. P3 is the
one that changes how the system is understood. P4–P6 are tidying and should only happen if something
else is already touching those files.**

---

## 1. Move the two leaking value types down into `Core`

**Fixes:** C1 (both C++ layering violations, both cycles).
**Cost:** ~30 minutes. **Risk:** near zero.

`Needs` and `Output` are 9 lines of plain data that describe sinks but are *used* by `Module` and
`Results`. Put them beside the sink vocabulary `Core` already carries (`Core::SinkSpec`,
`Core::Exit::Sink`) — in `Core/Types.hh`, or a new `Core/Contract.hh` if that reads better:

```cpp
namespace Core {
    struct Needs  { bool pythia = false; bool hepmc = false; };
    struct Output { std::string kind, path; bool partial = false; };
}
```

and have `Sink/Types.hh` re-export them, so no call site changes:

```cpp
namespace Sink {
    using Needs  = Core::Needs;
    using Output = Core::Output;
}
```

**`Sink::Concurrency` stays put.** It is referenced only from `Sink/` and `Run/`, which sit at or
above `Sink`, so it violates nothing. Moving it too would be tidying by symmetry — which is how the
*next* audit gets a finding about types living far from their users.

**Result:** `Module → Sink` and `Results → Sink` both disappear. The C++ graph becomes a strict DAG
matching 13 §2 exactly, and the rule in that document becomes true rather than aspirational.

**Trade-off:** `Core` grows by two structs it does not itself use. The alternative — a separate
rank-0 `Contract` namespace — is tidier in theory and adds a twelfth namespace to a project that
already asks a reader to hold eleven. `Core` already holds `Spec`, `Provenance`, `Errors` *and*
`SinkSpec`, which are the same kind of shared vocabulary; these belong with them.

**Then enforce it.** A ~30-line test that parses the includes and asserts the ranking, run in ctest.
Without it this decays again the next time a type is needed one layer down — which is exactly how
these two arose.

---

## 2. Declare a Python layering, and test it

**Fixes:** the cause of P1 and P2. **Cost:** the document is an hour; making it true is proposal 3.
**Risk:** none on its own.

The C++ half has two cycles and the Python half has nine, and the difference is not discipline — it
is that one has a written rank and the other does not. Write the rank down:

```
rank 0   errors, paths                    nothing
rank 1   config, sweep                    rank 0
rank 2   plan, layout                     rank ≤ 1
rank 3   adapters, store, prov            rank ≤ 2
rank 4   run, results(judgement), plot, proc, term   rank ≤ 3
rank 5   cli commands                     anything
```

Then add the same enforcement test as proposal 1 — an AST walk over module-level imports asserting
no package imports a higher rank. `tests/python/env/test_housekeeping.py` already does an AST walk
for a different rule and can be the model.

**Trade-off:** a declared layering makes some future change harder on purpose. That is the point; it
is also why the rank must be written where people look (13 §2 or MAP.md), not only in a test.

**This proposal on its own does not fix anything** — it will fail immediately against the four
module-level cycles. It is listed separately because the *decision to have a rank* is independent of
the refactor that satisfies it, and is worth taking even if proposal 3 is deferred.

---

## 3. Split `results` into `layout` and `results`

**Fixes:** P1 and P3, and most of P2 as a consequence.
**Cost:** ~1 day including test updates. **Risk:** medium — it touches five packages.

`results/` is doing three jobs at three different layers ([01 §3](01_Audit.md#finding-p3-results-is-a-junction-not-a-layer)). Split by layer, not by topic:

| New package | Takes | Rank |
|---|---|---|
| **`layout`** | `layout.py`, `manifest.py`, `skip.py` | 2 — *where things go* |
| `results` (remains) | `stats.py`, `compare.py`, `merge.py` | 4 — *judging numbers* |
| `results/clean.py` | stays, or moves to `env` with the other housekeeping | 4 |

**Why this specific cut:** "where a point's files are" is the single most widely needed fact in the
Python half — `run`, `plot`, `proc`, `prov` and `term` all need it, and it depends on nothing but the
config. "Is this curve consistent with that one" is a leaf that depends on plotting and statistics.
They are at opposite ends of the stack and sharing a package is what forces `prov → results` and
`results → plot`.

**Expected effect on the cycles:**

| Cycle | After |
|---|---|
| `prov ⇄ results` | gone — `prov` needs `layout`, not judgement |
| `plot ⇄ results` | gone — `plot` needs `layout`; `results` keeps needing `plot` |
| `results ⇄ run` | gone — `run` needs `layout` |
| `run ⇄ term` | **remains** — see below |

**What it does not fix.** `run ⇄ term` is a genuine mutual dependency: the supervisor drives the
dashboard and the dashboard reads the supervisor's model. That one is real and should be broken, if
at all, by extracting the shared *state model* (`term/model.py`, 336 lines) into its own rank-3
package — not by this split. Listed as future work rather than done here, because the two are
genuinely co-designed and separating them may cost more clarity than it buys.

---

## 4. One `Session` object, built once

**Fixes:** P4, and removes four of the deferred cycles.
**Cost:** ~half a day. **Risk:** low — it is additive; commands migrate one at a time.

Five commands hand-roll `load_config → select_points → build → Layout.of`, and they have **already
drifted** — `hep compare` passes `overlay` but not `style`, and one of the five omits
`check_analyses=False` with no way to tell whether that is deliberate.

Give the thing a name and build it in one place:

```python
@dataclass(frozen=True)
class Session:
    config: Config
    selection: Selection
    plan: Plan
    layout: Layout

    @classmethod
    def of(cls, config_file, *, selectors, check_analyses=False) -> "Session": ...
    def points(self) -> list[PointFile]: ...      # the one definition of "the points I mean"
    def study_dir(self) -> Path: ...              # and of "where this study's outputs go"
```

with a `@session` decorator that pairs with the existing `@selectors` decorator, so a command reads:

```python
@click.command()
@selectors
@session
def plot(session: Session, ...):
```

**Why this is the "interconnection" answer.** The question "how do the tools connect" currently has
the answer "each one repeats the same four lines and hopes". `hep run → hep proc → hep plot` is a
real pipeline, and the thing that flows along it is exactly this object: the same config, the same
selection, the same points, the same directory. Naming it makes the pipeline visible, gives one
place to fix selector semantics, and removes the reason four packages import `config`, `sweep` *and*
`plan` at function scope.

**Trade-off:** a `Session` is a small God object, and they grow. Mitigate by keeping it frozen and
data-only, with the two derived accessors above and nothing else — the moment it gains a method that
*does* something, it has become a service and should be split.

---

## 5. Lift `paths` out of `env`

**Fixes:** part of P5. **Cost:** ~1 hour. **Risk:** near zero.

`env/paths.py` is a rank-0 utility (repo root, results root, `HEKIT_RESULTS`) living in a package
that also scaffolds Rivet plugins and probes LHAPDF. Move it to `hekit/paths.py` beside `errors.py`,
which is the other thing everything may use.

Leaves `env/` as "commands about the machine" — `doctor`, `build`, `pdf`, `analyses`, `new` — which
is a coherent, if broad, description.

---

## 6. Move `bench` out of `run/cli.py`

**Fixes:** P7. **Cost:** ~1 hour. **Risk:** near zero.

`run/cli.py` is 701 lines, the largest file in the project, because it holds the `run` command, its
live-view wiring **and** `bench`'s entry point. `bench` already has its own 336-line module; give it
its own `run/bench_cli.py` (or move the pair to a `bench/` package) and point `COMMANDS` at it.

Drops the largest file to roughly 550 lines, which is still large but is one command's worth.

---

## 7. Considered and rejected

| Idea | Why not |
|---|---|
| **Merge `Events` (143 lines) into `Core`** | Small is not a defect. `Events` is the one type every sink sees and it depends on Pythia and HepMC3; folding it into `Core` would drag both into the bottom layer and cost the all-off build. |
| **Split `Sink/Rivet.hh` (383 lines)** | It is the largest file because Rivet is the most complicated dependency — merging, dumps, thread-safety refusal and cross-section handling are one story. Splitting it scatters that story across files without reducing it. |
| **Rename `results` → `outputs` for symmetry with `output/`** | Churn across 9 files and every test, for a synonym. The confusion is between `results/` (the directory) and `results/` (the package), and proposal 3 removes most of it by taking layout out. |
| **One `cli/` package holding all 19 commands** | Would centralise placement (P7) but destroy the lazy-import property that keeps `hep --help` fast — the whole point of the current command tree. |
| **Collapse `prov` (461 lines) into `results`** | Backwards: `prov` is *lower* than judgement and the current `prov → results` edge is one of the cycles. Proposal 3 separates them properly. |
| **Adopt a plugin registry for the four external generators** | `adapters/registry.py` already is one. Nothing to gain. |

---

## 8. If only one thing is done

**Proposal 1.** It takes half an hour, removes both C++ cycles, makes the project's own documented
layering true, and — with the enforcement test — keeps it true. Everything else can wait for a reason
to touch those files.

**If two:** add proposal 4. It is the change a user would feel, because it is the one that makes
`run → proc → plot` a pipeline with a name rather than four lines repeated five times.

## 9. What to revisit as this grows

- **`run ⇄ term`** — left alone deliberately (proposal 3). Revisit if a second front end appears
  (a web view, a log-only mode); at that point the shared state model has two consumers and must
  come out.
- **`Session` scope** — revisit the moment it gains a method that performs an action rather than
  deriving a value.
- **`adapters/` at 2 062 lines and five generators** — fine now. At eight or ten, the per-tool
  modules will want a `generators/` sub-package and the cache will want to be its own thing.
- **The C++ layering test** — if it ever needs an exception list, the exception is the finding.
