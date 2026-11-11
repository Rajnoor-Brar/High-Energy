# High-Energy

A Heimdall work dir (made by `heimdall setup` on 2026-10-22). Heimdall, the framework and its stack, is
elsewhere: `heimdall where` says which one this shell uses. Its manual is `$HEIMDALL/docs/README.md`.
`gjallarhorn High-Energy` loads Heimdall's environment and comes here, from anywhere (`heimdall recognise
--list` shows the titles this machine knows); `bifrost <pkg>` adds a package to the environment.

| Folder | Holds | In git |
|---|---|---|
| `configs/<Project>/` | run TOMLs and their cards (`.cmnd`, `.in`, `.yaml`, …) | yes |
| `modules/<Project>/` | your programs (`X.cc` → `build/<Project>/X.exe`) and Rivet analyses (`Rivet/<x>.cc`) | yes |
| `datasets/` | input files a run reads (`data = "…"`): small ones tracked; large ones listed in `datasets.toml` (url, sha256), which `heimdall setup .` fetches | yes |
| `decks/<deck>/` | your decks (`deck.md`, `deck.toml`), built into `reports/<deck>/` by `heimdall deck <deck>` | yes |
| `results/<P>/<run>/<cfg>/` | what runs produce: `points/<point>/` the products, `plots/` the pages | no |
| `records/<P>/<run>/<cfg>/` | what runs recorded: `points/<point>/` each point's provenance, identity and completion (keep it with `results/`); `logs/<point>/` its cards, configs and a failed tool's last lines (safe to delete: `heimdall clean`); `plots/` the page configs; `config/` the run TOML and cards it ran with (`heimdall plot <P>/<run>/<cfg>` draws from it) | no |
| `.cache/` | prepare caches (and card checks, converted data with `keep cache`): rebuilt when needed | no |
| `reports/` | the decks' slides, as `heimdall deck` builds them | no |
| `build/` | compiled modules and Rivet plugins (`heimdall build`) | no |

```bash
heimdall ls                          # every config and its configurations
heimdall build                       # compile modules/
heimdall run <Project>/<config>      # plan and run (add --plan to look first)
```

Git keeps no empty folders: after a fresh clone, `heimdall setup .` makes the missing ones again, and
fetches the files `datasets.toml` lists. `heimdall setup . --refresh` brings this file, `CLAUDE.md` and the
`Makefile` up to date with Heimdall's template.
