#!/usr/bin/env bash
# docs/stack/mac/build.sh — build the HEP stack on macOS: Homebrew's packages (Brewfile), then
# build_stack.py with mac.toml. Run it after README.md's manual steps (Xcode's tools, Homebrew).
#
#   bash docs/stack/mac/build.sh                       # the core stack into ~/HEP (hours: ROOT is 1–2 h)
#   bash docs/stack/mac/build.sh packages=all cores=8  # every build_stack.py argument passes through
#   bash docs/stack/mac/build.sh --dry-run             # the commands as bash; nothing installed or built
#   BREW_BUNDLE=0 bash docs/stack/mac/build.sh         # skip `brew bundle` (the Brewfile is installed)
#
# Rerunning resumes: finished packages are stamped and skipped (docs/stack/README.md).

set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

say() { printf '\033[1m==> %s\033[0m\n' "$*" >&2; }
die() { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || die "this is the macOS build; on Linux run docs/stack/build_stack.py"
xcode-select -p >/dev/null 2>&1 || die "no Xcode command-line tools: run 'xcode-select --install' (README step 1)"
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = 1 ] && [ "$(uname -m)" != arm64 ]; then
    die "this shell runs under Rosetta (x86_64) on an Apple Silicon Mac: open a native terminal (README step 0)"
fi

# Homebrew, on PATH even when the shell's profile does not set it up yet
if ! command -v brew >/dev/null; then
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)" && break; done
fi
command -v brew >/dev/null || die "no Homebrew: install it from https://brew.sh (README step 2)"
eval "$(brew shellenv)"                                       # HOMEBREW_PREFIX, which mac.toml uses
say "Homebrew in $HOMEBREW_PREFIX ($(uname -m))"

dry=0
for a in "$@"; do case "$a" in -n|--dry-run) dry=1 ;; esac; done
if [ "$dry" = 1 ]; then                                       # a dry run installs nothing: it only says
    brew bundle check --file "$HERE/Brewfile" >&2 || say "the Brewfile is not all installed (a real run installs it)"
elif [ "${BREW_BUNDLE:-1}" != 0 ]; then
    say "Homebrew packages (Brewfile)"
    brew bundle --file "$HERE/Brewfile"
fi

# GNU make, sed and coreutils ahead of Apple's, as setup.sh has them later
for g in make gnu-sed coreutils; do PATH="$HOMEBREW_PREFIX/opt/$g/libexec/gnubin:$PATH"; done
export PATH

# A Python with tomllib (3.11+): Homebrew's. It runs build_stack.py and the venv is made from it.
PY=""
for v in 3.13 3.12 3.11; do
    [ -x "$HOMEBREW_PREFIX/bin/python$v" ] && { PY="$HOMEBREW_PREFIX/bin/python$v"; break; }
done
[ -n "$PY" ] || die "no Homebrew Python 3.11+: brew install python@3.12"

# Arguments after mac.toml's, so the command line wins over it
exec "$PY" "$HERE/../build_stack.py" --config "$HERE/mac.toml" python="$PY" "$@"
