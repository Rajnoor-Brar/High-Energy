# 07 — Consistency across the whole framework

01–05 audited `utils/`. This file widens the view to `modules/`, `configs/`, the Makefile, `docs/`, `tests/` and `bots/`. The IDs are **K1…**.

Line numbers are for the working tree on 2026-10-03, which includes the user's uncommitted config changes. The files under `configs/` are the user's: findings there are reported, and changing them needs an order.

---

## Modules

### K1 — `Inproc` copies `App_Pythia`

`modules/PhotoProduction/Inproc/` re-implements what `utils/App_Pythia.cc` does:
- **σ combination:** `Stamp.hh:74-92` (`Instance`, `Xsec`, `combine`) is almost line for line `App_Pythia.cc:146-161`;
- **the event stamp:** `Stamp.hh:35-50` repeats the one event numbering, the one run info and the L2 re-stamp of `App_Pythia.cc:331-344`;
- **setup and running:** `Engines.hh` copies the card setup, `processAsync`, the L6 chunking and the converter per instance.

docs/06 says a helper needed by a second program moves into `utils/`, and this one now qualifies.

**Fix.** L16: a Pythia kit header shared by both.

### K2 — …and has already drifted from it

- **Seeds:** `Inproc` lacks the L4 check, one seed per thread and each in range (`App_Pythia.cc:262-273`).
- **Thread count:** `numThreads ≤ 0` resolves to the hardware's count in `App_Pythia.cc:260`, but to `max(1, …)` in `Engines.hh:211`. So with a card that leaves threads at 0, the two programs chunk differently. That contradicts the claim that `Inproc` does "the same work as App_Pythia".
- **Weights:** `Analysis.hh:133` re-implements `Module::Event::weight()`.

### K3 — `InprocJets` breaks the kit's contracts in three small ways

- **Exit code:** a Rivet write failure exits **70** (Internal) instead of **5** (Output) (`InprocJets.cc:51-52`).
- **Report:** `job.setCrossSection` (`InprocJets.cc:54`) leaves `haveSidecar_` false, so the report says `"sigma_from": "events"` although σ is the generator run's.
- **Requires line:** it includes FastJet and SISCone (`Inproc/Analysis.hh:23-26`, and calls `siscone::ranlux_*`), but `fastjet` is not in its `// requires:` line. Linking works only because `rivet-config` happens to pull FastJet in.

### K4 — Defaults that disagree, and defaults written in four places

- **`reserved_protons`:** **20** in `Lambda/Reconstruction.hh:39`, but **2** in `Lambda.cc:59`, `Lamriv.cc:39`, `Lamriv.info` and the README.
  - **What it is:** in the Λ reconstruction, the greedy p–π⁻ matching keeps at most (protons − `reserved_protons`) candidates, since beam-remnant protons cannot come from a Λ (`Reconstruction.hh:126-129`).
  - **What is actually used:** 2, everywhere. Both front-ends always set it (`Lambda.cc:59` from the config, default 2; `Lamriv.cc:39` from `RESERVED`, default 2), and `lambda.toml` keeps v1's 2 on purpose. The struct's 20 is never reached.
  - **Decision (the user, 2026-10-03):** Lambda is an abandoned project, kept only as a reference for the Pythia → ROOT module workflow. So no physics question: the struct default becomes 2, matching what runs. `Lambda.cc` and `Lamriv.cc` take the default from `Cuts{}` instead of repeating the literal. Results are unchanged.
- **Lambda's cuts and axes:** their defaults appear in `Lambda.cc:57-66`, `Lamriv.cc:37-80`, `Lamriv.info:168-179` and `lambda.toml:85-91`; the TOML copy is partial.

The same lesson as C2, at module level: a default should live once, preferably in the `.info`, which Rivet already reads. A kit program can read the same values.

### K5 — Naming

- `Reconstruction.hh` uses snake_case members (`mass_tolerance`, `proton_index`), against the camelCase rule in docs/06 and BOT.md.
- The program is `InprocJets`, but the configs are `InProcEIC` / `InProcZeus`.

### K6 — `delphes_jets.py`, a custom tool, follows none of the conventions

It has no status protocol, and its usage errors exit 1 through `sys.exit(str)` (`delphes_jets.py:37`) instead of 2. A small Python counterpart of the module kit (`utils/Env/kit.py`: arguments, status lines, exit codes, the report) would make custom Python tools behave like `Module.hh` programs.

---

## Rivet plugins

### K7 — `Lamriv`

- **Lost labels:** with `SET` ≠ `all`, histograms are booked without the `<set>_` prefix (`Lamriv.cc:70`), so the `.plot` patterns `/Lamriv/.*_mass` no longer match, and `lambda.toml`'s `sets` configuration draws pages with no labels.
- **Incomplete docs:** the option list in the header (`Lamriv.cc:12-18`) names 7 of the 12 options.
- **Repeated reads:** `getOption` is called again and again inside the booking loop (`Lamriv.cc:73-80`).

### K8 — `photo_eic`

- **η axes ignore the options:** the η axes are fixed at 28 bins over −3.5…3.5, and 0…3.5 for |η| (`photo_eic.cc:110-119`), and so are the η slice edges (`:163-169`). Neither follows `ETAMAX` / `CHETAMAX`.
- **Legends hard-code the cuts.** The `.plot` legend titles state the default cuts (acknowledged at `.plot:1-2`), so sweeping `ETMIN`, `ETAMAX` or `R` gives wrong legends. Placeholders (F7: `{opt:ETMIN}`) are the general fix.
- **A constant written twice:** the SISCone overlap 0.75 is hard-coded in `photo_eic.cc:81` and again in `Inproc/Analysis.hh:155`.
- **v1 vocabulary:** `photo_eic.cc:7` still speaks of `[static.rivet].options` and `[sweep.rivet.*]`.
- **Label style is mixed:**
  - `$E_T > 5$` sits beside `$E_T^{jet} > 5$`;
  - `\GeV` sits beside plain "GeV";
  - d15 and d16 are in swapped order in the `.plot`.

---

## Configs (the user's files: reported only)

### K9 — The state of `configs/PhotoProduction/`

- **`xx/` is a deliberate stash** (the user, 2026-10-03): the Herwig, Sherpa, Whizard, MadGraph and Delphes configs written while the config input was being standardised, unused by PhotoProduction and kept for reference. That they don't resolve from there is expected. What remains to fix is that the tests used them (K13: frozen fixtures), and that `eic.toml` still has a live `[tools.delphes]` table pointing at a card that is now stashed (unused by its active configuration). The details:
  - Baseconfigs in `xx/*.toml` resolve under `configs/PhotoProduction/` (one convention root, `paths.py`), so the Herwig, Sherpa, Whizard and MadGraph runs fail with "base config not found".
  - `eic.toml`'s `[tools.delphes]` baseconfig (`delphes_card_ATLAS.tcl`) now exists only in `xx/`.
  - The usage lines in the `xx/` files are stale.
- **Comments that are wrong:**
  - `eic.toml:17` and `InProcEIC.toml:30`: "ETMIN/ETMIN2 defaults are 17/21 GeV in the source". The source says 5/10 (`photo_eic.cc:53-54`).
  - `eic.toml:3` names `pdf` as the default configuration; it is `single`.
  - `zeus_validation.toml:11`: "1M for the PDFs, 200k for the MPI scans". The counts are 10M–200M.
  - `InProcEIC.toml` and `InProcZeus.toml` claim "the same quantities, statics and configurations" as their twins. They differ in static energies and `pt0ref`, value order, labels and plot settings.
  - `InProcZeus.toml:16-17`: the recipe to reproduce zeus_validation's seeds can't work, since that file now uses `seed_type = "random"`.
- **Copies:**
  - `energies` is declared in 5 files plus 4 in `xx/`, `lepton` in 5, `pdf` in 5 (with three spellings of PDF4LHC21), and `pt0ref` in 5 (with two value sets).
  - The identity map from ZEUS d01–d12 to `/REF/…` is written four times.
  - The pythia, rivet and yd2rt tool tables are in every file.

  These are F1 and F2's cases.
- **Style drift:**
  - `backend` is a list in some files and a string in others;
  - `min_entries` is `0`, `1` or `"default"`;
  - label padding is `PDFs_010M` in one file and `Energies_01M` in another;
  - the 27.5 GeV beam is tagged `27x920` but labelled `27.5x920`;
  - the e⁻p lepton tag is `em` in one file and `pe` in another.
- **Native cards:**
  - `photo_ep.cmnd` and `photo_zs.cmnd` set `Main:numberOfEvents`, `Random:*` and `Beams:*`, and the runner overrides every one of them (C6).
  - `photo_ep.cmnd:3-10` and `lambda.cmnd:7` still use v1 vocabulary.
  - `lambda.cmnd` contradicts itself. Its header says "soft-QCD pp", but it runs Angantyr Ne–Ne. It turns `SoftQCD:nonDiffractive` on (`:11`) under an "inelastic only" header, while `SoftQCD:inelastic = off` (`:44`). It sets `HeavyIon:SigFitNGen` twice (`:35, 38`). And it has comments orphaned from the lines they describe.
  - L14a (a clean combined card) would make what actually runs visible.

---

## Build

### K10 — The Makefile and docs/06 disagree

| docs/06 says | The Makefile does |
|---|---|
| "every non-parked `modules/**` program" is built (`06:57`) | `wildcard modules/*/*.cc` (`Makefile:73`): a program in a subfolder is never built |
| every source has a `// requires:` line (`06:337`) | none of the three Rivet plugins has one, and the Rivet rule never reads it |
| (nothing) | `-DHEKIT_WITH_HEPMC=1` (`Makefile:118`), which no source tests |
| the library table (`06:71-79`) | `KNOWN` (`Makefile:43`) adds geant4, onnx and delphes |

---

## Docs and the record

### K11 — The manual has drifted from the code

- **The runner's rank table exists three times,** and the copies disagree:
  - `runner/__init__.py:6-11` lists `status_client` (which doesn't exist) and leaves out `post`;
  - `tests/runner/test_imports.py:18-25` has both;
  - `02_Architecture.md:85-99` lists `post` only.

  Keep one table, read by the test.
- **"C1–C13"** in `02:17` and `README.md:25`, though C14 exists (`config.py:385`, `04:794`). 06's list of where each check lives (`06:163-164`) leaves C14 out.
- **02 is behind on execution:**
  - it says points run "one after another" (`02:160, 246`), while V36's `parallelism` runs several at once (as `02:349` itself says);
  - its run order (§5 step 6) leaves out the combined stage (V35).
- **06 is behind on the data model and tests:**
  - its data model (`06:105-106`) lacks `combine`, `parallelism`, `swept`, `title`, `run_name`, `seed_type`, `manual_seed` and `sweep_runs`;
  - its test list (`06:356-357`) lacks a dozen files;
  - it gives the Makefile's length as 160 lines; it has 161.
- **05:**
  - its tool table gives Sherpa `status = filters`, but `utils/Env/sherpa/` has no `filters.toml`, so the loader quietly gives it no rules;
  - its §5/§6 titles say `merge` runs "in `post`", though it also serves shards and `combine`.
- **`utils/Env/run:3`** says only `hep run` and `hep watch` land there; `hep plot` does too.
- **Words with several meanings:**
  - "run" is the TOML file in 02, but one configuration's execution in `cli.run_one`, `sweep_runs` and the `run NN` header;
  - "swept" means a quantity in `sweeps`, and also the configuration key `swept` (C3);
  - "label" means a configuration's folder, and also a value's legend text in `points.json`.
- **A stray file:** `docs/Untitled-1.md` is an untracked file of the user's in the manual's folder.

### K12 — The record and its IDs

- **V43 was replaced by V45/V46,** but the code cites "V43, V45" side by side (`config.py:406`). The record should mark V43 as superseded.
- **V20** (`07:203`) says `docs/rework_v1/` is kept. It isn't; `docs/README.md:33` points to git history instead.
- **ID namespaces clash.** The record has C-rules (in 04 §13), F-findings, an L-ledger, R-risks and V-decisions. This audit's C/F/L/B IDs collide with the first three, and `bots/intent.md` reuses "C1" and F-numbers for its own items.

  **The rule this plan adopts:**
  - audit IDs are cited as "audit C6", and only in `docs/audit_1/` and `bots/`;
  - code and the manual cite only the V-entry made when an item lands;
  - intent.md's items get their own prefix (`I1…`).

---

## Tests

### K13 — Tests depend on the user's files, and repeat each other

- **Seven near-identical `hep_run` wrappers,** each setting `HEKIT_OUTPUT` and `HEKIT_RESULTS`:
  - `test_gates_shards.py:60`, `test_process_generators_p4.py:25`, `test_generators_p4.py:29`, `test_modules_p4.py:28`;
  - `test_gates_seeds.py:49`, `test_gates_parallel.py:67`, `test_gates_run_sweep.py:79`.

  Two more files set the same environment inline. `plans()` and `plans_of()` are repeated in three runner tests. None of these are in `tests/runner/helpers.py`.
- **About 25 tests load the user's live configs,** and fail whenever they are edited or moved:

  | Test | Configs it loads | State in the working tree |
  |---|---|---|
  | `test_sweeps.py:31-90` | `eic.toml`, `zeus_validation.toml` (the count gate, seed disjointness, pages, the consumer table) | edited |
  | `test_generators.py:99-129` | `sherpa`, `herwig` | **moved to `xx/`** |
  | `test_process_generators.py:77` | `madgraph` | **moved** |
  | `test_paths.py:26, 54-56` | `photo_ep.cmnd`, `eic.toml` | edited |
  | `test_generators_p4.py:44-73` (slow) | `eic`, `sherpa`, `herwig` | **moved** |
  | `test_process_generators_p4.py:35-59` (slow) | `madgraph`, `whizard` | **moved** |
  | `test_modules_p4.py:59-113` (slow) | `eic`, `InProcEIC`, `InProcZeus`, with hard-coded serial folders | tied to serials |

  docs/06 (`:412-413`) describes `test_sweeps` as pinning seeds shared across configurations, but those configurations come from the live `eic.toml`.

  **Fix:** frozen copies under `tests/fixtures/configs/<Project>/`, loaded as `./tests/fixtures/…`. Your configs are then yours again, and a test failure means the code changed.
- **`conftest.py:20-21` uses `os.environ.setdefault`.** If `HEKIT_RESULTS` or `HEKIT_OUTPUT` is set in your shell (04 invites it), the tests write to your real locations. It should set them unconditionally.
- **The guard is too narrow.** It compares modification times under `configs/` only (`conftest.py:34-39`). `results/`, `modules/` and `tests/reference/` are unguarded, and any edit you make to `configs/` during a slow run fails the session (the "one pytest session at a time" memory).
- **A relative path:** `--basetemp=output/tests/pytest` (`pytest.ini:3`) works only from the repository root.

---

## Bots and naming

### K14 — `bots/`

- **`current_plan.md` (737 lines) is an append-only log.** It carries the whole finished v1 plan (from line 230), P0 notes and every finished task. It should hold what is current. Everything finished moves to `bots/archive.md`, or to the record, which already holds the decisions.
- **`BOT.md:32-33`** describes the P0 deletion of v1: history, not a rule.

### K15 — v1 names in the public interface

`HEKIT_ROOT`, `HEKIT_OUTPUT` and `HEKIT_RESULTS` (`paths.py:25-27`, `hep`, `hep_env.sh`) and `-DHEKIT_WITH_HEPMC` are v1's "hekit" name. They are documented and consistent, but they are the last visible piece of v1.

**Options:**
- rename them to `HEP_ROOT` and friends, keeping the old names as fallbacks for one phase;
- or keep them and call "hekit" the kit's name on purpose.

This is the user's call.

---

## The same patterns, across the framework

1. **A fact written in several places drifts.** This has happened in:
   - `utils/` (C2, the schema);
   - `modules/` (K1, σ; K4, cuts);
   - `configs/` (K9, quantities and data maps);
   - `docs/` (K11, the rank table).

   The remedy is the same each time: one source, read by the others.
2. **"Same as X" comments are unchecked claims, and several are false** (K9). Inheritance (F1, F2) replaces the claim with a mechanism.
3. **v1 vocabulary survives in comments,** in `photo_eic.cc`, `photo_ep.cmnd` and `lambda.cmnd` (K8, K9). One `grep -rn 'static\.rivet\|sweep\.\|\[beams\]' modules configs` finds them.
4. **Tests that read the user's files fail for reasons that aren't regressions** (K13). This has been the main source of noise in every recent test run.
