# Current plan — P0-S06 legacy-archive

> Mirror of the step being executed (per bots/BOT.md). Source: `docs/rework/steps/P0-S06_legacy-archive.md`.
> Step index: `docs/rework/steps/README.md`. Status: **in-progress** (2026-09-18).
> Approved by the user for P0: tags, `~/HEP` edits, local per-step commits (no push), `bots/` layout edits.

## Goal

Everything the new stack replaces lives in a tracked `legacy/` with history, a README and a porting guide;
nothing outside `legacy/` includes it; PhotoProduction still builds (D17).

## Moves (`git mv`, history preserved)

| From | To |
|---|---|
| `modules/Lambda{,.hh}`, `sources/Lambda`, `configs/lambda` | `legacy/lambda/` |
| `tests/*` except `tests/golden` | `legacy/tests/` |
| `utils/{Config,Monitor,Paint,Physics,Probe,Record,Utility}{,.hh}` | `legacy/utils/` |
| `_Paint.cc`, `_ThreadBench.cc`, `root_macros/` | `legacy/misc/` |
| `configs/{defaults,templates,all.toml,Paint.toml}` | `legacy/configs/` |
| `sources/PhotoProduction/photo_{5x41,10x100,18x275}.*` | `legacy/analyses/` |
| `configs/photo_zeus/README_ZEUS.txt` (00/B28) | `legacy/configs/photo_zeus/` |
| `docs/{MAP,Architecture,DataContract,UtilsAudit,UtilsDependencyMap,Audit}.md`, `docs/archive/`, `docs/plans/` | `legacy/docs/` |
| `tests/golden/results_inventory.json` | `legacy/results/PhotoProduction.inventory.json` (capture script updated) |

## Also

- `legacy/README.md`: what, why, the tags to build from (`legacy/lambda-final`, `rework/baseline`), the Lambda physics
  summary and its bugs, the old utils defects, port notes.
- `legacy/PORTING.md`: snippet → target step table (00b §4).
- `docs/README.md`: pointer (docs/ then holds only `rework/`).
- Fix any path in `docs/rework` that points at a moved doc.
- `bots/` layout and testing sections updated for `legacy/`, `tools/`, `env/`, `tests/golden` (approved);
  `bots/CLAUDE.md` is stale Lambda-era content and moves to `legacy/docs/`.

## Verification

| Check | Expected |
|---|---|
| `git grep -nE '#include "(Config\|Monitor\|Probe\|Record\|Paint\|Physics\|Utility\|Lambda)' -- ':!legacy'` | empty |
| `make PhotoProduction/generator.exe PhotoProduction/photo_eic.so` | builds |
| `git log --follow legacy/utils/Utility/Sha256.hh` | shows old commits |
| `pytest tests/golden` | passes (mini run still valid) |

## Next

P0-S07 `makefile-hygiene` (last P0 step).
