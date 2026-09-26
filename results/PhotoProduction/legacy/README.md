# Legacy results — frozen, not reproducible

These are the outputs of the pre-rework pipeline (`rivpyth` → `generator.exe` → HepMC3 FIFO → `rivet`,
then `ydmrg`/`ydplt`), moved here unchanged on **2026-09-18** by rework step
[P3-S01](../../../docs/rework/steps/P3-S01_decide-serial-and-legacy-results.md), decision **D-Q4**.

Nothing was converted, renamed or recomputed. Every file is exactly as the old tools wrote it: the 25
YODA files were checksummed against the inventory taken in P0-S06
(`legacy/results/PhotoProduction.inventory.json`) after the move, and all 25 matched.

```
25 YODA files · 7 plot directories · 541 files · 16.0 MB
serial 01 → configs/PhotoProduction/eic28.toml (partly unknown)
serial 02, 03, 04 → configs/PhotoProduction/eic.toml
```

## Why they are frozen rather than imported

The new layout keys every result by a point name **and** a hash of the inputs that produced it (03 §5,
07 §1), so that a result can always be traced back to, and rebuilt from, its configuration. These files
cannot be given such a hash honestly:

- **The analysis name drifted.** The files carry three different names for what became one analysis —
  `photo_5x41` (9 files), `photo_eic` (15) and `photo_10x100` (1) — so their YODA paths do not match
  anything the current plugin produces.
- **The event counts are accidental.** 977 047 … 999 914 events, because the old generator counted
  `next()` *attempts* and some attempts fail (finding 00/B21). Asking the new pipeline for 1 000 000
  events cannot reproduce these numbers.
- **The inputs are partly unknown.** Serial 01 has no recorded configuration, and the point `.cmnd`
  files in `cmnd/` were reconstructed rather than archived with the run.
- **Some plot pages reference temporary files.** 5 of the 7 `index.html` pages mention `.tmp` paths, a
  trace of the old non-atomic writer (00/B3). The plots render, but their inputs were not what the
  final names say.

Giving these files new-looking point directories and provenance would make them *look* rebuildable
while none of the above is true. Freezing them keeps them readable and honest.

## Using them anyway

They are still perfectly good curves to look at and to overlay:

- `hep plot … --extra <path>` (`[plot].extra`, P4-S02) overlays a YODA from here by path, alongside new
  results;
- `yoda-config`/`rivet-mkhtml` and `python tests/tools/yodacmp.py` read them directly;
- the `by_*` directories hold the `index.html` pages the old `ydmrg`/`ydplt` produced.

What they must not be used for: merging with new results (`rivet-merge` would mix incompatible analysis
paths and unknown normalisations), or as a reference in a comparison that claims a shared configuration.

## Layout

```
legacy/
  NN_<config>_<beams>_<lepton>_<pdf>[_tags].yoda   one point, as the old pipeline named it
  NN_<config>…_by_<quantity>/                      ydmrg/ydplt plot pages (index.html, *.pdf)
  cmnd/                                            reconstructed point cards
```

The `NN_` prefix is the old serial. The rework keeps a serial (decision **D-Q3**) but moves it to the
*study* directory, where it labels one run rather than the identity of a result.
