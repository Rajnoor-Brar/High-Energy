#!/bin/bash
# env/hep_env.sh — HEP shell environment (versioned; rework P0-S02, docs/rework/08_CLI.md §3).
#
# Sourced by the stub ~/HEP/setup.sh (alias `load_hep`), which sets HEP, HEP_INSTALL and HEKIT_ROOT.
# Safe to source repeatedly: path variables are only ever prepended once, and never get empty elements
# (an empty element means the CWD). `quit` removes exactly what was added here.

: "${HEP:=$HOME/HEP}"
: "${HEP_INSTALL:=$HEP/install}"
: "${HEKIT_ROOT:=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
export HEP HEP_INSTALL HEKIT_ROOT
# The file that sourced this one (the ~/HEP/setup.sh stub), re-sourced by hep_refresh
export HEP_SETUP="${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}"

_HEP_PACKAGES="LHAPDF hepmc3 fastjet xrootd root yoda pythia8 rivet herwig7 delphes sherpa madgraph whizard onnxruntime"
_HEP_SCALARS="LHAPDF_DATA_PATH ONNXRUNTIME_DIR"

# _hep_prepend VAR DIR — prepend DIR if it exists and is not already present; record the addition.
_hep_prepend() {
    [ -d "$2" ] || return 0
    case ":${!1-}:" in
        *":$2:"*) ;;
        *)  export "$1=$2${!1:+:${!1}}"
            export _HEP_ADDED="${_HEP_ADDED:+$_HEP_ADDED
}$1=$2" ;;
    esac
}

# _hep_strip VAR DIR — remove every DIR element from VAR; unset VAR when nothing is left.
_hep_strip() {
    local cur=":${!1-}:"
    while [[ $cur == *":$2:"* ]]; do cur=${cur//":$2:"/:}; done
    cur=${cur#:}; cur=${cur%:}
    if [ -n "$cur" ]; then export "$1=$cur"; else unset "$1"; fi
}

# --- status report (on demand; several version probes are slow) ---
# Strips version strings down to the number for most tools, with two exceptions: Sherpa keeps its
# codename ("3.0.5 (Erebus)"), and Herwig7/ThePEG share one line since `Herwig --version` reports both.
hep_status() {
    local GREEN=$'\033[0;32m' DIM=$'\033[2m' RESET=$'\033[0m'
    [ -t 1 ] || { GREEN=''; DIM=''; RESET=''; }

    _ver() {
        command -v "$1" &>/dev/null || { printf "%s—%s\n" "$DIM" "$RESET"; return; }
        local out v
        out=$("$@" 2>/dev/null | head -1)
        v=$(grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' <<< "$out" | head -1)
        printf "%s%s%s\n" "$GREEN" "${v:-$out}" "$RESET"
    }
    _flag() {
        [ -e "$1" ] && printf "%sinstalled%s\n" "$GREEN" "$RESET" || printf "%s—%s\n" "$DIM" "$RESET"
    }
    _sherpa_ver() {
        command -v Sherpa &>/dev/null || { printf "%s—%s\n" "$DIM" "$RESET"; return; }
        local out v
        out=$(Sherpa --version 2>/dev/null | head -1)
        v=$(grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?.*' <<< "$out")
        printf "%s%s%s\n" "$GREEN" "${v:-$out}" "$RESET"
    }
    _herwig_ver() {
        command -v Herwig &>/dev/null || { printf "%s—%s\n" "$DIM" "$RESET"; return; }
        local out hwv tpv
        out=$(Herwig --version 2>/dev/null)
        hwv=$(grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' <<< "$out" | sed -n '1p')
        tpv=$(grep -oE '[0-9]+\.[0-9]+(\.[0-9]+)?' <<< "$out" | sed -n '2p')
        if [ -n "$tpv" ]; then
            printf "%s%s with ThePEG %s%s\n" "$GREEN" "$hwv" "$tpv" "$RESET"
        else
            printf "%s%s%s\n" "$GREEN" "${hwv:-$out}" "$RESET"
        fi
    }

    echo "HEP environment — $HEP (repo: $HEKIT_ROOT)"
    echo " "
    printf "  %-10s %s\n" LHAPDF   "$(_ver lhapdf-config --version)"
    printf "  %-10s %s\n" HepMC3   "$(_ver HepMC3-config --version)"
    printf "  %-10s %s\n" FastJet  "$(_ver fastjet-config --version)"
    printf "  %-10s %s\n" ROOT     "$(_ver root-config --version)"
    printf "  %-10s %s\n" Yoda     "$(_ver yoda-config --version)"
    printf "  %-10s %s\n" Pythia8  "$(_ver pythia8-config --version)"
    printf "  %-10s %s\n" Rivet    "$(_ver rivet --version)"
    printf "  %-10s %s\n" Herwig7  "$(_herwig_ver)"
    printf "  %-10s %s\n" Delphes  "$(_flag "$HEP_INSTALL/delphes/bin/DelphesHepMC3")"
    printf "  %-10s %s\n" Sherpa   "$(_sherpa_ver)"
    printf "  %-10s %s\n" MadGraph "$(_flag "$HEP_INSTALL/madgraph/bin/mg5_aMC")"
    printf "  %-10s %s\n" Whizard  "$(_ver whizard --version)"
    printf "  %-10s %s\n" ONNXRT   "$(_flag "$HEP_INSTALL/onnxruntime/lib/libonnxruntime.so")"
    echo " "
    unset -f _ver _flag _sherpa_ver _herwig_ver
}

# --- routine commands ---
# quit: leave the environment. Removes the path elements added above, restores the scalars, deactivates
# the venv. Stays defined, and is a no-op when the environment is not loaded.
quit() {
    if [ -z "${HEP_ENV_LOADED-}" ]; then
        echo "HEP env not loaded"
        return 0
    fi
    if declare -F deactivate >/dev/null; then
        deactivate
    elif [ -n "${VIRTUAL_ENV-}" ]; then          # child shell: venv vars inherited, function not
        _hep_strip PATH "$VIRTUAL_ENV/bin"
        unset VIRTUAL_ENV VIRTUAL_ENV_PROMPT
    fi
    local var dir saved
    while IFS='=' read -r var dir; do
        [ -n "$var" ] && _hep_strip "$var" "$dir"
    done <<< "${_HEP_ADDED-}"
    for var in $_HEP_SCALARS; do
        saved="_HEP_SAVED_$var"
        if [ -n "${!saved-}" ]; then export "$var=${!saved}"; else unset "$var"; fi
        unset "$saved"
    done
    unset HEP_ENV_LOADED _HEP_ADDED
    hash -r
}
hep_refresh() {
    local setup="${HEP_SETUP:-$HEP/setup.sh}"
    quit >/dev/null
    source "$setup"
}
hep_src()     { cd "$HEP/src"; }
hep_build()   { cd "$HEP/build"; }
hep_install() { cd "$HEP/install"; }
# hep_cd PROJECT [configs|results|output|sources] — cd into a project directory of the repo.
hep_cd() {
    [ -n "${1-}" ] || { echo "usage: hep_cd PROJECT [configs|results|output|sources]"; return 2; }
    cd "$HEKIT_ROOT/${2:-configs}/$1"
}
hep_help() {
    cat << HLP
HEP environment commands:
  hep_status             show installed tool versions
  hep_refresh            reload the environment from scratch
  quit                   leave the HEP environment (restores paths, deactivates venv)
  hep_cd PROJECT [DIR]   cd to \$HEKIT_ROOT/DIR/PROJECT (DIR: configs|results|output|sources)
  hep_src                cd to \$HEP/src
  hep_build              cd to \$HEP/build
  hep_install            cd to \$HEP/install
  hep_help               this message
HLP
}

# Guard against double-sourcing. A child shell inherits the variables but not the functions defined
# above, so it only needs this file for the functions.
if [ -n "${HEP_ENV_LOADED-}" ]; then
    [[ $- == *i* ]] && echo "HEP env already loaded — $HEP (hep_help for commands)"
    return 0
fi

# Activate the Python venv
source "$HEP/.venv/bin/activate"

# Versioned legacy tools (rivpyth, ydplt, ydmrg) until hep replaces them (P4-S06)
_hep_prepend PATH "$HEKIT_ROOT/tools"

_hep_pyver=$("$HEP/.venv/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
for pkg in $_HEP_PACKAGES; do
    _hep_prepend PATH              "$HEP_INSTALL/$pkg/bin"
    _hep_prepend LD_LIBRARY_PATH   "$HEP_INSTALL/$pkg/lib"
    _hep_prepend LD_LIBRARY_PATH   "$HEP_INSTALL/$pkg/lib64"
    _hep_prepend PYTHONPATH        "$HEP_INSTALL/$pkg/lib/python$_hep_pyver/site-packages"
    _hep_prepend CMAKE_PREFIX_PATH "$HEP_INSTALL/$pkg"
    _hep_prepend PKG_CONFIG_PATH   "$HEP_INSTALL/$pkg/lib/pkgconfig"
done
# ROOT and Pythia install their Python modules into lib/ (import ROOT, import pythia8)
_hep_prepend PYTHONPATH "$HEP_INSTALL/root/lib"
_hep_prepend PYTHONPATH "$HEP_INSTALL/pythia8/lib"
unset pkg _hep_pyver

for _hep_var in $_HEP_SCALARS; do
    export "_HEP_SAVED_$_hep_var=${!_hep_var-}"
done
unset _hep_var
export LHAPDF_DATA_PATH="$HEP_INSTALL/LHAPDF/share/LHAPDF"
export ONNXRUNTIME_DIR="$HEP_INSTALL/onnxruntime"
# RIVET_ANALYSIS_PATH is deliberately not set: the tools prepend their plugin directory per run.
export HEP_ENV_LOADED=1
hash -r

# hep completion, cached: generating it costs a Python start-up, so it is only regenerated when the
# entry point is newer than the cache. Interactive shells only.
_hep_load_completion() {
    local hep_bin cache="${XDG_CACHE_HOME:-$HOME/.cache}/hekit/hep-complete.bash"
    hep_bin=$(command -v hep 2>/dev/null) || return 0
    if [ ! -s "$cache" ] || [ "$hep_bin" -nt "$cache" ]; then
        mkdir -p "$(dirname "$cache")"
        _HEP_COMPLETE=bash_source hep > "$cache" 2>/dev/null || { rm -f "$cache"; return 0; }
    fi
    source "$cache" 2>/dev/null
}
[[ $- == *i* ]] && _hep_load_completion

[[ $- == *i* ]] && echo "HEP env loaded — $HEP (hep_status for versions, hep_help for commands)"
return 0
