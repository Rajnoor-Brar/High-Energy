# 00 — The brief

The user's target design for the second rework, **verbatim** as given on 2026-09-26. Everything
else in `docs/rework_v2/` answers to this document. Where another document and the brief disagree,
the brief is the intent and the other document is either wrong or has recorded, with a reason, why
it departs (see [README.md §Decisions](README.md#decisions)).

Section headings below were added so other documents can cite them as *Brief §Tools*,
*Brief §Configurations* and so on; the text under each is unchanged, including its spelling.

---

## Preamble

> Goal of this session is second rework. Make files related to this in docs/rework_v2/
>
> This will be first round of plan for more high level planning with another round of planning to
> follow if required.
>
> As it stands, from my perspective whole framework is very convoluted and scattered, since it was
> rework by Claude as per its best judgement for the pipelines.
>
> So I will now give rough high level design for how I want whole thing to work and then you can
> plan after determining how much lean or bloated current framework is.

## Tools

> Tools will be categorised (informally, not necessarily physically into folders) into following
> categories. (whether a category actually has tools installed is different matter)
>
> 1. Providers (PDFs, PDF providers (LHAPDF) and tools such as FeynRules, Sarah; tools that extend
>    other tools with data/ standard configurations)
> 2. Bridges/Interfaces (HepMC3,LHE)
> 3. Process Generators (MadGraph, Whizard)
> 4. Event Generators
> 5. Detector Simulators (Geant, Delphes)
> 6. Analysis *Algorithms* (Fastjet, ROOT; fuction-like library based tools used inside analysis
>    applications or programs that provide function, classes and methods to process data)
> 7. Analysis *Applications*(Rivet, CMSS: pre-set pipelines; called as an independent process)
> 8. Analysis *Visualisation* (YODA, Root ; plot and store final data usually as graphs and
>    histograms)
> 9. Statistics (roofit, roostats, uproot, python; ML applications/libraries)
> 10. Database (xrootd,rucio etc)

## Directory Structure

> 1 ./configs/{project}/{file}.{ext}  for configuration files
> 2. ./modules/{project}/<{sources_to_be_compiled}.cc , {headers}.hh , {header}/{headers.hh}>  for
>    specific tasks that cant be achieved by typical tool chaining
> 3. ./output/{project}/ for tmp files, logs, configs and other technical files
> 4. ./output/{tests}/ for tests
> 5. ./results/{project}/ for yoda/root/plots and analysis and post analysis products
> 6. ./build/ for compiled stuff
> 7. ./build/Rivet/ for rivet analyses
> 8. ./docs/ for plans and documentations
> 9. no ./env folder, /utils/Env/ for bash script, terminal command codes
> 10. no ./analyses , recognise rivet sources from modules root by Rivet_ prefix or in
>     {module}/Rivet/
>
> generally automatically prefix path as expected by convention, fo example, where config is
> expected, automatically prefix by ./config/ and so, unless begun by ./

## Configurations

> Wherever possible, configuration will be provide to processes via config files (especially to
> generators; like cmnd to pythia; .run for herwig etc; or toml)

### Main toml config

> would have
>
> ```
> [master]
> master_toml =
> base option for additional infor for parsing the toml
> like [quanities.{standard_tool}.compatible_quantities]
>
> [run]
> serial
> name
> project
> configuration =
>
> [run.{configuation}]
> serial
> name
> event_count =
> threads =
> sweeps = [thisQuantity, [these two, together], and this] # independent and entangled sweeps
> plot_points = [energy, mass] # for example, plots will be separated by grid of point based on these quantities , (only first quantities of entangled groups, if two entangled quantities are put in here)
> tools = [firstThis, [these ones, together with &], thenthis] (sequence of tool call for each point)
> tools may called via tool configuration tag
>
> [prelim]
> fifo = ["this.hepmc","that.root"]
> files =
> #for preparations required before using tools, such as what files to be created beforehand, whether normal or fifo; typically for interface files between two or more tools, you cant entrust one process to make due to capability or timing constraints, that is, tools are given agree upon file that is already made for them so neither risks inexistence error.
> #other options that need to be evaluated, or executed BEFORE running tools.
>
> [static]
> quantity = value/preset used when not sweeped
>
> [tools.{tooltag}]
> tool = "pythia"
> baseconfig =
> output_file=
> OtherToolSpecificOption =
>
> [tools.{custom}]
> tool = "custom"
> executable = /folder/file.exe
> arguments = # given in tool call
>
> [tools.{custom}.config]
> #toml options extracted into separate toml file, given as first tool arg, so it can it however it wants.
>
> #either a tool can be compatible and report state in standard manner for terminal watch; or a json or some other thing can be supplied for tool with rules for run to parse/filter stdout lines
>
> [quantities.{quantity}]
>
>
> [plot.{options}]
> ```

### Plotting

> Primary Graphics shall be done via Root, unless explictly told to use yoda. Yoda files would be
> converted to non-temporary Root files. Perhaps a legacy Paint like utils, that can be compiled as
> standalone program, and called to output based on config file. have options to decide,
> pdf/png/svg as outputs.
>
> incluce options like
> y_gutter = 1.5 (y-axis goes to 1.5*MAXY_value in plot; to make space for labels/legends)
> x_gutter =

## Commands

> make *.exe ; for *.cc to .exe for manually compiling a particular source
> similarly make *.so ; expect full paths, then determine output path based on conventions
>
> hep build ; for all modules, utils/App_*.cc, utils/Apps/*
> hep run {config} (sourced directly from ./configs/{config}, unless {config} starts with ./)
>
> utils/App_Pythia for standard pythia tool that outputs hepmc, utils/App_yd2rt for yoda to root
> conversions and so on
>
> /utils/Env/run script, dict of standard tools, in Env/{tool}/ for standard operation scripts, such
> as config parser and whatever for that respective tool.

## Answers given during planning

Asked and answered in the same session; recorded here because they are as binding as the brief.

| Question | Answer |
|---|---|
| Language of the runner (`utils/Env/run`, `utils/Env/{tool}/`) | **Python, slimmed** |
| Fate of v1's in-process `hep-run` | **Drop it** — every tool is a process |
| v1 capabilities to keep beyond `run`/`build` | **Plan + seeds + provenance**, **live terminal watch**, **YODA-side plotting**. Not kept: fits/statistics (`hep proc`), and by default bench, config migrate/reference, store commands, compare, clean, new, doctor |
| How v1 is retired | **Refactor v1 in place / build from clean slate if required** |
| Granularity of the plan | "make proper detailed plan in docs/rework_v2/; do not overfactorise into too many steps in a phase" |
| When to implement | "do not start implementation until my explicit order, now keep planning" |
| Boldness (revision, same day) | "Go over plan once more. Do not be afraid to overhaul everything and scrapping entire utils. Do not be too risk averse" |
| Standard configurations for custom tools | "How about a way for custom tools to get configuration of standard tools. Let custom tool have in running toml to have {pythia_cmnd, etc} bool options (default false) during run temp confs wil be generated as usual but tool toml will have file path options [standard.pythia_cmnd] etc which tools can retrieve themselves and use for integrated process runs" |

The last answer **supersedes** the earlier "refactor v1 in place". The first draft of this plan
(refactor in place, dual routing, v1 fixtures, 9 phases) was replaced by a clean-slate plan: see
[README.md §Decisions](README.md#decisions), V5 and V7–V10.
