# Review — open backlog

Open backlog not yet promoted into the phased work in [PROPOSAL.md](PROPOSAL.md).
Everything below was re-checked against the active source tree; archive files
were read only for context.

---

## 1. `Probe::ScalarSpec` plumbing is still in source

`utils/Probe/Types.hh:40-45,77`; `utils/Probe/Event.hh:17-23`;
`utils/Probe/Parallel.hh:17-22,56-57,101-103,124-132`

The user reported this fixed, but the active tree still declares `ScalarSpec`,
stores `Event::scalars`, and threads scalar parameters through `EventStream`
and `runParallel`. No current reader populates those values and no active
driver passes scalar specs. Keep this open until the scalar path is either
wired end-to-end or removed.

---

## 2. Add a `Driver` / `App` skeleton

`_Lambda_Parallel.cc:11-55`; `_Lambda_Reconstruction.cc:13-90`;
`_Lambda_Data.cc:12-62`; `_Lambda_Test.cc:10-58`;
`modules/Lambda/Context.hh:21-35`

The remaining duplication is the lifecycle scaffold, not the callback payload.
`AnalysisContext` and `GenerationContext` already removed most of the argument
noise; reassess this after PROPOSAL Phase 2 lands.

---

## 3. Doc-comment header on every umbrella

`utils/Utility.hh:1-4`; `utils/Paint.hh:1-6`; `utils/Physics.hh:1-6`;
`utils/Monitor.hh:1-7`; `utils/Probe.hh:1-9`; `utils/Record.hh:1-7`

The bare include-list umbrellas still need one consistent header block each
describing the module role and the subheaders they re-export.

---

## 4. Cross-link the docs

`docs/MAP.md:10`; `bots/CLAUDE.md:87-88`

`MAP.md` still points only to REVIEW/ROADMAP, and the bot-facing entry point
still lacks a link to the phased plan document. Revisit once the new doc
layout settles.

---

## Investigations

### A. BranchControl / Probe namespacing

`utils/Probe/Schema.hh:28-211`; `utils/Probe/VecReader.hh:40-47,75`;
`utils/Probe/FlatReader.hh:29-46,104,220`;
`utils/Probe/Parallel.hh:24,46,68,73,87,92,129`

Readability does improve if the current internal helper namespace stops being
the opaque `detail`. It does not improve enough to justify a deeper split into
`TreeControl`, `LeafControl`, `EventControl`, and similar subnamespaces. The
helpers are cross-cutting: `Partition`, `enableRootThreadSafety`,
`probeFirstKey`, and `scanIndexBranch` do not group cleanly into narrower
buckets, and `FlatReader` / `VecReader` / `Parallel` each pull from several
families at once. The right move is a single internal namespace rename,
`Probe::detail` -> `Probe::BranchControl`, paired with
`Schema.hh` -> `BranchControl.hh`.

### B. AsyncLogger queue shape vs. exception aggregation

`utils/Monitor/Logger.hh:188-280`; `utils/Probe/Parallel.hh:51-63,96-109`

The ambiguous robustness note maps to `AsyncLogger::runLoop`, not to
`Probe::runParallel` exception aggregation. `runLoop` currently coalesces
three action types through `PendingActions`, one latest `RunSnapshot`, and a
`dirtyThreadSnapshots_` drain vector. That is awkward to extend but still
coherent for the current action surface. By contrast, worker exception
aggregation is a separate concrete backlog item with a straightforward failure
mode. Recommendation: keep the current coalescing `PendingActions` model until
the logger needs more action types or stricter cross-action ordering. A queue
is not yet pulling its weight.

### C. Abstraction pair 1: `Lambda::fillCandidates`

`modules/Lambda/Recording.hh:35-43`

The current three-pass structure is acceptable as-is. Each pass maps directly
to one semantic bucket (`Unvalidated`, `Validated`, `Selected`), and the
surrounding `resetAllCounts` / `countAll` calls make the lifecycle obvious at
the call site. Keep this as a late-stage "document rationale or combine into
one pass" item, not as phased work.

### D. Abstraction pair 2: `Record::write` / `writeToDir`

`utils/Record/Histogram.hh:128-159`

This is a legitimate late-stage deduplication target. The two functions differ
mainly in where `cd()` happens and whether the helper receives an explicit
directory. A private iterator-style helper can collapse them later without
changing behaviour, but the duplication is not blocking enough to promote into
the phased plan.

### E. `event_particles` TOML schema

`utils/Config/Types.hh:59-69`; `utils/Config/Reader.hh:191-210`;
`utils/Probe/Types.hh:18-37`; `utils/Probe/Schema.hh:109-134`;
`utils/Probe/FlatReader.hh:28-50`; `utils/Probe/VecReader.hh:39-50`;
`modules/Lambda/Parameters.hh:105-119`

The proposed row shape
`event_particles = [[name, spec, treeName, [specBranchNames], branchType]]`
is not fully source-compatible with the current Probe layer. The active code
still has no mapping from integer `spec` to `CoordSpec`, `CollectionSpec`
still requires explicit `coords` and `indexBranches`, and `BranchSpec` still
expects per-branch typing rather than one shared `branchType` for an arbitrary
list. It also cannot express the flat-reader requirement for an index branch
separately from aux branches. Conclusion: viable only after extending the
parser and schema model; not ready to phase in under the current interfaces.

---

## Unconcerns

- Former REVIEW 11: Per-event `WorkerStats` RAII helper remains readable enough as-is.
- Former REVIEW 12: The old four-way `Register` split is superseded by the `HistConfig` route in [PROPOSAL.md](PROPOSAL.md).
- Former REVIEW 17: Reproducibility metadata can wait until the phased source reshapes settle.
- Former REVIEW 19: `README.md` is useful, but it is not on the critical refactor path.
- ROADMAP 8: `EventScope` RAII is the same class of local boilerplate cleanup as former REVIEW 11.
- ROADMAP robustness unconcern: `tests/run_all.sh:26-29` breaking on first failure is acceptable for now.
- ROADMAP performance unconcern: `Watch::freeze()`'s dual allocation on the fatal path is acceptable for now.
- ROADMAP readability unconcern: `modules/Lambda/ParamAid.hh:42-47` indirection via `resolveCandidateLabels` is acceptable for now.
