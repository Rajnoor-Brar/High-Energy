# Current plan

**The order of work is [docs/audit_1/06_Plan.md](../docs/audit_1/06_Plan.md)** (P0–P5): its Progress table
is the state. Finished plans and task logs are in [archive.md](archive.md); decisions in docs/07_Record.md.

## Now

- **audit 1, P0** (ordered 2026-10-03): S1 (V52), S2 (V53), S3 (V54) done, fast suite green. Held
  until the user's run ends: the slow suite, and S3's C++/Rivet items (K3, K4, K7, K8, K10's define,
  yd2rt's dead parameter). A rebuilt App_Pythia, App_yd2rt, InprocJets or Rivet plugin changes the
  identity of every point that ran it: ask before.
- `configs/PhotoProduction/` stays untouched until the last steps of the last phase (user, 2026-10-03).

## Standing constraints

- Commits are local, never pushed; messages end with the Co-Authored-By line.
- Tests never read or write the user's `configs/` and `results/` (V52: `tests/fixtures/configs/`).
- One pytest session at a time; the slow suite not while the user's long runs share the cores.
- `~/HEP` changes and downloads need the user's approval; the venv is the user's.
- Never implement without an explicit order; plans first, questions when a request is ambiguous.

## Audit of `utils/` — **DONE 2026-10-03** (asked by the user 2026-10-03, /tech-debt)

- docs/audit_1/: README (summary, top ten), 01 conflicts (C1–C17), 02 missing features (F1–F10),
  03 lean code (L1–L14; L14 = clean appended cards, Pythia cards parsed and merged, added 2026-10-03 at the user's suggestion), 04 bold proposals (B1–B9), 05 backlog (45 items scored, phases 0–5).
- No code changed. Nothing is ordered yet: every item waits for the user's choice.
- Extended the same day: 07_Consistency.md (K1–K15, the whole framework) and **06_Plan.md** (P0–P5, 2–3 steps each; the user's decisions: "default" = keep it as it is, runtime state off disk unless flagged, B3/B5 committed, B4c/B8 to discuss, a positional beam convention, break-and-migrate configs). Progress is tracked in 06's table.

