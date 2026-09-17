# 07 — Outputs, provenance, plotting

## 1. Results layout

```
results/<project>/
  points/<group>/                      one generation (event group, 03 §4)
    run.toml                           resolved spec (input to hep-run)
    point.cmnd | point.yaml | …        rendered native card(s)
    analysis.yoda                      all Rivet analysis variants + module objects of this group (YODA only, D14)
    analysis.partial.yoda              instead of the above when the run was stopped (never both)
    analysis.dump.yoda                 optional periodic dump (re-entrant analyses only)
    events/                            optional HepMC3 store: events.<k>.hepmc.gz + events.index.json (11)
    delphes.root                       optional (external Delphes stage; Delphes' own format)
    run.summary.json                   hep-run's run section (σ, counts, seeds, warnings)
    provenance.json
    status.jsonl
    logs/  prepare.log  generate.log  delphes.log
  studies/<study>/                     one per study (or ad-hoc selection)
    manifest.json                      points, pages, CLI, timestamps, optional run.label
    plots/<page>/                      index.html | *.pdf | *.png
    compare.md                         optional χ² table (§5)
    proc/                              hep proc outputs: fits.json, proc.yoda, optional proc.root, proc.log (12)
  legacy/                              pre-rework results, moved here unchanged (decision Q4, P3-S01)
  .cache/<tool>/<prep-hash>/           integration grids, .run files, MG process dirs
```

**Changes from today:**
| Today | New |
|---|---|
| The flat `results/<P>/<serial>_<name>_<tags>.yoda` and `cmnd/` directory | One directory per generation. Point card, logs, provenance and outputs sit together. |
| The numeric `serial` prefix, which drifted across studies | Study directories. Points are shared by any study that reaches the same physics (name + hash, 03 §5). Decision Q3 (P3-S01): no serial in paths; an optional free-text `run.label` goes into manifests. |
| A killed run leaves a YODA at the final path (00/B3) | Outputs are written under temporary names and renamed; stopped runs produce only `analysis.partial.yoda`. |
| — | An analysis-option variant is **not** a separate generation. It lives inside the group's YODA under Rivet's canonical path (`/photo_eic:R=0.4/d01-x01-y01`). Plotting selects it. |

## 2. Provenance

`provenance.json` (written by hep; `hep-run` fills in the run part):

```json
{
  "schema": 2,
  "point": "eic_5x41_em_NNLO", "hash": "sha256:4c1e…",
  "origin": {"config": "configs/PhotoProduction/eic.toml", "study": "pdf", "cli": "hep run … --study pdf"},
  "created": "2026-09-17T12:40:03+05:30", "host": "Lab_PC", "user": "rajnoor",
  "git": {"sha": "0a10209", "dirty": true, "diff_sha256": "…"},
  "tools": {"hekit": "0.1.0", "pythia": "8.317", "rivet": "4.1.3", "yoda": "2.1.3", "hepmc3": "3.3.1", "lhapdf": "6.5.6"},
  "cards": [{"path": "configs/PhotoProduction/photo_ep.cmnd", "sha256": "…"}, {"path": "point.cmnd", "sha256": "…"}],
  "resources": {"pdf_sets": ["NNPDF23_lo_as_0130_qed"], "analyses": {"photo_eic": {"so_sha256": "…"}},
                "modules": {"mymodule": {"so_sha256": "…"}}, "store": {"index_sha256": "…", "hash": "sha256:…"}},
  "run": {"events_requested": 1000000, "events": 1000000, "threads": 20,
          "seeds": {"policy": "identity", "point": 83920417, "instances": ["…"]},
          "mode": "sharded", "stopped": false, "wall_s": 847.1,
          "xsec_pb": 18290.0, "xsec_err_pb": 55.0, "warnings": {"pythia": 2, "rivet": 1}},
  "outputs": [{"path": "analysis.yoda", "sha256": "…", "bytes": 912345}],
  "exit": 0
}
```

**Embedded copies**, so a file that leaves the directory still identifies itself:
- **YODA:** hep adds annotations `HekitPoint`, `HekitHash` and `HekitGit` to the `/_EVTCOUNT` object after the run (Python `yoda`).
- **Store:** `events.index.json` carries the point hash and a pointer to `provenance.json` (11 §2).
- **ROOT:** only processing outputs (`proc.root`) get a `TNamed("hekit_provenance", json)` key. `delphes.root` gets a sidecar `delphes.provenance.json`.

`hep show <point>` renders this file (06 §5).

**Partial outputs:** a stopped run writes `analysis.partial.yoda`, never `analysis.yoda`, and sets `"stopped": true` with the events actually processed. The skip rule treats it as incomplete (it reruns), and plots mark such curves with `(partial)` in the legend.

## 3. Merging

| Case | Tool | Rule |
|---|---|---|
| Seed replicas of one point | **`rivet-merge -e`** (re-runs finalize) | Correct for normalised and ratio objects. **Requires a re-entrant analysis.** `photo_eic`'s `finalize()` already uses only booked objects; P4-S05 validates this and sets `Reentrant: true`. |
| Module objects in the same YODA | `hekit` merge | `rivet-merge` does not know user modules. `hekit` adds the raw module objects and re-applies the module's `finalize` scaling (05 §5, P8-S01). |
| Same, non-re-entrant analysis | `yodamerge` | Allowed only for plain counts/σ-scaled histograms. `hep` warns. |
| Different physics | — | Never merged; overlaid (the current rule). |

## 4. Plotting (`hep plot`)

This replaces `ydplt` and `ydmrg`.

```
select points (study / pins) → load YODA → pick analysis variant(s) → unify analysis names
  → void empty / min_entries → align reference data → auto-range → backend → index
```

The pipeline stages are the current `rivpyth_common` functions, reorganised into `hekit.plot.{io,select,transform,data,backends}`. Their behaviour is already validated.

### Backends

| Backend | Good for | Label and style source |
|---|---|---|
| `mkhtml` (default) | Browsing many histograms, ratio panels, Rivet reference data | Rivet `.plot` files + generated overrides (auto range, voiding) |
| `mpl` | Publication figures, custom layouts, Rivet + module + `hep proc` curves on one page | The **same `.plot` keys** (Title, XLabel, YLabel, LogY, XMin/XMax, RatioPlot*), parsed into mplhep calls, plus `[plot.style]` (mplhep style, figure size, fonts) |

Parsing `.plot` files for the `mpl` backend keeps **one** label source per analysis.

### Fits and derived histograms

These replace Paint's TOML booking.
- **Module histograms** are already in `analysis.yoda` and plot like Rivet objects.
- **Fits** (`[[proc.fit]]`) and **Delphes-derived histograms** (`[[proc.hist]]`) come from `hep proc` ([12](12_Processing.md)) as YODA under `/PROC/…`.
- With `[plot].show_fits = true`, `hep plot` overlays the fitted curve on its target.

**Data overlays** use an explicit map (`[plot.data].map`), or identical paths. Name-only matching is gone (00/B5).

## 5. Comparison (`hep compare`)

- Per histogram:
  - χ²/ndf against the reference curve (data or the chosen MC);
  - the number of bins used after voiding;
  - the max pull.
- Output: a **rich table** in the terminal and `compare.md` in the study directory.
- Useful for scanning PDF or tune studies without opening PDFs.
- Data and MC with different binning are compared only on aligned bins (the existing `align_to_edges` rule).

## 6. Retention

**`hep clean`:**
| Option | Removes |
|---|---|
| `--cache` | prepare caches |
| `--events` | HepMC stores older than N days (`events/` directories; the index and provenance are kept as a tombstone) |
| `--plots` | study plots (regenerable) |
| `--orphans` | point directories without provenance |

**Never touched automatically:** YODA files, `fits.json` and provenance.

A size report (`hep clean --dry-run`) lists the largest directories.
