# P1 — One chain, end to end

| Status | Steps | Depends on | Ends with | Updated |
|---|---|---|---|---|
| not started | 3 | P0 | `hep run PhotoProduction/eic single` runs App_Pythia ══FIFO══► rivet, watched, checked and recorded | 2026-09-26 |

## Goal

The smallest real thing, **all of it**: one point, one generator, one analysis, from a v2 run TOML to
a YODA in `results/`. It comes with a watch view, failure handling that cannot hang, and provenance.
Every physics-critical fact is proved here, on the smallest chain that can get it wrong.

Design:

- [02_Architecture.md](../02_Architecture.md) §§1, 3, 5, 8–10;
- [04_Config.md](../04_Config.md) §§3–5, 7;
- [05_Tools.md](../05_Tools.md) §§1–4.

Ledger rows to honour: **L1–L10, L17, L25**.

---

## S1 — `Status.hh` and App_Pythia, proved by hand

**Tasks**

1. **`utils/Status.hh`** (~120 lines):
   - `Status::Reporter`, which reads `$HEP_STATUS_FD` and falls back to plain stderr;
   - the messages `phase`, `progress`, `xsec`, `log` and `summary`;
   - non-blocking, drop-on-full writes;
   - a 500 ms heartbeat thread;
   - the X11 `Status` macro guard.
2. **`utils/App_Pythia.cc`** as specified in [05 §4](../05_Tools.md#4-apppythia-utilsapppythiacc):
   cards in order; the seed-list check (L4); chunked runs (L6); a serialised writer; catching at the
   thread boundary (L3); the σ combination (L1) **stamped on every event** (L2); fan-out; gz/zst by
   suffix (L25); the sidecar (L5); exit codes; SIGINT within a chunk.
   **With no `--seeds`, the cards' own seeds stand**, which is what the reference gate needs.
3. Tests: `tests/cxx/test_status.cc` (the JSON envelope, drop-on-full, the fallback) and
   `tests/cxx/test_app_pythia.cc` (seed refusal, the sidecar schema, the codec by suffix).
4. **The gates, run by hand**: App_Pythia → FIFO → `rivet`, with no runner in between.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `make test` (the C++ tests) | pass |
| 2 | **the reference gate**: `tests/reference/legacy_run/photo_ep.cmnd` + `mini_27x920_ep_MSTW.cmnd` → App_Pythia (threads = 1, seed 12345 from the card) → FIFO → `rivet -a photo_eic` | **bin-for-bin equal** to `mini_27x920_ep_MSTW.yoda` (σ 71,422.16 pb, 5,000 entries). If `photo_eic.cc` has changed since the capture (2026-09-18), rebuild the capture-time version from git for this row, and note it. |
| 3 | the same for `mini_27x920_ep_NNLO` | equal; 4,999 entries (one failed event, L5), and the sidecar says `written = 4999` |
| 4 | **the σ gate** (R1): the eic point at threads = 4, 100k events → rivet | Rivet's `/_XSEC` equals the sidecar's `sigma_pb` to **1e-6 relative**. If it fails, switch to the `rivet -x` fallback, record it as V21, and rerun. |
| 5 | a card that fails `init()` | exit `1` or `3`; no output file; a `log` status explaining why |
| 6 | a FIFO output with no reader, then SIGINT | exits `6` within one chunk |
| 7 | eic single point, 50k events, threads = 20 → rivet: events/s against the P0 baseline | a ratio in the Log (R4) |

---

## S2 — The runner core, for one point

**Tasks**

1. **`config.py`**: load the run TOML with `tomllib`, then run a strict schema check (unknown keys
   get did-you-mean; types; every error has a `where` and a `hint`). This step needs `[run]`,
   `[run.<cfg>]` (`tools`, `event_count`, `threads`; `sweeps = []` only), `[prelim]`,
   `[tools.<tag>]`, and `[master]` with no quantities yet.
2. **`tools.py`**:
   - discover `utils/Env/*/tool.toml` and validate them;
   - check the tool-specific keys against each folder's `[options]`;
   - render point cards (`append` style for Pythia; argv only for rivet);
   - build argv from placeholders.

   Write the tool folders `pythia/`, `rivet/` (with `filters.toml`, patterns from v1's
   `run/parsers.py`) and `custom/`.
3. **`execute.py`**:
   - `[prelim]` (`mkfifo`, touch, `commands`);
   - each group as **one process group**;
   - the first nonzero exit kills the group after a grace period;
   - stall detection on output, status and heartbeat;
   - attribution: the first process to exit nonzero before any signal was sent is the cause;
   - the SIGINT → SIGTERM → SIGKILL ladder;
   - **the count check**: Rivet's `/RAW/_EVTCOUNT` against the sidecar's `written` (L7);
   - `*.partial.*` on a mismatch.
4. **`status.py`**: one pipe per process on `$HEP_STATUS_FD`; the filter rules; everything appended
   to `status.jsonl`; stdout and stderr to `logs/<tag>.log`.
5. **`record.py`**: the per-point identity (02 §7); `provenance.json` (V14); `.complete` written
   last.
6. **`hep run <config> [<cfg>]`** and **`--plan`**, which prints the groups, the resolved argv and
   paths, and the connection kinds.
7. **The connection rules** (C6) and the path rules (C12), with a test for each refusal.
8. **Standard configurations for custom tools** (V21, [04 §7.3](../04_Config.md#73-standard-configurations-for-custom-tools)):
   - `<tool>_<export> = true` in a `custom` table;
   - the referenced table is rendered even when it is not in the chain;
   - `[standard.<key>]` goes into the extracted config, and `{std:<key>}` works in `arguments`;
   - rule C13.

   Exports in this step: the automatic `<tool>_card` for every tool with a card, the alias
   `pythia_cmnd` (`[exports.cmnd] alias = "card"` in `pythia/tool.toml`), and `rivet_analyses`.
9. Write `configs/PhotoProduction/eic.toml` in v2 form with its `single` configuration only
   (**approval**: `configs/`). The v1 file stays in git.

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `hep run PhotoProduction/eic single --plan` | 2 groups, 3 tools, the FIFO connection, and paths under `output/PhotoProduction/03_eic/single/point/` and `results/…` |
| 2 | `hep run PhotoProduction/eic single` (100k events, threads = 1), then App_Pythia → rivet **by hand** with the cards the runner rendered (`output/…/cards/`) | `photo.yoda` **bit-identical** both ways: the runner adds nothing to the physics |
| 3 | kill App_Pythia mid-stream | the group is killed; `photo.partial.yoda`; no `.complete`; exit `1`; wall time ≤ `stall_after` + grace |
| 4 | a card that fails `init()`, with rivet blocked at open | no hang, bounded as above; attributed to pythia |
| 5 | kill rivet | pythia gets SIGPIPE; attributed to rivet |
| 6 | a FIFO into a fake `streamable = false` tool; a FIFO between two groups; two readers on one FIFO | three plan-time errors, each with a hint |
| 7 | config tests: one bad file per rule C1, C2, C5, C6, C12, C13 | each fails with `where` and `hint` |
| 8 | a `custom` test tool with `pythia_cmnd = true` beside the normal `[["pythia", "rivet"]]` chain for the same point | its `[standard.pythia_cmnd].path` is **byte-identical** to the card App_Pythia received, seeds included; `parts` lists the base and point cards in reading order |
| 9 | the same custom tool in a configuration where `pythia` is **not** in `tools` | the card is still rendered; quantities consumed by pythia pass C7; App_Pythia is not spawned |
| 10 | `pythia_cmnd = true` with two `tool = "pythia"` tables | C13 error with the hint to use `pythia_cmnd = "<tag>"` |

---

## S3 — The watch view

**Tasks**

1. **`watch.py`**:
   - one line per running tool: point, tool, progress, rate, ETA, last warning;
   - one line per finished point;
   - `rich` when on a TTY, plain lines otherwise;
   - fed only by status messages, so it knows nothing about processes.
2. **`hep watch [<config>]`** tails `status.jsonl` from another terminal.
3. `utils/Env/runner/status_client.py`, for Python custom tools (~30 lines).

**Verification**

| # | Row | Expect |
|---|---|---|
| 1 | `hep run PhotoProduction/eic single` on a TTY | live progress for both tools; the displayed rate is within 10% of `written / wall time` |
| 2 | `hep watch PhotoProduction/eic` from a second shell | the same point, live |
| 3 | `hep run … > log.txt` | plain lines, with no control codes |
| 4 | a `custom` tool that only prints | a spinner and its last line; the run is unaffected |

**Done when** every row of S1–S3 passes. `hep run PhotoProduction/eic single` is then the
user's working tool again (R3 closes).

---

## Rollback

Revert the step commits. The work is additive on the P0 skeleton.

## Log

*(filled during execution)*
