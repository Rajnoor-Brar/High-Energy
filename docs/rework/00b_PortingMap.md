# 00b — Porting map

Date: 2026-09-17. Companion to [00_Audit.md](00_Audit.md).

This file lists every piece of existing code worth keeping, and says where it goes in the new layout and which step moves it.

- **Paths:**
  - `tools/…` is where the `~/HEP` scripts live after P0-S03.
  - `legacy/…` is where the old code lives after P0-S06.
  - Before those steps, read the same files from `~/HEP/…` or the repo root.
- **Bug IDs:** `00/Bn` refers to the defects in [00_Audit.md §4](00_Audit.md#4-current-workflow-defects-2026-09-17).
- **Rule:** new code **copies or adapts**. It never `#include`s or imports from `legacy/`.

---

## 1. `rivpyth_common.py` → `hekit` (1147 lines, no dead code)

**Flag key:**
- **PDF**: leftover from the old PDF-only sweep; it survives only as a migration message.
- **LEG**: FIFO/`path_literal`-era leftover.
- **DUP**: duplicated elsewhere.

### Config readers and validators

| Line | Name | Purpose | Target | Step | Flags / bugs |
|---|---|---|---|---|---|
| 16 | `ConfigError` | the single error type | `hekit.errors.HepError` | P1-S01 | |
| 20–65 | `get_table`, `get_string`, `get_integer`, `get_boolean`, `get_choice`, `get_string_list` | typed getters with ranges | `hekit.config.schema` validators | P1-S02 | |
| 67 | `get_serial` | `serial` 0–99 → `"NN"` | dropped; only `config.migrate` reads it | P1-S06 | LEG |
| 78 | `reject_keys` | error with a hint for removed keys | `hekit.config.migrate` | P1-S06 | PDF |
| 84 | `reject_unknown` | unknown-key error | `config.schema`, plus did-you-mean | P1-S02 | |
| 90–100 | `PDF_MIGRATION`, `MOVED_ANALYSIS_KEYS`, `MOVED_YODA_KEYS` | migration tables | `config.migrate` | P1-S06 | PDF |
| 103 | `read_config` | loads `[analysis]`/`[yoda]`/`[rivpyth]` + sweep/settle/study | `config.load` (one dataclass per section) | P1-S02 | LEG (148–152), 00/B7 |
| 157 | `validate_config` | cross-field checks | `config.validate`, run **after** study/pins are applied | P1-S03 | 00/B7 |

### Quantities and sweeps

| Line | Name | Purpose | Target | Step | Flags / bugs |
|---|---|---|---|---|---|
| 173–179 | `QUANTITY_TYPES`, `QUANTITY_KEYS`, `SWEEP_KEYS`, `SETTLE_KEYS`, `SAFE_TAG`, `SAFE_NAME` | schema constants | `config.schema` (v2 types: setting/beams/energies/seed/card/generator/events/analysis/option) | P1-S02 | `style` is LEG |
| 182–186 | `is_scalar`, `is_number` | type predicates | `config.schema` | P1-S02 | |
| 190 | `format_value` | bool → on/off; floats → `:g` | `adapters.pythia.render_value`, lossless | P1-S03 | **00/B9** |
| 199 | `sanitize` | filename-safe text | `plan.naming` | P1-S03 | |
| 203 | `normalize_setting` | canonical Pythia key for clash checks | `adapters.pythia` | P1-S05 | |
| 207 / 213 | `check_beams` / `beams_settings` | eCM or pair → frameType | `config.schema` (energies) and `adapters.pythia.render_energies`; new `render_beams` for ids | P1-S02 / P1-S05 | |
| 220 / 225 | `check_seed` / `seed_settings` | seed range; `Random:*` | `adapters.pythia`; `Parallelism:seeds` blocks | P1-S04 | 00/B1, 00/B2 |
| 229 | `check_option_value` | Rivet option value (no `:` or `=`) | `adapters.rivet`, which also validates the name against `.info` | P1-S05 | 00/B14 |
| 235–300 | `Quantity` dataclass (`value_text`, `label`, `tag`, `legend`, `settings`, `find_value`) | catalogue entry | `config.schema.Quantity` + `plan.naming` + `sweep.select` | P1-S02/S03 | |
| 303 | `Sweep` | across/overlay/only/tag_style/legends/seed_step/skip | `sweep.model`; the fields move to `[output]`/`[plot]`/`[run]` | P1-S03 | |
| 326 | `Settle` | settle settings | `config.schema.Settle` | P1-S02 | |
| 334 / 392 | `read_quantity` / `read_sweep` | catalogue parsing and duplicate-option checks | `config.schema`, `sweep.select` | P1-S02/S03 | |
| 427 / 434 | `flat_groups` / `set_groups` | group resolution; coupled length checks | `sweep.select` | P1-S03 | 00/B6 (overlay re-flattens) |
| 456 | `parse_across` | CLI grammar `a+b,c` | `cli` → `sweep.select` | P1-S03 | DUP (help text ×3) |
| 464 | `read_settle` | settle.cmnd/rivet/use/tag | `config.schema`; shorthands in `config.migrate` | P1-S02/S06 | |
| 520–530 | `STUDY_KEYS`, `check_across`, `read_studies` | study presets | `config.schema` (+ per-section overrides) | P1-S02 | |
| 561 | `parse_pin` | `KEY=SEL`; all-digit selector means index | `cli` + `sweep.select` | P1-S03 | **00/B22** |
| 569–587 | `apply_pins`, `apply_study`, `apply_overrides` | layering study → pins → CLI | `sweep.select` | P1-S03 | 00/B6, 00/B7 |

### Points, naming, provenance cards

| Line | Name | Purpose | Target | Step | Flags / bugs |
|---|---|---|---|---|---|
| 620 | `Point` | point dataclass | `plan.model.Point` | P1-S04 | |
| 631 | `expand_points` | product of groups, uniqueness, INDEX | `sweep.expand` | P1-S03 | |
| 660 | `build_point` | `claim()` clash checks; run control; seeds; analysis string | `plan.build` + `adapters.pythia` + `adapters.rivet` | P1-S04/S05 | **00/B1, 00/B2** |
| 718 / 727 / 737 / 746 | `constant_suffix`, `page_suffix`, `curve_legend`, `group_pages` | naming and pages | `plan.naming`, `sweep.pages`, `plot.select` | P1-S03/S04 | 00/B15 (one tag order) |
| 755 / 763 / 773 | `resolve_path`, `run_filename`, `resolve_yoda_file` | CWD-relative paths, serial names | `hekit.env.paths` + `hekit.results` layout; `run_filename` only for legacy lookup | P1-S01, P3-S03 | LEG, **00/B18** |
| 786 | `execution_plan` | generator/cmnd/yoda/plugin paths | `plan.build` → resolved spec v2 | P1-S05 | LEG (literal branch) |
| 803 | `write_point_cmnd` | point card with header and `! from` blocks | `adapters.pythia.render_card` + `prov` | P1-S05 | |

### Plotting

| Line | Name | Purpose | Target | Step | Flags / bugs |
|---|---|---|---|---|---|
| 831 / 837 | `plot_file_for`, `common_analysis` | `.plot` lookup; common analysis name | `plot.backends.mkhtml`, `plot.select` | P4-S01/S02 | DUP (`ydplt:57`) |
| 841 | `unify_yodas` | rename other plugins onto the common analysis | `plot.transform` | P4-S01 | 00/B17 |
| 864 | `void_bins` | NaN out empty/low-count bins (uses `/RAW`) | `plot.transform` (per-variant keys) | P4-S01 | |
| 939 | `auto_range_plot` | XMin/XMax `.plot` override | `plot.transform` + backends | P4-S01 | |
| 980–1007 | `read_yoda`, `is_reference`, `split_object_path`, `edge_index` | YODA I/O helpers | `plot.io` | P4-S01 | |
| 1014 | `align_to_edges` | trim data to MC-aligned edges | `plot.data` (also used by `compare`) | P4-S01/S04 | |
| 1047 | `remap_data_yoda` | move data under the analysis path | `plot.data`, with an **explicit map** | P4-S01 | **00/B5** |
| 1116 | `plot_arguments` | rivet-mkhtml argv (rmopts, refs, LegendOnly trick) | `plot.backends.mkhtml` | P4-S02 | |

---

## 2. Scripts → `hep` commands

| Script (lines) | Piece | Target | Step | Notes |
|---|---|---|---|---|
| `rivpyth` 93–114 | argparse (+ `--study/--pin/--across/--overlay/--style`) | `hekit.cli` (click) | P1-S01/S05 | argparse block DUP ×3 |
| `rivpyth` 117–125 | `terminate` (TERM → 5 s → KILL) | `run.supervisor` (INT → TERM → KILL ladder) | P3-S02 | |
| `rivpyth` 128–146 | `commands`, `print_point` | `hep plan` | P1-S05 | unused `config` parameter |
| `rivpyth` 149–166 | `supervise` (poll 0.2 s) | `run.supervisor` | P3-S02 | **00/B20** |
| `rivpyth` 169–222 | `run`, `run_with_fifo` (mkdtemp FIFO, env prepend, signal handlers) | `run.transport` + `env` | P3-S02 | env prepend DUP ×3; **00/B3** |
| `rivpyth` 225–263 | `main` (dry-run dir, skip_existing, point cmnd) | `hep run`, `hep plan` | P3-S05, P1-S05 | 00/B19 (fixed `/tmp`) |
| `rivpyth` 22–90 | `EXAMPLE` | `hep config init` | P1-S06 | identical to `rivpyth.example.toml` |
| `ydplt` 44–76 | per-point pages | `hep plot --points` | P4-S02 | |
| `ydmrg` 43–92 | overlay pages; yodamerge path | `hep plot`; `rivet-merge -e` for seed studies | P4-S02, P4-S05 | 00/B17 |
| `ydplt`/`ydmrg` 17–23 | `plotting_environment` | `hekit.env` (per-run `MPLCONFIGDIR`) | P4-S01 | 00/B19 |

---

## 3. `generator.cc` → `hep-run` (`Source::Pythia` + `Run`)

The behaviours to preserve and the fixes are listed in [00_Audit.md §4.3](00_Audit.md#43-generatorcc).

| Behaviour | Target | Step |
|---|---|---|
| Cards read in order, later wins; failure → exit 1 | `Source::Pythia` | P2-S04 |
| `Print:quiet` default; cards may re-enable output (goes to the log) | `Source::Pythia` + supervisor log | P2-S04, P3-S02 |
| Runner owns `processAsync` | `Run` concurrency mode | P2-S04, P6-S01 |
| Output opened only after `init()` | `Run` + sinks | P2-S04 |
| `Pythia8ToHepMC` conversion | `Events::View` (lazy, per worker) | P2-S04 |
| Exit 2 = usage, 1 = card/init | exit-code table (06 §3.3; init → 3) | P2-S04 |
| **Fix:** merged σ, write-failure exit, disjoint seeds | `Run`, `Results`, `Store`, planner | P2-S02/S05, P1-S04 |

---

## 4. Legacy `utils/` → new namespaces

| Legacy source (`legacy/utils/…`) | Take | Target | Step |
|---|---|---|---|
| `Utility/Sha256.hh` (whole) + FIPS vectors `legacy/tests/test_utils_hardening.cc` (~129–153) | copy; add a regular-file check | `Core/Sha256.hh` | P2-S03 |
| `Utility/Signals.hh:22-57` + cooperative skip `legacy/lambda/sources/_Lambda_Data.cc:43-50` | adapt to `sigaction` + atomic flag | `Core/Signals.hh`, `Run` | P2-S03, P2-S04 |
| `Utility/Time.hh:15-21`, `durationString` :46 | wall vs monotonic clock aliases; plain-mode durations | `Core/Clock.hh` | P2-S03 |
| `Utility/Paths.hh:25-54` | env var → walk up to an anchor (rename to `HEKIT_ROOT`) | `Core/Paths.hh`; `hekit.env.paths` | P2-S03, P1-S01 |
| `Utility/Toml.hh:75-92` | idea: `requirePositive` with key context | `hekit.config.schema` | P1-S02 |
| `Physics/Particles.hh:24-58`, `Physics/Types.hh:51-113`, `Physics/Kinematics.hh:24-41` | self-keyed trait tables with `static_assert`; PDG table; ΔR/Δφ/mass | `Phys` | P8-S02 |
| `Monitor/Timer.hh` (whole, standard library only) | copy | `Status/Timer.hh` (optional) | P2-S03 |
| `Monitor/Threading.hh:121-136, 212-213, 256-265` | deadline loop; coalescing | `Status/Heartbeat.hh` | P2-S03 |
| `Monitor/Threading.hh:97-116` | stall predicates (monotonic idle ≥ threshold) | `hekit.run.supervisor` | P3-S02 |
| `Record/Meta.hh:25-110, 243-299` | provenance field list; git/host/compiler capture | `Core/Provenance.hh`, `hekit.prov` | P2-S03, P3-S03 |
| `Record/Recording.hh:204-231` | write to `.tmp`, then atomic rename | `Results/Writer.hh`, `Store` | P2-S05, P5-S01 |
| `Record/Cloning.hh:31-47, 82-86` | per-worker clone, merge by add | `Results` (YODA shards) | P8-S01 |
| `Record/Declaration.hh` (validation) | name/shape/duplicate checks at declare time | `Results::Booker` | P8-S01 |
| `Record/Type_Methods.hh:11-27` | enum-keyed ids + hash | `Results` (optional) | P8-S01 |
| `Record/Threading.hh:116-236`, `Record/Lifecycle.hh:76-95` | quiesce/barrier; fatal write with timeout | `Run` (checkpoints) | P6-S01 |
| `Probe/Lifecycle.hh:229-267` | bounded queue with backpressure, stop, workers-finished | `Source` (replay reader → consumers) | P5-S02 |
| `Probe/Types.hh:148-203` | access patterns (labelled collections, typed columns, per-event scalars) | `Events::View` accessors | P2-S04, P8-S01 |
| `Config/Reader.hh:79-102`, `Monitor/Configure.hh:20-60` | "removed; use X" tables | `hekit.config.migrate` | P1-S06 |
| `Paint/Resolve.hh:124-140, 269-280` | preset chain with cycle detection; glob → regex | `hekit.plot` (optional) | P4-S03 |
| `configs/defaults/Paint.toml`, `misc/root_macros/saveHist.C:20-177` | house style (fonts 43, margins .12/.05/.12/.08, 900×600, blue palette) | `hekit/plot/styles/hekit.mplstyle` | P4-S03 |
| `configs/defaults/Limits.toml` | RangeSize binning presets (GeV) | optional binning presets for modules | P8-S01 |
| `configs/templates/Record.toml:172-184`, `[record.metadata]` keys | naming and metadata vocabulary | `07_Outputs.md` provenance fields | P3-S03 |

**Dropped outright:**
- `Utility/RootTypes.hh`, `Utility/RootAid.hh`, `Utility::numberString`, directory-merge TOML;
- `Probe/*` readers;
- `Record` TTree/TH* writing;
- `Paint` rendering;
- `Config::Register`/`Watch` scaffolding.

---

## 5. Lambda (archived; for a future revival only)

| Lambda piece | Future home | Note |
|---|---|---|
| `harvestParticles` (`isFinal`, pid 2212/−211) | `Phys` selectors on `GenEvent` | Add Λ̄ |
| `reconstructCandidates` | a module: pair-in-window + greedy unique | The angle cut is dead (cos θ ≡ −1); rethink `reserved_protons` |
| `declareObjects` (21 histograms) | `Module::book` (YODA) | Pz range must be symmetric |
| mass-peak study | `hep proc` fit | Generator level is a spike: needs smearing or truth matching |
| `.cmnd` | fix before reuse | Delete the Ne20 redefinition (line 14), the duplicate `SigFitNGen`, and the Pb `SigFitDefPar` |

Estimated effort: about 1.5 d for a faithful port, 3–4 d with fixes and fits. See `legacy/README.md` (P0-S06).
