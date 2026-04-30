# Configuration & Probe Data Pipeline Report

This report analyzes the current data configuration pipeline, specifically focusing on the extraction of "particles" via the `Config`, `Probe`, and `Lambda` namespaces.

## 1. Current Possible Pipelines (TOML → `rootAnalysis`)

There are currently two distinct configuration paths for defining the extraction of particle data from a ROOT file. One is defined but inactive, while the other is active but improperly nested within module-specific code.

### Pipeline A: The Config/Probe Path (Inactive)
*   **TOML Definition:** The user specifies an `event_particles` array under the `[probe]` section (e.g., `["protons", 0, "Protons", ["pX", "pY", ...], ...]`).
*   **Parsing (`Config::readProbeSection`):** This reads `[probe]` into `Config::ProbeConfig::particles` (a `std::vector<Config::ProbeParticle>`).
*   **Data Representation:** `Config::ProbeParticle` stores the label, spec ID, tree name, branch names (`momentaBranches`), branch type, and index branch.
*   **Conflicts & Usage:** Despite being fully parsed and available, **this data is entirely ignored** by the reconstruction driver. There is no logic mapping `Config::ProbeConfig` to `Probe::CollectionSpec`.

### Pipeline B: The Lambda Module Path (Active)
*   **TOML Definition:** Expected under `[input]` and `[candidates]` sections, but these are notably absent from the current `Lambda_Reconstruction.toml`.
*   **Parsing (`Lambda::loadInputSection`, `Lambda::loadCandidatesSection`):** Reads configuration into `Lambda::InputConfig` and `std::vector<Lambda::CandidateConfig>` within `Lambda::Parameters`.
*   **Data Representation:** 
    *   `Lambda::InputConfig` defines the coordinate branch names (`pX`, `pY`, `pZ`, `Energy`) and the `indexBranch`. Defaults are hardcoded.
    *   `Lambda::CandidateConfig` defines the `label`, `enabled` status, `writeTree`, and `pidAbs`. Defaults are "Protons" (2212) and "Pions" (-211).
*   **Schema Construction (`Lambda::inputSchema`):** Converts the `InputConfig` and `CandidateConfig` lists manually into `std::vector<Probe::CollectionSpec>` objects. 
*   **Data Delivery:** `_Lambda_Reconstruction.cc` directly calls `Probe::runParallel(..., Lambda::inputSchema(physParams), ...)`. `Probe` reads the ROOT trees based on this schema and builds `Probe::Event` maps (`ev["Protons"]`, `ev["Pions"]`).
*   **Usage Site (`Lambda::rootAnalysis`):** Extracts particle collections via `ev[protonLabel]` and `ev[pionLabel]`, dynamically resolving labels using the PID fallback mechanism in `Lambda::ParamAid::resolveCandidateLabels`.

## 2. Conflicts, Overlaps, and Messiness

*   **Config Undercutting:** The user's configuration in `[probe] event_particles` is undercut by `Lambda::Parameters`'s hardcoded fallback values for `[input]` and `[candidates]`. The actual active branches read from the ROOT tree have nothing to do with `[probe]`.
*   **Type Duplication:** `Config::ProbeParticle` and the combination of `Lambda::InputConfig` + `Lambda::CandidateConfig` represent the exact same concept: mapping tree branches to physical collections.
*   **Violated Domain Boundaries:** `Lambda` (a specific physics module) is dictating generic ROOT file I/O schemas (`Probe::CollectionSpec`) via `Lambda::inputSchema`. `Lambda::Parameters` is polluted with branch names and coordinate specs.
*   **Brittle Label Resolution:** `Lambda::ParamAid::resolveCandidateLabels` does a reverse-lookup to find a label matching a specific absolute PID, rather than just explicitly receiving the labels it needs to analyze from the generic configuration.

## 3. Streamlining the Pipeline

To resolve this mess and prefer generic `Probe` and `Config` workflows over module-specific `Lambda` workarounds, the pipeline should be streamlined as follows:

### Step 1: Commit to the `[probe]` Schema
Remove `[input]` and `[candidates]` sections from `Lambda::Parameters` entirely. The `[probe] event_particles` block should be the single source of truth for branch-to-collection mapping.

### Step 2: Establish `Config` → `Probe` Translation
Move schema construction out of `Lambda`. Add a conversion utility in `Config` (e.g., `Config::toCollectionSpecs(const Config::ProbeConfig&)`) that translates `Config::ProbeParticle` directly into `Probe::CollectionSpec`. 

### Step 3: Decouple `Lambda::Parameters` from I/O
Delete `Lambda::InputConfig`, `Lambda::CandidateConfig`, and `Lambda::inputSchema`. `Lambda::Parameters` should only care about the physics cuts, tolerances, and the string names of the collections it needs to read from `Probe::Event`. 

### Step 4: Simplify Delivery
Update the driver `_Lambda_Reconstruction.cc` to construct `CollectionSpec` from `Config::ProbeConfig` and pass it to `Probe::runParallel`. `Lambda::rootAnalysis` can then directly access the particles using explicitly configured labels (e.g., `ev["protons"]`, `ev["pions"]`), bypassing the convoluted PID-based label resolution.

**Resulting Cohesive Pipeline:**
`TOML [probe]` → `Config::ProbeConfig` → `Config::toCollectionSpecs()` → `Probe::CollectionSpec` → `Probe::runParallel` → `Probe::Event` → `Lambda::rootAnalysis(ev["protons"], ev["pions"])`.

## 4. Features in Pipeline B (Lambda) Absent from Pipeline A (Probe)

While Pipeline A is more generic and structurally sound, Pipeline B currently provides several convenience features and configurability options that Pipeline A lacks. If transitioning to Pipeline A, these features must either be ported over or explicitly deprecated:

*   **Global Kinematic Branch Definitions (`[input]`):** Pipeline B allows the user to define common branch names (`index_branch`, `energy`, `px`, `py`, `pz`) *once* globally in the `[input]` section. Pipeline A's `event_particles` array requires the user to repeat the `momentaBranches` and `indexBranch` individually for every single particle collection, leading to verbose and repetitive configuration.
*   **Toggleable Collections (`enabled`):** Pipeline B's candidate tables support an `enabled = false` flag, allowing users to easily toggle specific particle collections on or off without deleting their configuration blocks. Pipeline A requires completely removing the entry from the `event_particles` array to disable it.
*   **Implicit Tree Name Resolution (`resolveTreeName`):** Pipeline B provides a fallback mechanism (`Lambda::defaultTreeName`) that automatically derives the expected ROOT tree name by capitalizing the first letter of the candidate label if a specific `tree_name` isn't provided. Pipeline A currently expects all fields to be explicitly defined.
*   **PID Association (`pid_abs`):** Pipeline B explicitly associates each configured candidate with an absolute Particle ID (e.g., `pid_abs = 2212` for Protons). This allows `Lambda` to dynamically identify which configured label corresponds to which physics particle using `resolveCandidateLabels`. Pipeline A does include a numeric `spec` field, but lacks the established logic bridging it to physics PIDs.
*   **Output Tree Control (`write_tree`):** Pipeline B includes a `write_tree` flag that dictates whether a specific candidate collection should be serialized out to new ROOT trees during the data generation phase. Pipeline A only models the configuration required for *reading* data.
