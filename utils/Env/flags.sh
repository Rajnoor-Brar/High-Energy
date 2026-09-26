#!/usr/bin/env bash
# utils/Env/flags.sh — probe each library's *-config once and write build/flags.mk
# (docs/rework_v2/03_Layout_Build.md §5.3).
#
#   flags.sh [OUT]     probe and write OUT (default build/flags.mk)
#   flags.sh --key     print what the cache depends on, cheaply: no probe runs
#
# The Makefile compares FLAGS_KEY in the cache with `--key` on every invocation and rewrites the
# cache only when they differ. A cache keyed on less than everything it reads is a correctness bug
# waiting for an unusual environment (ledger L22, v1's 00/B38), so the key holds the resolved path
# of every tool probed, plus the two directories the non-config libraries come from.
set -u

TOOLS=(pythia8-config HepMC3-config yoda-config root-config fastjet-config lhapdf-config rivet-config pkg-config)

key() {
    local t
    for t in "${TOOLS[@]}"; do printf '%s=%s;' "$t" "$(command -v "$t" || echo -)"; done
    printf 'HEP_INSTALL=%s;ONNXRUNTIME_DIR=%s' "${HEP_INSTALL-}" "${ONNXRUNTIME_DIR-}"
}

if [ "${1-}" = "--key" ]; then key; exit 0; fi

OUT=${1:-build/flags.mk}
mkdir -p "$(dirname "$OUT")"

found=()
emit() {                                    # emit NAME FLAGS...
    local name=$1; shift
    printf 'FLAGS_%s := %s\n' "$name" "$*"
    found+=("$name")
}
probe() {                                   # probe NAME COMMAND ARGS...
    local name=$1; shift
    local out
    if command -v "$1" >/dev/null 2>&1 && out=$("$@" 2>/dev/null); then
        emit "$name" $out
    else
        printf '# %s: not found (%s)\n' "$name" "$*"
    fi
}
dir_lib() {                                 # dir_lib NAME DIR LIB — a library with no *-config
    local name=$1 dir=$2 lib=$3
    if [ -d "$dir/include" ] && [ -d "$dir/lib" ]; then
        emit "$name" "-I$dir/include" "-L$dir/lib" "-l$lib" "-Wl,-rpath,$dir/lib"
    else
        printf '# %s: not found (%s)\n' "$name" "$dir"
    fi
}

{
    echo "# build/flags.mk — written by utils/Env/flags.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ). Do not edit:"
    echo "# delete it, or run \`hep build --configure\`, to probe again."
    echo "FLAGS_KEY := $(key)"
    probe pythia8 pythia8-config --cxxflags --ldflags
    probe hepmc3  HepMC3-config --cflags --libs
    probe yoda    yoda-config --cppflags --libs
    probe root    root-config --cflags --libs
    probe fastjet fastjet-config --cxxflags --libs --plugins=yes
    probe lhapdf  lhapdf-config --cppflags --ldflags
    probe rivet   rivet-config --cppflags --ldflags --libs
    probe toml    pkg-config --cflags --libs tomlplusplus
    probe zstd    pkg-config --cflags --libs libzstd
    probe zlib    pkg-config --cflags --libs zlib
    dir_lib onnx    "${ONNXRUNTIME_DIR:-${HEP_INSTALL-}/onnxruntime}" onnxruntime
    dir_lib delphes "${HEP_INSTALL-}/delphes" Delphes
    echo "FOUND := ${found[*]}"
} > "$OUT.tmp" && mv "$OUT.tmp" "$OUT"

# One line per probe run, so "the second make probed nothing" is checkable (P0 S2, row 3).
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) probed: ${found[*]}" >> "$(dirname "$OUT")/flags.log"
echo "flags: probed ${#found[@]} libraries → $OUT" >&2
