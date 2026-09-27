# 06 — Roadmap

Five phases, **2–3 steps each (13 in all)**. The detail of each phase is in its own file in
[phases/](phases/). This document is the index, the budget and the risks.

The plan was rewritten on the user's instruction *"do not be afraid to overhaul everything and
scrapping entire utils. Do not be too risk averse"*. The first draft took 9 phases and 22 steps to
refactor v1 in place, keeping v1 running beside v2 throughout. This one deletes v1 on day one and
builds the brief directly.

---

## 1. The phases

| Phase | Name | Steps | Ends with | Gate (a number) | Status |
|---|---|---|---|---|---|
| [P0](phases/P0_clean-slate.md) | Clean slate | 2 | v1 deleted; the v2 tree and Makefile in place; Rivet plugins build | `make` builds both plugins; 0 files left under `utils/` from v1 | **done** |
| [P1](phases/P1_one-chain.md) | One chain, end to end | 3 | `hep run PhotoProduction/eic single` generates, analyses, watches and records one point | legacy reference YODA reproduced bin for bin; σ at threads = 4 within 1e-6; failure injection never hangs | **done** |
| [P2](phases/P2_sweeps.md) | Sweeps | 2 | every eic and zeus configuration plans and runs, with skip-unchanged | point and page counts equal `point_counts.toml`; a rerun spawns 0 processes | **done** |
| [P3](phases/P3_results-and-plots.md) | Results and plots | 3 | YODA → ROOT, Paint pages, `rivet-mkhtml` when asked, `post`, and a new GUIDE | `energy_pdf` draws 4 pages per histogram; the gutter arithmetic is exact | **done** (style: P5 S2) |
| [P4](phases/P4_modules-and-tools.md) | Modules and the other tools | 3 | Lambda as a program; Delphes, Herwig, Sherpa, Whizard, MadGraph; the generator comparison; budget measured | each tool produces a point and passes the count check; line counts within budget | **done** |
| [P5](phases/P5_after-the-rework.md) | After the rework (the user's additions) | 1 | markers in output/, plots/root and plots/yoda, one line per point, `pre`, `plotmerge`, `hep plot` | the rows of P5 | **done** |

```
P0 ──► P1 ──► P2 ──► P3 ──► P4
        └─────────────────► P4 S1 (modules) needs only P1
```

**Why this order:**

- **Delete first (P0).** Nothing new is written in the shadow of the old, and nothing is ported by
  accident.
- **One real chain before anything general (P1).** The physics-critical parts (σ, seeds, threads,
  FIFO failure) are exercised on the smallest thing that can be wrong.
- **Sweeps next (P2).** They are what the user runs every day.
- **Plots after there are points to plot (P3).**
- **Breadth last (P4).** Each extra tool is independent and small, *once the contract is proven*.

---

## 2. How a phase is run

Light on ceremony. v1's method is in [rework_v1/05_Process.md](../rework_v1/05_Process.md); this
keeps only the parts that paid for themselves.

1. **Read** the phase file and the ledger rows it names.
2. **Mirror** the phase into `bots/current_plan.md` (per `bots/BOT.md`). Set it to *in progress*
   here and in the phase file.
3. **Do the steps in order.** Write deviations and measured numbers into the phase's **Log** as they
   happen.
4. **Run the step's verification rows.** A row that turns out to be the wrong question is replaced
   by the right one, with a sentence in the Log saying why.
5. **Commit once per step**, locally, never pushed.
6. **Mark the phase done** in both places when its gate passes.

**Approvals, asked once at the start of P0, not per step:**

- the tag;
- the P0 deletion commit;
- per-step commits;
- rewriting the TOMLs in `configs/`;
- repointing the `~/HEP/setup.sh` stub.

*All given on 2026-09-26.*

**Standing rules:**

- tests write to `output/tests/`, never to `results/` or `configs/`;
- name `encoding="utf-8"` on every text I/O (L17);
- a fake in a test has the real type (L26).

**No design is re-litigated mid-phase.** If building something shows the design is wrong, the
Log says so, the smallest fix is made, and a V-row is added to
[README.md §Decisions](README.md#decisions). v1 found about 20% of its design wrong during
building, so expect that here too and do not treat it as failure.

---

## 3. Budgets

Measured at the end of P4 with the appendix commands of
[01_Assessment.md](01_Assessment.md#appendix-reproducing-the-numbers). **Any row over 1.5× is a
finding**, recorded with its cause, not smoothed over. v1's Python came in at 3.3× its estimate
because it was sized by feel, so these are sized by surface area: commands, config sections, tools.

| Part | v1 | v2 budget | Basis | **Measured (P4 S3)** | Ratio |
|---|---|---|---|---|---|
| Runner, `utils/Env/runner/` | 17,172 | **2,000** | 12 modules (02 §3) | 3,344 (14 modules; `tools.py` 950) | **1.67×** |
| Tool folders, `utils/Env/<tool>/` | (adapters: 2,062) | **1,000** | 12 folders: `tool.toml`, `filters.toml`, and a `render.py` for 4 of them | 858 (12 folders, 3 `render.py`, 1 `backend.py`, the master) | 0.86× |
| Shell, `utils/Env/{hep, hep_env.sh, flags.sh}` | 213 | **250** | | 325 | 1.30× |
| C++ headers (`Status.hh`, `Module.hh`) | 6,546 (11 namespaces) | **320** | | 535 (163 + 372) | **1.67×** |
| C++ apps (App_Pythia, App_yd2rt, Paint) | 291 (`hep-run`) | **1,400** | 250 + 250 + 900 | 1,248 (354 + 257 + 637) | 0.89× |
| Build (`Makefile`) | 691 | **200** | | 160 | 0.80× |
| **Code total** | **~24,700** | **~5,200** | **≈ 0.2×** | **6,470** | **1.24×** (0.26× of v1) |
| Tests | 33,178 (17k data) | **~1,500** + the reference data | runner, apps, integration | 2,496 + 8,649 reference data | **1.66×** |
| Commands | 19 | **3** (`run`, `watch`, `build`) + `make` | | 3 + `make` | 1.0× |
| Config sections | 19 | **9** (the brief's) | | 9 | 1.0× |

**Three rows are over 1.5×, each a finding with its cause (P4 S3):**
- **The runner (1.67×)** was sized as 12 modules of about 170 lines. `tools.py` alone is 950: the
  whole tool-folder contract lives there (placeholders, exports and prepare on demand (V21), C6
  connections, C9 `.info` checks, card styles, the prepare key, seeds in argv). P3 and P4 added two
  modules nobody planned (`post.py`, the plot backends) and the prepare stage in `execute.py`.
  The core still names no tool; what grew is what a folder can say.
- **The C++ headers (1.67×)**: `Module.hh` is 372 lines, because the kit took on the report, the
  sidecar reader, the standard configurations (V21), `RootOut` and the integrated-program calls.
- **Tests (1.66×)**: every tool folder got plan-time tests and a slow gate, and the plot stage's
  legacy and v1 vectors were ported. The reference data are the same 8.6k lines v1 captured.

The code total is 1.24× its budget and a quarter of v1's.

---

## 4. Risks

Accepted risks are marked. Not every risk is mitigated: V5 trades some safety for speed and
clarity, on purpose.

| # | Risk | Likelihood | Impact | Response | Where |
|---|---|---|---|---|---|
| **R1** | **σ normalisation**: a CLI Rivet takes σ from the last event, and each Pythia thread stamps its own (L2, F6) | certain unless handled | every absolute number is wrong at threads > 1 | App_Pythia's writer stamps the combined σ; a gate at threads = 4 against the sidecar to 1e-6; fallback `rivet -x` | P1 S1 |
| **R2** | **FIFO failure modes**: deadlock at open, and a partial result that looks complete (L8) | high | a hang, or a wrong result | process groups, stall timeout, the sidecar count check, `.complete` written last; a failure-injection suite | P1 S2–S3 |
| **R3** | **Nothing runs between P0 and P1 S2.** *Accepted.* | certain | the user cannot run studies for that span | v1 stays one command away: `git worktree add ../High-Energy-v1 rework/v1-final`, then build it there with its own CMake | P0 |
| **R4** | **Lost in-process speed** (v1's sharded Rivet was 1.67×; the chain adds HepMC serialisation). *Accepted.* | certain | low: `photo_eic` could never shard anyway (L16) | one timing baseline from v1 before the delete (P0 S1), compared once in P1 | P0, P1 |
| **R5** | **No sharing between points**, so an analysis-option sweep regenerates. *Accepted* (V9). | certain | CPU time | the workaround of keeping events as a file plus an analysis-only configuration; trigger for per-step identity in 02 §7 | P2 |
| **R6** | **Knowledge lost with the code** | medium | a bug v1 already fixed comes back | the ledger L1–L26; each phase file names the rows it must honour, and P4's tool steps read their rows *before* writing the plugin | all |
| **R7** | **Size overrun** | medium | medium | the budget in §3, measured; over 1.5× is a finding | P4 S3 |

---

## 5. Decided during execution

Nothing blocks P0: V1–V20 are in the README. The only choices left to execution are the ones that
**need a measurement to decide**:

| Choice | Decided by |
|---|---|
| σ stamping vs `rivet -x` re-finalisation (R1) | P1 S1: whichever passes the threads = 4 gate. Stamping is tried first. |
| The watch view's refresh rate and layout | P1 S3: whatever reads well on the eic single point |
| Paint's default style (fonts, palette, canvas) | P5 S2: the user asked for rivet-mkhtml's look; the defaults copy its `default.mplstyle` |
| Whether `Phys`-style helpers come back from git | P4 S1: only if the Lambda rewrite needs more than ~50 lines of kinematics |

Each becomes a V-row when decided.
