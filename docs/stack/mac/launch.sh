#!/usr/bin/env bash
# docs/stack/mac/launch.sh — the HEP stack's environment on macOS, from any shell (zsh included):
#
#   docs/stack/mac/launch.sh                       # an interactive bash with $HEP/setup.sh loaded
#   docs/stack/mac/launch.sh hep run PhotoProduction/eic     # one command in that environment
#   HEP=/opt/hep docs/stack/mac/launch.sh          # another prefix (default ~/HEP)
#
# The environment (utils/Env/hep_env.sh) is bash, and macOS's own bash is 3.2: this runs Homebrew's.

set -euo pipefail
prefix=${HEP:-$HOME/HEP}
setup=$prefix/setup.sh
[ -f "$setup" ] || { echo "no $setup: build the stack first (bash docs/stack/mac/build.sh)" >&2; exit 1; }

if ! command -v brew >/dev/null; then
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do [ -x "$b" ] && eval "$("$b" shellenv)" && break; done
fi
command -v brew >/dev/null || { echo "no Homebrew (README step 2)" >&2; exit 1; }
eval "$(brew shellenv)"
bash5=$HOMEBREW_PREFIX/bin/bash
[ -x "$bash5" ] || { echo "no Homebrew bash: brew install bash" >&2; exit 1; }

if [ $# -eq 0 ]; then                                         # a shell: your ~/.bashrc, then the stack
    exec "$bash5" --rcfile <(printf '[ -f ~/.bashrc ] && source ~/.bashrc\nsource %q\nhep_status\n' "$setup") -i
fi
exec "$bash5" -c 'source "$0" && exec "$@"' "$setup" "$@"     # one command
