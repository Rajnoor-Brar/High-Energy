# post_rework/

An audit of the structure of `utils/` after the rework, and what it would take to improve it.

Written 2026-09-20, against `rework/v1` (`ddfeb40`). Nothing here has been applied — these are
findings and proposals, and each one says what it would cost.

| Document | What it covers |
|---|---|
| **[01_Audit.md](01_Audit.md)** | What was measured: sizes, both dependency graphs, cycles, duplication. The evidence. |
| **[02_Proposals.md](02_Proposals.md)** | Six changes, ranked by value per unit of disruption, with trade-offs and what to revisit later. |

## The short version

**The C++ half is in good shape and the Python half is not**, and the reason is not size — it is
that one has an enforced layering and the other has none.

| | C++ (`utils/`) | Python (`hekit`) |
|---|---|---|
| Lines | 6 837 | 16 853 |
| Largest file | 383 | 701 |
| Declared layering | yes (13 §2) | **none** |
| Module-level cycles | **2** | **4** |
| Cycles incl. deferred imports | 2 | **9** |

The two C++ cycles come from **14 lines of value types** sitting in the wrong namespace and are a
half-hour fix. The Python cycles are structural: `results`, `run` and `term` form a knot, and every
command re-derives "which points do you mean" by hand.

**The single highest-value change** is not a reorganisation at all — it is giving the Python half
the thing the C++ half already has: a written layering, and one shared object that carries
config → selection → plan → layout so that commands stop reaching sideways for it.

## What this audit is not

It does not propose renaming namespaces, merging packages for tidiness, or moving files to make a
diagram prettier. The rework's structure is mostly right; what it lacks is a rule on the Python side
and three small corrections on the C++ side. Anything that costs more than it repays is listed in
[02 §7](02_Proposals.md#7-considered-and-rejected) with the reason it was rejected.
