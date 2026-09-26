# P2 — Sweeps

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| **done** (2026-09-26) | 2 | P1 | every eic and zeus configuration plans and runs; quantities are checked for consumers; reruns are free | 2026-09-26 |

## Goal

From one point to all of them:

- quantities, the master TOML and static values;
- the consumer check, which refuses a quantity that no tool uses;
- sweeps, as a grid of independent axes and a zip of entangled ones;
- identity seeds and skip-unchanged.

After this phase, the user's daily work (eic studies) runs on v2.

Design: [04_Config.md](../04_Config.md) §§2, 4, 6, 8.1, 10; [02 §7](../02_Architecture.md#7-identity-seeds-and-skip).
Ledger: **L4, L19, L23**.

---

## S1 — Quantities, the master TOML, and the checks

**Tasks**

1. **`utils/Env/master.toml`**: the Pythia mappings from [04 §2](../04_Config.md#2-master)
   (energies, sqrts, beam_a, beam_b, pdf, events, threads). Also the optional project overlay
   (V17).
2. **`quantities.py`**:
   - resolve `[static]` and per-configuration `static`, as tag, then value, then `#N`;
   - resolve each quantity's consumers from `target`, `key` and the master
     ([04 §6.1](../04_Config.md#61-quantitiesq));
   - the built-in `events`, `threads` and `seed`;
   - the `replica` seed-only target.
3. Point-card rendering with overrides grouped by origin, plus **one owner per native key** (C8).
   An override equal to the base card's value still renders, but does not change the identity.
4. **The checks:**

   | Rule | Check | Ledger |
   |---|---|---|
   | C3 | entangled groups have equal lengths | — |
   | C4 | `plot_points` ⊆ `sweeps` | — |
   | C7 | every active quantity has a consumer | — |
   | C9 | Rivet options are declared in the `.info` | L19 |
   | C10 | PDF sets are installed (`lhapdf ls --installed`) | — |
   | C11 | point names are unique | — |

5. `--plan` prints the **quantity × tool consumer table**.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | a quantity swept with no consumer | plan-time error naming the quantity and the chain |
| 2 | a Rivet option not in `photo_eic.info` | plan-time error (L19) |
| 3 | a PDF set that is not installed | plan-time error with the `lhapdf install` hint |
| 4 | `--plan` for a config with `pdf` + `lepton` + `pt0ref` | consumer table: all three → pythia, and the rendered override lines, snapshot-tested |
| 5 | two sources for `PDF:pSet` (a static value and a `key` override) | error (C8) |

---

## S2 — Sweeps, seeds, skip, and the real configs

**Tasks**

1. **`sweep.py`** (~150 lines):
   - points from `sweeps`: string entries are grid axes, list entries zip;
   - point names are the tags joined in `sweeps` order;
   - pages from `plot_points` (drawn in P3).
2. **Seeds from identity** ([02 §7](../02_Architecture.md#7-identity-seeds-and-skip)): a block of
   `threads` seeds in 1…9·10⁸ (L4), checked for overlap across the plan and moved up on a clash.
   The Pythia card always gets `Random:setSeed = on` and `Random:seed = <first>`, plus
   `Parallelism:seeds` at threads > 1, so a serial in-process Pythia is seeded too (02 §7).
3. **Skip-unchanged** through `.complete` and the identity; `--rerun`; `--points <sel>`;
   `--set <key>=<value>`.
4. **`points.json`**, the manifest used by P3.
5. **Translate** `configs/PhotoProduction/eic.toml` (all eleven configurations) and
   `zeus_validation.toml` to v2, following
   [04 §8.1](../04_Config.md#81-configsphotoproductioneictoml) (**approval**: `configs/`). Carry
   the v1 file's physics comments across, especially the reference-data map's justification (L18)
   and the `process`/`pthatmin` notes (L23).

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `--plan` point and page counts for every eic and zeus configuration, against `tests/reference/point_counts.toml` | all equal: `pdf` (4, 1), `energy_pdf` (16, 4), `mpi` (3, 1), `mpi_grid` (6, 2), `radius` (3, 1), … |
| 2 | `hep run PhotoProduction/eic pdf` at 50k events | 4 points, each with `.complete` and provenance |
| 3 | the same command again | **0 processes spawned**; "4 points complete" |
| 4 | change `threads` | every point reruns, and `--plan` says so beforehand |
| 5 | seed blocks across all eic configurations | disjoint |
| 6 | `hep run PhotoProduction/eic pdf --points MSTW08lo --rerun` | exactly 1 point runs |

**Done when** every row of S1–S2 passes.

---

## Rollback

Revert the step commits. The v1 configs are in git at `rework/v1-final`.

## Log

### S1 — 2026-09-26 — done

Most of S1 had come forward in P1 S2 (`quantities.py`, `sweep.py`, the master TOML, the consumer
table). Added here:

- **C9.** The rivet folder's `[checks]` says where `.info` files are (`build/Rivet/` and
  `rivet-config --datadir`). An unknown analysis is refused, and so is an option its `.info` does
  not declare.
- **C10.** A master mapping can carry `check = "lhapdf"`, and a PDF set missing from
  `LHAPDF_DATA_PATH` is refused with the `lhapdf install` line to type.
- **Redundant overrides.** An override equal to the base card's value (e.g. `pT0Ref = 3.2`) is still
  written, but no longer changes the identity.

| Row | Result |
|---|---|
| 1 | (S2 row 1 below) |
| 2 | A swept quantity nobody consumes: refused (C7, `test_plan.py`) |
| 3 | Entangled groups with unequal lengths: refused (C3, `test_config.py`) |
| 4 | The `--plan` consumer table of `energy_pdf`: energies → pythia `[Beams:eA, Beams:eB]`, pdf → `PDF:pSet`, lepton (static) → `Beams:idB` (`test_sweeps.py`) |
| 5 | Two sources for `PDF:pSet`: refused (C8) |

### S2 — 2026-09-26 — done

| Row | Result |
|---|---|
| 1 | **Point and page counts equal the legacy table for all 12 cases** (11 eic configurations incl. the default, plus zeus): `energy_pdf` (16, 4), `mpi_grid` (6, 2), `radius` (3, 1), and so on. `single` has 1 page in v2 against 0 in legacy, by design; the table's `pages_v2` column records it. |
| 2 | `hep run PhotoProduction/eic pdf` at 50k events: 4 points, all with `.complete` and provenance, 2 min 33 s |
| 3 | The same command again: **0 processes**; "4 skipped" |
| 4 | With `--set run.pdf.threads=8`, `--plan` marks all 4 points "to run" (the seed block depends on the threads) |
| 5 | Seed blocks across every eic configuration are disjoint (`test_sweeps.py`) |
| 6 | `--points MSTW08lo --rerun`: exactly 1 point runs |

- **`zeus_validation.toml` translated.** Its beams, fixed in v1's `[beams]`, are now static
  quantities, and its lepton is still e+ via `lepton = "ep"`.
- **`points.json` lists every point** (values with tags and labels, page, products, identity, seed,
  complete), even under `--points`. `plan.json` is dropped: `points.json` carries the same content.
- Tests: `tests/runner` 71 (`test_sweeps.py` +21, including the 12-case count gate); `make test` 79.
