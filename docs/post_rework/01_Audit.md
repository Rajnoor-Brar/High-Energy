# 01 — What was measured

Against `rework/v1` (`ddfeb40`), 2026-09-20. Every number here came from a script over the tree, not
from reading.

---

## 1. Sizes

### C++ — `utils/`, 6 837 lines

| Namespace | Files | Lines | | Namespace | Files | Lines |
|---|---|---|---|---|---|---|
| `Core` | 8 | 949 | | `Phys` | 5 | 887 |
| `Status` | 5 | 469 | | `Source` | 4 | 736 |
| `Events` | 2 | 143 | | `Module` | 3 | 217 |
| `Store` | 5 | 662 | | `Sink` | 6 | 960 |
| `Results` | 5 | 604 | | `Run` | 2 | 327 |
| `ML` | 3 | 437 | | `apps` | 1 | 291 |

Largest file: `Sink/Rivet.hh` at 383 lines. Then `Core/Spec.hh` 363, `Source/Replay.hh` 329,
`Run/Loop.hh` 296.

**Verdict: healthy.** No God file, no namespace over a thousand lines, and the biggest file is the
one wrapping the most complicated external library. Nothing here needs splitting on size grounds.

### Python — `hekit`, 16 853 lines

| Package | Files | Lines | | Package | Files | Lines |
|---|---|---|---|---|---|---|
| `run` | 9 | 2 137 | | `results` | 9 | 1 618 |
| `adapters` | 11 | 2 062 | | `term` | 7 | 1 561 |
| `config` | 9 | 1 977 | | `plan` | 8 | 1 150 |
| `proc` | 10 | 1 822 | | `env` | 6 | 1 088 |
| `plot` | 12 | 1 719 | | `sweep` | 5 | 629 |
| | | | | `prov` | 6 | 461 |
| | | | | `store` | 4 | 435 |

Largest: `run/cli.py` **701**, `results/cli.py` 435, `config/migrate.py` 427, `run/supervisor.py` 398.

**Verdict: two outliers.** `run/cli.py` at 701 lines is the only file in the project that is clearly
too big — it holds the `run` command, its live-view wiring, *and* `bench`'s entry point. Everything
else is proportionate.

---

## 2. The C++ dependency graph

The documented layering (13 §2) is:

```
Core ─► Status ─► Events ─► { Store, Results, ML, Phys } ─► { Source, Module } ─► Sink ─► Run ─► apps
rank    0         1          2          3                     4                    5       6
```

Measured from `#include` directives:

| Namespace | rank | includes |
|---|---|---|
| `Status` | 1 | Core |
| `Events` | 2 | Core |
| `Store` | 3 | Core, Status |
| `ML` | 3 | Core |
| `Phys` | 3 | Core |
| `Results` | 3 | Core, Status, **Sink** ← |
| `Module` | 4 | Core, Events, Results, **Sink** ← |
| `Source` | 4 | Core, Events, Status, Store |
| `Sink` | 5 | Core, Events, Status, Store, Results, Module |
| `Run` | 6 | Core, Events, Status, Results, Sink, Source |
| `apps` | — | Core, Status, Run, Sink |

### Finding C1 — two layering violations, and they are the same 9 lines

```
Module/Types.hh    (rank 4) includes Sink   (rank 5)
Results/Summary.hh (rank 3) includes Sink   (rank 5)
```

Both produce a **cycle**: `Module ⇄ Sink` and `Results ⇄ Sink`.

The cause is not a tangle of logic. It is **two** pure value types that live in `Sink/Types.hh` and
are needed further down:

```cpp
struct Needs  { bool pythia; bool hepmc; };                // 4 lines
struct Output { std::string kind, path; bool partial; };   // 5 lines
```

`Module::Base::needs()` returns a `Sink::Needs`; `Results::summaryJson()` takes a
`std::vector<Sink::Output>`. Neither has anything to do with the `Sink` *interface* — they are the
vocabulary the layers use to talk about sinks, put in the namespace of the thing they describe
rather than in one both sides can see.

**9 lines of struct cause both violations of the project's own layering rule.**

Checked and *not* a violation: `Sink::Concurrency` is referenced only from `Sink/` and `Run/`, both
at or above `Sink`. It belongs where it is. An audit that swept it up with the other two would be
moving a type for symmetry rather than for a reason.

There is already a precedent for the fix: **`Core::SinkSpec` exists** (`Core/Spec.hh:59`), as does
`Core::Exit::Sink`. `Core` already carries sink vocabulary; these two types are the ones that did
not get the same treatment.

### Finding C2 — nothing else is wrong

Every other edge respects the ranking. `Sink` legitimately sits above `Results`, `Store` and
`Module`; `Run` sits above everything. The `Events`/`Store` split holds. This is a graph that was
designed and then obeyed, which is rare enough to say out loud.

---

## 3. The Python dependency graph

There is no declared layering, so there is nothing to check against. What is measurable is the shape.

### Module-level (structural) dependencies

| Package | imports at module level |
|---|---|
| `sweep` | — |
| `adapters` | sweep |
| `env` | prov |
| `prov` | **results** |
| `plan` | adapters, config, env, sweep |
| `plot` | config, env, plan, **results**, sweep |
| `proc` | config, plan, results, sweep |
| `results` | env, plan, **plot**, **prov**, **run**, **term** |
| `run` | config, plan, **results**, sweep, **term** |
| `term` | **run** |
| `config` | — (at module level) |
| `store` | — (at module level) |

### Finding P1 — four cycles at module level

```
plot ⇄ results
prov ⇄ results
results ⇄ run
run  ⇄ term
```

These are not deferred or managed; they are top-of-file imports that happen to work because Python
resolves them in an order nobody chose. They are the reason `results` imports `plot`, `run`, `term`
*and* `prov` — it is not a layer, it is a junction.

### Finding P2 — nine cycles once deferred imports count

Adding function-local imports (the codebase uses them deliberately, to keep `hep --help` fast):

```
adapters ⇄ plan      env ⇄ plan      env ⇄ plot      env ⇄ prov
plot ⇄ results       prov ⇄ results  results ⇄ run   run ⇄ term    store ⇄ term
```

The deferred ones are defensible individually — a lazy import is the standard fix for a CLI that must
start fast. But nine of them means the *packages* have no order, and the laziness is load-bearing:
several would become import errors if someone moved them to the top of the file for tidiness.

### Finding P3 — `results` is a junction, not a layer

`results/` contains: `layout.py`, `manifest.py`, `skip.py`, `stats.py`, `compare.py`, `merge.py`,
`clean.py`, `cli.py`. That is at least three unrelated jobs fused:

1. **where things go** (`layout`, `manifest`, `skip`) — needed by `run`, `plot`, `proc`, `prov`;
2. **judging numbers** (`stats`, `compare`, `merge`) — needed by `plot` and the `compare` command;
3. **housekeeping** (`clean`) — needed by nobody else.

Job 1 is the lowest layer in the whole Python half — everything needs to know where a point's files
are. Job 2 is near the top. Fusing them is what forces `results → plot` and `prov → results`.

---

## 4. Duplication

### Finding P4 — every command re-derives its own context

This block, or a near-copy, appears in **five** command modules (`plot`, `proc`, `run`, `results`,
`term`):

```python
config    = load_config(config_file, sets=tuple(sets))
selection = select_points(config, study=study, pins=tuple(pins), across=across,
                          style=style, overlay=overlay)
plan      = builder.build(config, selection, check_analyses=False)
layout    = layout_module.Layout.of(config)
```

It is short, so it looks harmless. It is not:

- the `check_analyses=False` flag is passed by four of them and omitted by one, and whether that is
  deliberate is not discoverable from the code;
- `results/cli.py` passes `overlay` but not `style`, so `hep compare` and `hep plot` interpret the
  same selector flags slightly differently;
- it is why `plot`, `proc`, `results`, `run` and `term` each import `config`, `sweep` **and** `plan`
  — four of the nine deferred cycles exist to serve this one preamble.

The selector *flags* are shared properly (`plan.cli.selectors` is a reusable decorator). What is not
shared is what to **do** with them.

### Finding P5 — `env/` is a grab-bag

`env/` holds `paths`, `doctor`, `lhapdf`, `scaffold` and a 278-line `cli.py` implementing **five
unrelated commands**: `doctor`, `build`, `pdf`, `analyses`, `new`. Their only common property is
"about the machine rather than about a run". `paths.py` in particular is a genuine bottom-layer
utility that everything needs, sitting in a package that also knows how to scaffold a Rivet plugin.

### Finding P6 — no duplication across the language boundary

Checked because it is the obvious place to look: `run/status.py` + `run/parsers.py` (275 lines) read
the JSON-lines stream that C++ `Status/` (469 lines) writes. They are **two halves of one contract**,
not two implementations of one thing. Correctly split. No action.

---

## 5. Command surface

19 commands, none a placeholder. Their placement:

| Package | Commands |
|---|---|
| `env` | doctor, build, pdf, analyses, new |
| `results` | runs, show, compare, clean |
| `run` | run, bench |
| `config` | config, studies |
| `term` | watch, events |
| `plan`/`plot`/`proc`/`store` | plan / plot / proc / store |

**Finding P7 — placement follows implementation, not the user's model.** `hep studies` lives in
`config` and `hep analyses` in `env`, though a user thinks of both as "tell me what is available".
`hep bench` lives in `run` and is 336 lines of its own module plus an entry point in the 701-line
`run/cli.py`. This is not harmful — the lazy command tree means placement is invisible at the CLI —
but it is why `run/cli.py` is the largest file in the project.

---

## 6. Summary of findings

| # | Finding | Severity | Cost to fix |
|---|---|---|---|
| C1 | Two C++ layering violations, both from 9 lines of value types in the wrong namespace | **high** — breaks the project's own stated rule | ~30 min |
| C2 | The rest of the C++ graph is clean | — | — |
| P1 | Four module-level cycles in Python | **high** | medium |
| P2 | Nine cycles including deferred imports; laziness is load-bearing | medium | follows from P1/P3 |
| P3 | `results` fuses layout, judgement and housekeeping; it is the junction | **high** | medium |
| P4 | Five commands hand-roll the same context preamble, with drift already visible | medium | ~half a day |
| P5 | `env/` is a grab-bag holding a bottom-layer utility | low | ~1 hour |
| P6 | No cross-language duplication | — | — |
| P7 | `run/cli.py` is 701 lines because `bench` shares it | low | ~1 hour |

Proposals in [02_Proposals.md](02_Proposals.md).
