# Target: Ubuntu (apt, sudo)

The primary target: the lab PC after its reinstall, and any Linux PC with apt and sudo. Only what
differs from the phase files is here (D11).

## Prerequisites (P0 S1)

- `git`, `curl`, `python3` ≥ 3.11 with `venv` (`python3-venv`).
- `sudo`. A password is fine: the gates ask before every `sudo`.
- 60 GB free where `$HEP` goes.

## System packages (P2 S1)

`settings.toml`'s `apt_packages`: 51 at 9cb907a, grouped there by what needs each one. That
includes `pandoc`, `poppler-utils` and `texlive-latex-recommended` for decks (V102–V104). They are
installed once, at P2 S1's gate, and the build then runs with `system=false`.

## Overlay and launching

- **Overlay:** none. `packages.toml` and `settings.toml` are the lab PC's.
- **Launching:** `source ~/Github/Heimdall/setup.sh`, or the alias `load_hep` (09 S2 asks to add it).

## Allowed adjustments (02 §7)

These may be made without a gate, then recorded, reported and folded back:

1. **A `-dev` package with no candidate whose only user builds its own copy when it is missing.**
   Drop it from `apt.txt`, then confirm in that package's log that it used its own copy. The known
   case is `libpcre3-dev`, which Debian has been removing: ROOT then builds its bundled PCRE, so
   `grep -i pcre $HEP/logs/root.log` must show the builtin being switched on. If the log does not
   show it, this is not allowed: it is a gate.
2. **`python3-venv` with no candidate** while a versioned `python3.X-venv` matches `python3
   --version`: take that one.
3. **A package renamed by Ubuntu, with the same source package.** Check with `apt-cache showsrc
   <new>` against the old name's source, and record both names.

Everything else is a gate. That includes:
- a different release of any HEP package (it changes P2 S3's expected versions);
- a compiler flag;
- a patch.

## Known limits

- **Ubuntu 24.04** is the lab PC's system before the reinstall. Every row in the phase files was
  measured there, and no adjustment is expected.
- **A newer Ubuntu** (26.04) brings a newer GCC, glibc and Python. The suspects, in the order they
  build:
  - ROOT 6.40.04, against the new Python (PyROOT) and GCC;
  - ThePEG and Herwig (C++ headers that newer GCCs stopped including transitively);
  - Whizard (its OCaml);
  - Sherpa.

  A failure there is a gate. The way out is usually a newer release (`<package>.release=…` on the
  command line), which the user must approve because P2 S3's versions move.
- **P4 S2's R2** (byte-identical against the legacy reference) may fail on a new compiler, as 07
  explains. That is a decision for the user, not a fault.
