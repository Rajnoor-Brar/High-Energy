# Current plan — P1-S06 config-migrate (done) → next P1-S07

> Source: `docs/rework/steps/P1-S06_config-migrate.md`. Index: `docs/rework/steps/README.md`.
> Status: **done** (2026-09-18).

## What P1-S06 delivered

`hep config migrate|validate|reference|init`; `configs/PhotoProduction/{eic,zeus_validation}.v2.toml`
committed next to the originals (00/B12 tag renames with the old names recorded, 00/B14 undeclared
option quantities dropped, 00/B5 explicit empty data map); `docs/rework/reference/config.md` generated
from the schema.

## Next: P1-S07 doctor-pdf (last step of P1)

`hep doctor [--json/--brief]` (versions cached, imports, ThePEG modules, HepMC compression,
`hep-run --capabilities`, env sanity) and `hep pdf check/list/install`; `hep_status` becomes an alias.
