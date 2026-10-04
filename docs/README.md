# The manual

A framework for Monte Carlo studies in high-energy physics: **tools are processes, chained by a
TOML**. A run TOML under `configs/<Project>/` names a configuration; its sweeps expand into points;
for each point the runner writes every tool's native card, connects the tools through agreed files
and FIFOs, runs them in order, watches them, checks what they made, and records it; after all points
it draws the pages with ROOT (Paint) or rivet-mkhtml. Technical files go to `output/`, products to
`results/`, compiled things to `build/`.

```bash
load_hep && hep build
hep run PhotoProduction/eic energy_pdf --plan     # look
hep run PhotoProduction/eic energy_pdf            # run: 16 points, 4 pages per histogram
```

## Contents

| | For | |
|---|---|---|
| [01_Overview.md](01_Overview.md) | everyone | what it is, the model in one picture, the vocabulary (object, figure, page …), the principles and what each buys, what is refused, where it came from |
| [02_User_Guide.md](02_User_Guide.md) | users | set up, a first run, the anatomy of a run TOML, **the pipelines** as recipes (sweeps, generators and chains, your own programs, scale and seeds), reruns, failures, housekeeping, results from Python, a new project |
| [03_Plots.md](03_Plots.md) | users | the plot stage, `[plot]` in practice, data and ratios, curves and bands, the style, **the seven figure classes** with examples, Hist1D/Scatter2D/HeatMap, the backends, `hep overlay` |
| [04_Config_Reference.md](04_Config_Reference.md) | users | **every accepted key**, as tables generated from the schema; paths, precedence and `"default"`; quantities and consumers; placeholders; the style keys; the validation rules C1–C14; the files the runner writes |
| [05_Commands_and_Tools.md](05_Commands_and_Tools.md) | users, developers | **every command** (generated from the CLI) and what it does; the build and the environment; every standard tool; App_Pythia, App_yd2rt and Paint's command line |
| [06_Internals.md](06_Internals.md) | developers | layout, components and ranks, the data model, a run in code, connections, identity and seeds, caches, events, failures, the plot stage inside, where files go; the build, the tool-folder contract, adding a tool, backend or figure class, Paint inside, the C++ kits and protocols, tests, conventions |
| [07_Record.md](07_Record.md) | everyone | the brief, the decisions (V), the knowledge ledger (L), findings (F), v1's findings and decisions, risks, what has been verified, the budget, the glossary |

**Reading paths.** To use it: 02 and 03, then 04 and 05 as references. To understand it: 01, 06.
To extend it: 06, then 05. The code cites these pages by section (`04 §9.4`) and the record by id
(`L18`, `V22`, `C7`, `00/B5`). The key, style and command tables are generated: `make docs` (V91).
The manual was rebuilt at V90–V92 (audit 2); the old pages are in git (`git show a029c21:docs/…`).

The documents this manual replaced (v1's design set and retrospective, the rework v2 plan and phase
logs) are in git: `git show rework/v1-final:docs/…` and `git log --all -- docs/rework_v2`. Ideas
found in them, not yet built, are in [bots/intent.md](../bots/intent.md).

What is open is the health check [audit_2/01_Health.md](audit_2/01_Health.md) (H1–H16). The finished audit 1
(V52–V89) and the manual's rebuild plan (V90–V92) are in git: `git show c5cbaa3:docs/audit_1/README.md`,
`git show c5cbaa3:docs/audit_2/02_Manual.md`.

`tests/runner/test_docs.py` holds this manual to the code: its links resolve, its TOML parses, its
complete examples load, its generated blocks are current, and every key the runner accepts is documented.
