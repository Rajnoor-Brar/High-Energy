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
| [01_Philosophy.md](01_Philosophy.md) | everyone | what the framework is, its principles and what each buys, what it refuses, where it came from |
| [02_Architecture.md](02_Architecture.md) | everyone | the model; components; a run from command to pages; connections; identity, seeds and skip; the prepare cache; status; failures; provenance; the plot stage; where files go |
| [03_User_Guide.md](03_User_Guide.md) | users | set up, a first run, the anatomy of a run TOML, **the pipelines** as recipes, plots and style, reruns, when something fails, a new project |
| [04_Config_Reference.md](04_Config_Reference.md) | users | **every accepted key**, its default and checks; paths; quantities and consumers; placeholders; `[plot]` and the style; the validation rules C1–C14; the commands; the files the runner writes |
| [05_Tools_Reference.md](05_Tools_Reference.md) | users, developers | every standard tool; the plot backends; App_Pythia, App_yd2rt and Paint; `Module.hh`; the status protocol; filter rules |
| [06_Developer_Guide.md](06_Developer_Guide.md) | developers | the layout, the build, the runner inside, the tool-folder contract, adding a tool or a backend, C++, tests, conventions |
| [07_Record.md](07_Record.md) | everyone | the brief, the decisions (V), the knowledge ledger (L), findings (F), v1's findings and decisions, risks, what has been verified, the budget, the glossary |

**Reading paths.** To use it: 03, then 04 as a reference. To understand it: 01, 02. To extend it:
02, 06, 05. The code cites these pages by section (`04 §9.4`) and the record by id (`L18`, `V22`,
`C7`, `00/B5`).

The documents this manual replaced (v1's design set and retrospective, the rework v2 plan and phase
logs) are in git: `git show rework/v1-final:docs/…` and `git log --all -- docs/rework_v2`. Ideas
found in them, not yet built, are in [bots/intent.md](../bots/intent.md).

Audits of the framework, and their plans: [audit_1/](audit_1/README.md) (`utils/`, V52–V89) and
[audit_2/](audit_2/01_Health.md) (a health check after the figures; the manual's rebuild, [02_Manual](audit_2/02_Manual.md)).

`tests/runner/test_docs.py` holds this manual to the code: its links resolve, its TOML parses, its
complete examples load, and every key the runner accepts is documented.
