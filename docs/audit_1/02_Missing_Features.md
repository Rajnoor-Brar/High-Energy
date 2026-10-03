# 02 — Features one would expect, and that are missing

These features are ordered by how often their absence costs time in the current configs and workflow. Each one says what is missing, what it would look like, and which existing machinery it would build on. Several are cheap because the machinery already exists (V35 combine, the identity, the journal).

---

## F1 — Configuration inheritance

**Today.** `zeus_validation.toml` has seven configurations, `default` and `default01` … `default4`, that differ only in `label` and `event_count`. Each repeats `description`, `sweeps` and `tools`: about 40 lines for 7 facts. `eic.toml` shows the same pattern in its commented-out blocks.

**Expected.**

```toml
[run.defaults]                         # every configuration starts from this
tools = [["pythia", "rivet"], "yd2rt"]
description = "Proton-PDF comparison at 27.5x920 GeV e+p against ZEUS 2012"

[run.pdfs]
sweeps = ["pdf"]

[run.pdfs_100M]
extends     = "pdfs"                   # a configuration may extend another
event_count = 100_000_000
label       = "PDFs_100M"
```

Or, for this exact case, sweep the event count itself (see F1b).

**Builds on.** L1's resolver: `extends` is one more parent layer, at no extra cost.

### F1b — Sweeping built-in run settings

`events` and `threads` are built-in quantities (`quantities.py:26`), but they can't be swept: they come from `event_count`, not from `[quantities]`. A statistics-convergence study (10M, 25M, 50M, …) is exactly a sweep:

```toml
[quantities.events]
values = [10_000_000, 25_000_000, 50_000_000]
tags   = ["010M", "025M", "050M"]
```

The plan already treats `events` as a mapped quantity. What is missing is letting a swept value override `configuration.event_count` per point.

---

## F2 — A shared quantity library per project

**Today.** `[quantities.energies]` (the same values, tags and labels) and `[quantities.lepton]` are declared in both `eic.toml` and `zeus_validation.toml`. A fix to a label must be made twice.

**Expected.**

```toml
[master]
include = ["common.toml"]             # configs/<Project>/common.toml: [quantities.*], [tools.*], [plot.*]
```

Included tables come before the file's own (the file wins, by L1's rule). `configs/PhotoProduction/common.toml` then holds the beams, PDFs, lepton and the standard Pythia/Rivet tool tables.

**Builds on.** `[master].master_toml`, which already overlays `master.toml` per project (`quantities.py:47-65`). This is the same mechanism, extended to the run TOML's own tables.

---

## F3 — "Why does this point rerun?"

**Today.** After any edit, `--plan` says `to run` or `complete`, and nothing more. The `.complete` file holds only the identity hash (`record.py:155-161`), so the runner can't say *what* changed. In the last session, every `eic` point showed "to run" after the TOML was reorganised, and the reason had to be worked out by hand.

**Expected.**

```
point 3 18x275_NNPDF23lo   identity 9f2c41…   to run
  changed: tools.pythia.card  + "PDF:pSet = LHAPDF6:NNPDF23_lo_as_0130_qed"
                              - "PDF:pSet = 13"
           events             25000000 → 10000000
```

**How.** Write the identity's parts (the JSON `record.identity` already builds and hashes) beside `.complete`, as `identity.json`. `--plan --why` diffs the stored parts against the new ones. This costs one file per point and a small JSON diff.

---

## F4 — `hep check`: lint without planning

`--plan` hashes every executable and base card for every point. A config check should:

- load and validate every configuration of a file, including `[plot]` (C11);
- resolve every path, and check every quantity's consumers (C7) and every connection (C6);
- skip hashing binaries and probing versions;
- exit 0 or 2, so it can run in a pre-commit hook or CI over all of `configs/`.

The planning code supports this once hashing is behind a flag (L10).

---

## F5 — Housekeeping commands

| Command | What it does | Why |
|---|---|---|
| `hep status [CONFIG]` | A table of configurations × points: complete, to run or failed, last run time, product sizes | Today this needs `--plan`, which prints argv walls, or reading `points.json` |
| `hep clean [CONFIG] [--dry-run]` | Removes point folders no longer in any plan, stale `.partial` files, and prepare cache entries no plan references | `output/<P>/.cache/` grows for ever, and so do old points after a quantity's tags change |
| `hep ls [Project]` | Every config and its configurations, with descriptions | Discoverability |
| `hep make <path>` | What the usage already promises (C15) | A one-line fix |
| `hep explain <key>` | A key's type, default, inheritance and doc string, from the schema (B1) | Faster than docs/04 |
| `hep new <Project>/<name>` | Scaffolds a run TOML from the tool folders and the master | Onboarding |

---

## F6 — Editor support for the run TOML

The repository already has `aux/` for VS Code tooling. The Even Better TOML (Taplo) extension reads a JSON Schema named in a `#:schema` comment or in its settings, and gives completion, hover docs and inline errors. With the schema file (B1), a generated `utils/Env/schema/run.schema.json` turns most of `config.py`'s refusals into red squiggles before `hep run` is typed.

---

## F7 — Plotting features

| Feature | Today | Expected |
|---|---|---|
| Curve style per quantity value | Colour by curve index (`base.toml` palette); no line styles | `[quantities.pdf].style = [{colour = "kRed"}, {line = "dashed"}, …]`, or `[plot.curves."<tag>"]`, so a PDF keeps its colour across pages and configurations |
| Line styles and markers for MC | None (solid steps only) | `curves.styles = ["solid", "dashed", "dotted"]` in `base.toml` |
| Normalisation | Not available (pending from earlier) | `normalise = "area" \| "first_bin" \| false` per `[plot]` / object |
| Placeholders in titles | Not available (pending) | `title = "{q:energies} — {cell}"` |
| Ratio reference | Data, else the first curve | `ratio_reference = "<tag>"`: divide by a named point |
| 2D objects | Skipped (`objects_of` keeps 1D only), though `App_yd2rt` converts them | A heat-map page, or a page per slice |
| Index page (root backend) | None; mkhtml makes `index.html` for yoda | `plots/root/index.html` or one multi-page PDF per cell |
| Several reference datasets | One `[plot.data]` | `[plot.data.<name>]`, each with a marker |
| Envelopes / bands | None | `band = ["pdf"]`: draw a quantity's points as a min–max band (PDF or scale uncertainty) |

The last row is the usual HEP way to show a PDF or scale variation. The points exist already; the page document only needs a `band` curve kind.

---

## F8 — Adding statistics to a complete point

To go from 25M to 50M events, the configuration must change, which changes the identity, and everything reruns from zero. V35's `combine` already merges seed replicas with `rivet-merge -e`.

**Expected.** `hep run CONFIG --more 25M` adds a replica (a new seed block, disjoint by construction) to each complete point, and its `combine` stage merges them. The merged product's provenance lists the replicas. This is mostly wiring: replicas are a `<tool>/seed` quantity, so the runner can add one implicitly.

---

## F9 — Batch and cluster execution

Execution is local only: `parallelism` runs threads in one process. A point is already self-contained (its folder holds cards, argv and FIFOs, and `.complete` marks success), so a backend that writes one job script per point and submits it to Slurm or HTCondor fits the design. `hep watch` already follows a journal, which a job could append to on a shared filesystem.

**Expected.** `[run] executor = "local" | "slurm"`, with `[executor.slurm]` holding partition and time limits.

---

## F10 — Smaller expected features

| Feature | Note |
|---|---|
| `parallelism = "auto"` | `cores // max(cores per point)`; today the user computes it and `crowded()` only warns |
| Notification on finish | `notify = "desktop"` (notify-send), for multi-hour runs |
| Value types on mappings | `{ key = "Beams:idA", type = "int" }` in `master.toml`, checked at plan time; today a string PDG id reaches the card |
| `hep reproduce provenance.json` | Rebuilds the exact point (`seed_type = "manual"` with the recorded seed), as V39 promises in prose |
| Runner verbosity | `-v` / `-q`; a runner log beside `status.jsonl` |
| Reading results from Python | A documented helper, `runner.results.load(config, cfg)` → points with their YODA/ROOT paths and values, for notebooks. Category 9 (statistics) in the original brief has no support at all |
| Remote inputs | `root://` and `davs://` paths for category 10 (xrootd, rucio): `paths.resolve` refuses anything that isn't local |
