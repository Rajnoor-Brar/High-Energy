# 06 — Terminal presentation, supervision, status protocol

**Guideline 2:** terminal presentability while going over events in Pythia, Rivet, etc.

The design separates four concerns:

| Concern | Owner |
|---|---|
| Producing facts (progress, σ, warnings) | each stage: `hep-run` natively; external tools via parsers |
| Supervising processes (spawn, timeouts, signals, exit codes) | `hekit.run.supervisor` |
| Rendering (live dashboard or plain lines) | `hekit.term` — the **only** renderer |
| Keeping everything | `logs/<stage>.log` (raw) + `status.jsonl` (structured) |

**Why the rendering left C++:**
- Today's `Monitor` draws ANSI for one process only.
- A multi-stage run (Sherpa → hep-run → Delphes) needs one view across processes. Only the parent can provide that.
- C++ keeps only the facts.

---

## 1. Live dashboard (TTY)

```
 hep run eic.toml --study pdf                                PhotoProduction · sidequest@0a10209+dirty
 ─────────────────────────────────────────────────────────────────────────────────────────────────────
  points ██████████░░░░░░░░░░ 2/4      elapsed 18:42      eta ≈ 37 min
 ─────────────────────────────────────────────────────────────────────────────────────────────────────
  ✔ 1  eic_5x41_em_MSTW    1.00 M ev   σ = 1.832e+04 pb ± 0.3 %   9m12s   0 warnings
  ▶ 2  eic_5x41_em_NNLO
       generate+rivet  ██████████████░░░░░░░░  642 113 / 1 000 000  64 %  1.18 k ev/s  eta 5m03s
       20 workers · sharded · σ(running) 1.79e+04 pb · warnings 3 (Pythia 2 · Rivet 1)
  · 3  eic_5x41_em_NNNLO   queued
  · 4  eic_5x41_em_LHC21   queued
 ─ 2/generate.log (curated) ──────────────────────────────────────────────────────────────────────────
  12:41:07  Pythia  W  SpaceShower::pT2nearThreshold: stuck in loop            ×2
  12:43:51  Rivet   W  photo_eic: jet outside |η| acceptance after boost       ×1
 ─────────────────────────────────────────────────────────────────────────────────────────────────────
  Ctrl-C: stop at next checkpoint (partial YODA kept) · Ctrl-C ×2: abort
```

**Layout rules:**
- **Header:** command, project, git state.
- **Point list:** ✔ done, ▶ running (with its stage bars), · queued, ✖ failed (with an exit-code reason), ↷ skipped (`skip_existing`, hash matched).
- **Stages:** one bar per running stage. Prepare stages (integration, `Herwig read`) show a spinner with elapsed time when the tool gives no count.
- **Curated log pane:**
  - warnings and errors only, de-duplicated with counts;
  - `[terminal] log_tail` lines;
  - the full log path is always shown.
- **Footer:** the key hints.

**Rendering technology:** **`rich`** (`Live`, `Progress`, `Table`, `Tree`), added to the venv. It is pure Python and handles SIGWINCH, cursor restore and colour detection.
- **Rejected: a hand-rolled ANSI renderer.** That is what `Monitor/Render.hh` is: fragile cursor arithmetic, no resize handling, one process only.
- **Rejected: textual (full TUI).** Too much for a progress view. It also takes over the terminal, which breaks scrollback and remote viewing.

The dashboard renders **inline**: no alternate screen, so the final summary stays in scrollback.

## 2. Plain mode (non-TTY, `--plain`, CI, remote logs)

One line per event of interest, rate-limited to one progress line per `plain_every` (default 30 s) per stage:

```
12:40:03 [2/4 eic_5x41_em_NNLO] generate  start  hep-run (20 threads, sharded)
12:40:33 [2/4 eic_5x41_em_NNLO] generate  35211/1000000  3.5%  1.17k/s  eta 13m44s
12:41:07 [2/4 eic_5x41_em_NNLO] WARN pythia SpaceShower::pT2nearThreshold: stuck in loop
12:54:10 [2/4 eic_5x41_em_NNLO] done      σ=1.829e+04 pb ±0.3%  14m07s  → results/…/analysis.yoda
```

`auto` chooses live on a TTY and plain otherwise.

## 3. Status protocol (child → hep)

### 3.1 Channel

- `hep-run` writes **JSON lines to fd 3** (passed with `pass_fds`).
- Without fd 3 (standalone use), it prints plain progress to stderr instead.
- stdout/stderr stay free for tool chatter, which goes to the log file.

### 3.2 Messages

```json
{"t":1758103203.1,"k":"phase","phase":"init","detail":"reading 2 cards"}
{"t":…,"k":"init","sqrt_s":28.64,"beam_ids":[2212,11],"beam_energies":[41,5],"threads":20,"mode":"sharded","analyzers":["rivet","hepmc"]}
{"t":…,"k":"progress","done":642113,"total":1000000,"rate":1180.4,"workers":[32110,31987,…]}
{"t":…,"k":"xsec","value_pb":17900.0,"err_pb":95.0,"final":false}
{"t":…,"k":"log","level":"warn","source":"pythia","msg":"SpaceShower::pT2nearThreshold: stuck in loop"}
{"t":…,"k":"checkpoint","done":600000,"outputs":["analysis.yoda.part"]}
{"t":…,"k":"event","index":0,"particles":[…]}                  # only with --list (§5)
{"t":…,"k":"summary","events":1000000,"xsec_pb":18290,"err_pb":55,"stopped":false,"seeds":[…],"outputs":{"yoda":"analysis.yoda","store":"events/","shards":20}}
{"t":…,"k":"heartbeat"}
```

- The `k` field is a closed enum.
- Unknown `k` values are logged and ignored, so the protocol can grow.
- The C++ `Status::Writer` (namespace `Status`, 13) is ~150 lines. It holds a rate limiter and an atomic counter read by a heartbeat thread, so the event loop never formats JSON.

**Pythia warnings.** Pythia's `Logger` aggregates messages and prints them in `stat()`. `Source::Pythia` reads `logger` counts at checkpoints and at the end, and emits them as `log` messages. Live per-message streaming is not needed.

**Rivet warnings.** Rivet logs go to stderr → the log file. The supervisor's Rivet parser surfaces `WARN`/`ERROR` lines.

### 3.3 Exit codes (all stages run by hep)

| Code | Meaning | Dashboard |
|---|---|---|
| 0 | success | ✔ |
| 1 | spec or card error (`readFile` false, bad key) | ✖ "config" + log excerpt |
| 2 | usage | ✖ |
| 3 | generator init failed | ✖ "init" (e.g. vanishing σ) |
| 4 | source I/O (FIFO closed early, parse error) | ✖ "input" + the upstream stage's status |
| 5 | analyzer error (Rivet finalize, write failed) | ✖ "output" |
| 6 | stopped by signal, partial outputs finalised | ◐ "partial" |
| 7 | stalled or timed out (set by the supervisor) | ✖ "stall" |
| 70 | internal error | ✖ "bug" + a hint to report |

External tools only report 0 vs non-zero. The adapter maps known log patterns to codes 1, 3 or 4.

## 4. Supervision

- **Pipelines:** stages of one point that share a FIFO start together.
  - The supervisor polls all of them. This generalises today's `supervise()` fix.
  - Any non-zero exit → SIGINT the siblings → grace period → SIGTERM → SIGKILL.
- **FIFOs** live in a per-run temporary directory, which is removed on exit (the current design).
- **Stall detection** (moved from C++ `Monitor`):
  - no status message and no log growth for `stall_after` → yellow "stalled 5m";
  - after `stall_kill` (default off) → stop with exit code 7.
- **Signals:**
  - first Ctrl-C → SIGINT to the children: hep-run stops at the next chunk and finalises;
  - second Ctrl-C → SIGTERM;
  - third → SIGKILL;
  - the terminal is always restored (the `rich` context plus `atexit`).
- **External-tool progress parsers.** Regex tables live in the adapter; calibrate them against real logs during implementation.

| Tool | Progress source | Surfaced |
|---|---|---|
| Sherpa | `Event <n> ( … )` lines | events, rate; σ from the final table |
| Whizard | the event-generation progress lines | events; integration iterations in prepare |
| Herwig | `event> <n>` progress | events |
| MadGraph | stage lines (`Survey`, `Refine`, `Combining`) | stage names; spinner |
| DelphesHepMC3 | its progress output | events |
| hep-run | status fd | everything |

  Without a parser: a spinner + elapsed time + the last log line.
- **Tool noise control:** `[terminal] quiet = [regex…]` and `surface = [regex…]` extend the per-tool defaults.

## 5. Going over events

This is the "presentability when going over events" part.

**`hep events <config|point|store> [-n 3] [--from FILE]`:**
- runs `hep-run --list 3` (Pythia, 3 events, analyzers off); or reads a store ([11](11_EventStore.md), first shard) or any HepMC3 file (`.hepmc`, `.hepmc.gz`) with `pyHepMC3`;
- renders each event as a **rich table**:
  - index, name (from `ParticleData`/PDG), status (colour-coded: beam / hard / shower / final);
  - mothers → daughters, pT, η, φ, m;
- `--tree` shows the decay tree;
- `--final` shows final-state particles only;
- `--hard` shows the hard process only.

This replaces Pythia's fixed-width `event.list()` for inspection. `event.list()` stays available in the log with `Next:numberShowEvent`.

**`hep show <point>`** is the post-run report:
- changed Pythia settings (parsed from `Init:showChangedSettings` in the log);
- the σ table (parsed from `stat()`);
- warnings summary;
- Rivet analyses and options;
- event count and outputs with sizes;
- provenance (git, versions, hashes).

**`hep analyses <pattern>`** is a pretty `rivet --list-analyses` with `.info` summaries, options and reference-data availability.

## 6. Remote and background runs

- The supervisor also appends every message to `results/…/<run>/status.jsonl`, and writes `run.pid`.
- **`hep watch [run|latest]`** tails `status.jsonl` and renders the **same dashboard**, read-only.
  - It works from a second terminal, over SSH, or from a remote Claude session. No shared TTY is needed.
- **`hep runs`** lists active runs (the pid is alive) and recent ones (with summary).
- **`hep run --detach`** starts under `setsid` with plain output to `run.log`. Use `hep watch` to view it.
- **Optional `[terminal] notify = true`:** `notify-send` (Linux) or `osascript` (Mac) when the run ends.
