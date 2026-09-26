# docs/

- **[GUIDE.md](GUIDE.md)** — using the toolkit: a config, a run, results, your own analysis or
  module, and what to do when something goes wrong. Start here.
- **[MAP.md](MAP.md)** — where everything lives and what owns what: the two halves, the C++
  namespaces, the `hekit` packages, and the shape of a results directory.
- **[rework_v1/](rework_v1/)** — the framework as built, and why: philosophy, design, conventions,
  the decisions with their outcomes, the process as a reusable method, and the lessons. **The
  reference for changing or extending the system, and the case study for the next overhaul.**
- **[rework/](rework/)** — the design: `README.md`, the numbered documents 00–13, the generated
  [config reference](rework/reference/config.md), and `steps/` (the step index, dependency graph,
  decision register and traceability).
- **[post_rework/](post_rework/)** — the structural audit of the result: sizes, both dependency
  graphs, cycles, duplication, and six ranked proposals. Measured, not assessed.

**The design documents are now a record, not a plan.** They describe the system that was built,
with each step's Log recording what was *measured* rather than what was intended — including the
places where the design turned out to be wrong and what replaced it. When a document and the code
disagree, the code is right and the Log usually says why.

Everything describing the pre-rework code is archived, with its history, under
**[../legacy/docs/](../legacy/docs/)**: the old `MAP.md`, `Architecture.md`, `DataContract.md`,
`UtilsAudit.md`, `UtilsDependencyMap.md`, `Audit.md`, `archive/`, `plans/` and the old
`bots/{CLAUDE,plan,GEMINI}.md`. Nothing current links into it for how the system works.
