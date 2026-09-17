# Expected fixture deltas — P0-S05 hotfixes (2026-09-18)

The golden fixtures were captured in P0-S04 from the pre-hotfix tools and configs, and recaptured after the
P0-S05 hotfixes. Every difference between the two captures is listed here. Anything not in this list is a
regression.

Recapture: `python tests/golden/capture_legacy.py inputs plan mini`.

## 1. Point seeds (00/B2) — every case, every point after the first

`[sweep].seed_step` went from 1 to 20 in both configs, because Pythia gives parallel instance *i* the seed
`seed + i` and both configs run 20 threads. With `seed_step = 1` neighbouring points shared 19 of their 20
random-number streams.

| Point | before | after |
|---|---|---|
| 1 | 270403 | 270403 |
| 2 | 270404 | 270423 |
| 3 | 270405 | 270443 |
| 4 | 270406 | 270463 |

`Random:seed = seed + (point − 1) × 20`. 162 `point_cmnd` texts change for this reason.

**Consequence for existing results:** the YODA files under `results/PhotoProduction` were produced with the old
seeds. Their names do not encode the seed, so rerunning a study now yields statistically independent events under
the same file name. This is 00/B1 / 00/B15 and is fixed properly by identity seeds in P1-S04. The existing files
are inventoried in `tests/golden/results_inventory.json` and move to `legacy/` in P3-S01.

## 2. Base cmnd hash — 161 point cmnd texts

`configs/PhotoProduction/photo_ep.cmnd` gained comments (00/B13, 00/B23), so the `! base sha256:` line changes
from `54435225…027b8` to `63c1c13a…2e0b2`. Physics settings are untouched.

## 3. 27x920 legends (00/B4) — 38 label strings

`√s = 95.6 GeV` → `√s = 318.1 GeV` (2·√(27.5 × 920) = 318.1). Affects the `legend` and `curve_legend` of every
27x920 point, including the default expansion of `eic.toml`.

## 4. zeus_validation `cli_across_process`: 3 points → 2

`Photon:ProcessType = 2` fails `init()` with this base cmnd (proton = beam A, photon from the lepton = beam B), so
the `direct` value was removed from the catalogue (00/B13). The page name changes with it.

## 5. `use_data` (00/B5) — no fixture change, behaviour change

`eic.toml` now has `use_data = false`. The plan fixtures do not record plot arguments, so no JSON changes; the
`legacy_run` fixtures still exercise the data path deliberately through `legacy_mini.toml`.

## 6. Unchanged, deliberately

- **The mini-run YODA files are byte-identical** (`mini_27x920_ep_{MSTW,NNLO}.yoda`), and so are the voided and
  remapped intermediates: same seeds (the mini uses 1 thread, so the B2 guard does not apply) and comment-only
  changes to the base cmnd. Attempts, written events and σ are identical: 5000/5000 and 5000/4999,
  σ = 71 422.16 pb and 72 994.84 pb. The hotfixes changed no physics.
- Point and page counts are unchanged everywhere except §4.
- `results_inventory.json` is unchanged (read-only view of pre-existing results).
