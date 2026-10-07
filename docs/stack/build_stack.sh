#!/usr/bin/env bash
# docs/stack/build_stack.sh — build the HEP software stack from source, as the lab PC has it (~/HEP).
#
#   bash docs/stack/build_stack.sh                       # the core stack into $HOME/HEP
#   bash docs/stack/build_stack.sh PACKAGES=all JOBS=8   # everything, 8 jobs
#   bash docs/stack/build_stack.sh --config my.conf      # variables from a file (see stack.conf)
#   bash docs/stack/build_stack.sh --dry-run PACKAGES=all   # print what would run; run nothing
#   bash docs/stack/build_stack.sh --list                # the packages, their versions and order
#
# Every setting is a variable below, given (in rising precedence) by its default here, the
# environment, a --config file, or a VAR=value argument. A package that finished is stamped
# ($HEP_PREFIX/.stamps/<package>-<version>) and skipped next time: rerun the same command to resume.
# Each package's output goes to $HEP_PREFIX/logs/<package>.log; a failure prints its tail.
# docs/stack/README.md says why each flag is what it is.

set -Eeuo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd || true)

# ── command line ───────────────────────────────────────────────────────────────────────────────

usage() { sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

# Arguments first: the defaults below (download URLs among them) are worked out from what they set.
ACTION=build
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --list) ACTION=list ;;
        --dry-run|-n) export DRY_RUN=1 ;;
        --config) shift; [ -f "${1:-}" ] || { echo "no config file '${1:-}'" >&2; exit 2; }
                  # shellcheck disable=SC1090
                  source "$1" ;;
        *=*) [[ "${1%%=*}" =~ ^[A-Z0-9_]+$ ]] || { echo "not a setting: '$1'" >&2; exit 2; }
             export "${1%%=*}=${1#*=}" ;;
        *) echo "unknown argument '$1' (see --help)" >&2; exit 2 ;;
    esac
    shift
done

# ── settings (each may be overridden) ────────────────────────────────────────────────────────────

: "${HEP_PREFIX:=$HOME/HEP}"                     # src/, build/, install/, .venv/, setup.sh go here
: "${PACKAGES:=core}"                           # core | all | a list: "lhapdf hepmc3 fastjet …"
: "${JOBS:=$(nproc 2>/dev/null || echo 4)}"     # parallel jobs for every package but ROOT …
: "${ROOT_JOBS:=auto}"                          # … whose LLVM/Cling needs ~3 GB a job: auto = RAM ÷ 3 GB
: "${CXX_STD:=17}"                              # one C++ standard for the whole stack (ABI)
: "${OPT_FLAGS:=-O2}"
: "${PYTHON:=python3}"                          # the interpreter the venv is made from
: "${SYSTEM_DEPS:=auto}"                        # auto | apt | dnf | skip: install the OS packages first
: "${SUDO:=auto}"                               # auto: sudo when not root; "" for none
: "${DRY_RUN:=0}"                               # 1: print every command, run nothing
: "${FORCE:=}"                                  # packages to rebuild although stamped: "root rivet"
: "${KEEP_BUILD:=1}"                            # 0: remove a package's build dir once installed
: "${SETUP_STYLE:=auto}"                        # auto | repo | standalone (see write_setup)
: "${HEKIT_ROOT:=}"                             # the High-Energy repository, for SETUP_STYLE=repo

# Versions: the ones the lab PC runs (utils/Env/stack.toml, `hep status --stack`).
: "${LHAPDF_VERSION:=6.5.6}"
: "${HEPMC3_VERSION:=3.3.1}"
: "${FASTJET_VERSION:=3.5.0}"
: "${FJCONTRIB_VERSION:=1.104}"
: "${ROOT_VERSION:=6.40.04}"                    # not 6.40.00: its rootcling regression (README)
: "${YODA_VERSION:=2.1.3}"
: "${RIVET_VERSION:=4.1.3}"
: "${PYTHIA8_VERSION:=8317}"
: "${THEPEG_VERSION:=2.3.0}"
: "${HERWIG_VERSION:=7.3.0}"
: "${DELPHES_VERSION:=3.5.1}"
: "${SHERPA_VERSION:=3.0.5}"
: "${MADGRAPH_VERSION:=3.7.3}"
: "${WHIZARD_VERSION:=3.1.8}"
: "${ONNXRUNTIME_VERSION:=1.29.0}"
: "${GEANT4_VERSION:=11.4.2}"
: "${XROOTD_VERSION:=6.1.1}"                    # standalone client/server only: ROOT builds its own

# Features
: "${FASTJET_SISCONE_PATCH:=1}"                 # thread-local SISCone state (L29): several Rivets per process
: "${FASTJET_PATCH:=$REPO_ROOT/utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch}"
: "${ROOT_GRAPHICS:=ON}"                        # x11, opengl, webgui, asimage: OFF for a headless container
: "${ROOT_EXTRA:=}"                             # more ROOT cmake arguments: "-Dfoo=ON -Dbar=OFF"
: "${GEANT4_DATA:=ON}"                          # download Geant4's physics datasets (~4 GB) during the build
: "${GEANT4_X11:=ON}"                           # OpenGL/X11 visualisation
: "${GEANT4_MT:=ON}"                            # multithreaded
: "${SHERPA_EXTRA:=}"                           # more Sherpa cmake arguments
: "${PDF_SETS:=CT14lo CT14nlo CT10 CT18NLO CT18NNLO cteq6l1 MSHT20nlo_as118 MSTW2008lo68cl MSTW2008lo90cl \
MSTW2008lo68cl_nf3 MSTW2008lo68cl_nf4 MSTW2008lo68cl_nf4as5 MSTW2008lo90cl_nf3 MSTW2008lo90cl_nf4 \
MSTW2008lo90cl_nf4as5 NNPDF23_lo_as_0130_qed NNPDF23_nlo_as_0119_qed NNPDF40_nlo_as_01180 PDF4LHC21_40 \
PDF4LHC21_40_pdfas nNNPDF30_nlo_as_0118_A208_Z82}"
: "${PYTHON_PACKAGES:=numpy cython tomli_w rich pyyaml pillow matplotlib uproot awkward pytest}"   # the framework's
: "${PYTHON_EXTRAS:=vector hist mplhep particle hepunits scipy pandas scikit-learn xgboost lightgbm pyhf onnx}"

# Download locations; a tarball already in $HEP_PREFIX/src is used as it is (offline builds).
: "${LHAPDF_URL:=https://lhapdf.hepforge.org/downloads/?f=LHAPDF-${LHAPDF_VERSION}.tar.gz}"
: "${HEPMC3_URL:=https://hepmc.web.cern.ch/hepmc/releases/HepMC3-${HEPMC3_VERSION}.tar.gz}"
: "${FASTJET_URL:=https://fastjet.fr/repo/fastjet-${FASTJET_VERSION}.tar.gz}"
: "${FJCONTRIB_URL:=https://fastjet.hepforge.org/contrib/downloads/fjcontrib-${FJCONTRIB_VERSION}.tar.gz}"
: "${ROOT_URL:=https://root.cern/download/root_v${ROOT_VERSION}.source.tar.gz}"
: "${YODA_URL:=https://yoda.hepforge.org/downloads?f=YODA-${YODA_VERSION}.tar.gz}"
: "${RIVET_URL:=https://rivet.hepforge.org/downloads/?f=Rivet-${RIVET_VERSION}.tar.gz}"
: "${PYTHIA8_URL:=https://pythia.org/download/pythia${PYTHIA8_VERSION:0:2}/pythia${PYTHIA8_VERSION}.tgz}"
: "${THEPEG_URL:=https://thepeg.hepforge.org/downloads/?f=ThePEG-${THEPEG_VERSION}.tar.bz2}"
: "${HERWIG_URL:=https://herwig.hepforge.org/downloads/?f=Herwig-${HERWIG_VERSION}.tar.bz2}"
: "${DELPHES_URL:=https://github.com/delphes/delphes/archive/refs/tags/${DELPHES_VERSION}.tar.gz}"
: "${SHERPA_URL:=https://gitlab.com/sherpa-team/sherpa/-/archive/v${SHERPA_VERSION}/sherpa-v${SHERPA_VERSION}.tar.gz}"
: "${MADGRAPH_URL:=https://launchpad.net/mg5amcnlo/3.0/${MADGRAPH_VERSION%.*}.x/+download/MG5_aMC_v${MADGRAPH_VERSION}.tar.gz}"
: "${WHIZARD_URL:=https://whizard.hepforge.org/downloads/?f=whizard-${WHIZARD_VERSION}.tar.gz}"
: "${GEANT4_URL:=https://github.com/Geant4/geant4/archive/refs/tags/v${GEANT4_VERSION}.tar.gz}"
: "${XROOTD_URL:=https://github.com/xrootd/xrootd/releases/download/v${XROOTD_VERSION}/xrootd-${XROOTD_VERSION}.tar.gz}"
: "${ONNXRUNTIME_URL:=}"                        # empty: the release for this machine's architecture

CORE="venv lhapdf herwig_pdfs hepmc3 fastjet root yoda rivet pythia8 herwig delphes pdfsets"
ALL="venv lhapdf herwig_pdfs hepmc3 fastjet root yoda rivet pythia8 herwig delphes sherpa madgraph whizard onnxruntime geant4 pdfsets pyextras"
ORDER="venv lhapdf herwig_pdfs hepmc3 fastjet root yoda rivet pythia8 herwig delphes sherpa madgraph whizard onnxruntime geant4 xrootd pdfsets pyextras"
# What each package builds against: each must be installed already, or built before it in this run.
# The Python bindings (LHAPDF, HepMC3, ROOT, YODA, Rivet, Pythia8) go into the venv.
declare -A NEEDS=(
    [lhapdf]="venv" [herwig_pdfs]="lhapdf" [hepmc3]="venv" [root]="venv" [yoda]="venv"
    [rivet]="venv hepmc3 yoda fastjet" [pythia8]="venv lhapdf hepmc3 fastjet"
    [herwig]="lhapdf herwig_pdfs hepmc3 fastjet" [delphes]="root" [sherpa]="hepmc3 lhapdf rivet fastjet"
    [madgraph]="lhapdf pythia8" [whizard]="hepmc3 fastjet lhapdf pythia8" [pdfsets]="lhapdf" [pyextras]="venv"
)

SRC=$HEP_PREFIX/src
BUILD=$HEP_PREFIX/build
INSTALL=$HEP_PREFIX/install
VENV=$HEP_PREFIX/.venv
LOGS=$HEP_PREFIX/logs
STAMPS=$HEP_PREFIX/.stamps
STD="-std=c++${CXX_STD}"
CXXFLAGS_ALL="$OPT_FLAGS $STD"

# ── helpers ────────────────────────────────────────────────────────────────────────────────────

say()  { printf '\033[1m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# fail WHAT: the end of the package's log, then stop (a build is never carried on past a failure).
fail() {
    [ -f "$LOG" ] && { echo "--- the end of $LOG ---" >&2; tail -n 40 "$LOG" >&2; }
    die "${CURRENT:-setup}: $1 failed; the whole output is $LOG"
}

# run CMD…: the command, logged to the current package's log; printed only, with DRY_RUN=1.
run() {
    if [ "$DRY_RUN" = 1 ]; then
        printf '    %s\n' "$*"
        return 0
    fi
    printf '+ %s\n' "$*" >> "$LOG"
    "$@" >> "$LOG" 2>&1 || fail "$*"
}

# at DIR CMD…: run CMD in DIR.
at() { local dir=$1; shift; if [ "$DRY_RUN" = 1 ]; then printf '    (in %s)\n' "$dir"; run "$@"; else (cd "$dir" && run "$@"); fi; }

version_of() {
    case "$1" in
        venv) "$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "?" ;;
        lhapdf) echo "$LHAPDF_VERSION" ;; hepmc3) echo "$HEPMC3_VERSION" ;;
        fastjet) echo "$FASTJET_VERSION+$FJCONTRIB_VERSION$( [ "$FASTJET_SISCONE_PATCH" = 1 ] && echo +tls)" ;;
        root) echo "$ROOT_VERSION" ;; yoda) echo "$YODA_VERSION" ;; rivet) echo "$RIVET_VERSION" ;;
        pythia8) echo "$PYTHIA8_VERSION" ;; herwig) echo "$HERWIG_VERSION+$THEPEG_VERSION" ;;
        delphes) echo "$DELPHES_VERSION" ;; sherpa) echo "$SHERPA_VERSION" ;; madgraph) echo "$MADGRAPH_VERSION" ;;
        whizard) echo "$WHIZARD_VERSION" ;; onnxruntime) echo "$ONNXRUNTIME_VERSION" ;;
        geant4) echo "$GEANT4_VERSION" ;; xrootd) echo "$XROOTD_VERSION" ;;
        herwig_pdfs) echo "CT14" ;; pdfsets) echo "sets" ;; pyextras) echo "pip" ;;
    esac
}

stamp()   { echo "$STAMPS/$1-$(version_of "$1")"; }
is_done() { [ -f "$(stamp "$1")" ] && [[ " $FORCE " != *" $1 "* ]]; }

# fetch URL FILE: into $SRC/FILE, unless it is already there.
fetch() {
    local url=$1 file=$SRC/$2
    [ -s "$file" ] && return 0
    if [ "$DRY_RUN" = 1 ]; then printf '    download %s → %s\n' "$url" "$file"; return 0; fi
    printf '+ download %s\n' "$url" >> "$LOG"
    if command -v wget >/dev/null; then wget -q -O "$file.part" "$url" >> "$LOG" 2>&1 || fail "download $url"
    else curl -fsSL -o "$file.part" "$url" >> "$LOG" 2>&1 || fail "download $url"; fi
    mv "$file.part" "$file"
}

# unpack FILE DIR: $SRC/FILE into $SRC/DIR (its top folder renamed to DIR), unless DIR exists.
unpack() {
    local file=$SRC/$1 dir=$SRC/$2
    [ -d "$dir" ] && return 0
    if [ "$DRY_RUN" = 1 ]; then printf '    unpack %s → %s\n' "$file" "$dir"; return 0; fi
    rm -rf "$dir.part"; mkdir -p "$dir.part"
    tar xf "$file" -C "$dir.part" --strip-components=1 >> "$LOG" 2>&1 || fail "unpack $file"
    mv "$dir.part" "$dir"
}

missing() {   # missing PACKAGE: what it needs that is neither installed nor selected
    local p out=""
    for p in ${NEEDS[$1]-}; do
        is_done "$p" || check "$p" || [[ " $SELECTED " == *" $p "* ]] || out="$out $p"
    done
    echo "${out# }"
}

venv_python() { if [ -x "$VENV/bin/python" ]; then echo "$VENV/bin/python"; else echo "$PYTHON"; fi; }
python_tag() { "$(venv_python)" -c 'import sys; print("%d.%d" % sys.version_info[:2])'; }

# ── system packages ────────────────────────────────────────────────────────────────────────────

APT_PACKAGES="build-essential gfortran cmake git wget curl patch rsync pkg-config libtool autoconf automake \
python3-venv python3-dev libxml2-dev libfftw3-dev libsqlite3-dev libx11-dev libxpm-dev libxft-dev \
libxext-dev liblzma-dev libpcre3-dev libglew-dev libgif-dev libftgl-dev libgraphviz-dev libcurl4-openssl-dev \
uuid-dev libkrb5-dev libssl-dev libgsl-dev libboost-all-dev libyaml-cpp-dev libzstd-dev zlib1g-dev \
libbz2-dev libzip-dev libtomlplusplus-dev texlive-latex-base texlive-latex-extra \
ocaml ocaml-findlib libgc-dev libgomp1 \
libxerces-c-dev libgl1-mesa-dev libglu1-mesa-dev libxmu-dev libxi-dev"
DNF_PACKAGES="gcc gcc-c++ gcc-gfortran make cmake git wget curl patch rsync pkgconf-pkg-config libtool autoconf \
automake python3-devel libxml2-devel fftw-devel sqlite-devel libX11-devel libXpm-devel libXft-devel libXext-devel \
xz-devel pcre-devel glew-devel giflib-devel ftgl-devel graphviz-devel libcurl-devel libuuid-devel krb5-devel \
openssl-devel gsl-devel boost-devel yaml-cpp-devel libzstd-devel zlib-devel bzip2-devel libzip-devel \
tomlplusplus-devel texlive-latex ocaml ocaml-findlib gc-devel libgomp xerces-c-devel mesa-libGL-devel \
mesa-libGLU-devel libXmu-devel libXi-devel"

system_deps() {
    local mode=$SYSTEM_DEPS sudo=$SUDO
    [ "$mode" = skip ] && return 0
    if [ "$mode" = auto ]; then
        if command -v apt-get >/dev/null; then mode=apt
        elif command -v dnf >/dev/null; then mode=dnf
        else warn "no apt-get or dnf: install the system packages yourself (README, 'System packages')"; return 0; fi
    fi
    if [ "$sudo" = auto ]; then sudo=""; [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null && sudo=sudo; fi
    say "system packages ($mode)"
    LOG=$LOGS/system.log
    case "$mode" in
        apt) run $sudo env DEBIAN_FRONTEND=noninteractive apt-get update
             # shellcheck disable=SC2086
             run $sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $APT_PACKAGES ;;
        dnf) run $sudo dnf install -y epel-release || true
             # shellcheck disable=SC2086
             run $sudo dnf install -y --skip-broken $DNF_PACKAGES ;;
        *) die "SYSTEM_DEPS must be auto, apt, dnf or skip, not '$mode'" ;;
    esac
}

# ── the packages ───────────────────────────────────────────────────────────────────────────────

build_venv() {
    run "$PYTHON" -m venv "$VENV"
    run "$VENV/bin/pip" install --upgrade pip wheel setuptools
    # shellcheck disable=SC2086
    [ -z "$PYTHON_PACKAGES" ] || run "$VENV/bin/pip" install $PYTHON_PACKAGES
}

build_lhapdf() {
    fetch "$LHAPDF_URL" "LHAPDF-$LHAPDF_VERSION.tar.gz"
    unpack "LHAPDF-$LHAPDF_VERSION.tar.gz" "LHAPDF-$LHAPDF_VERSION"
    at "$SRC/LHAPDF-$LHAPDF_VERSION" env PYTHON="$VENV/bin/python" ./configure --prefix="$INSTALL/LHAPDF" \
        CXXFLAGS="$CXXFLAGS_ALL"
    at "$SRC/LHAPDF-$LHAPDF_VERSION" make -j"$JOBS"
    at "$SRC/LHAPDF-$LHAPDF_VERSION" make install
}

pdf_install() {   # pdf_install SET…: each not yet in the data directory
    local set todo=()
    for set in "$@"; do [ -d "$INSTALL/LHAPDF/share/LHAPDF/$set" ] || todo+=("$set"); done
    [ ${#todo[@]} -eq 0 ] || run env LHAPDF_DATA_PATH="$INSTALL/LHAPDF/share/LHAPDF" "$INSTALL/LHAPDF/bin/lhapdf" install "${todo[@]}"
}

# Herwig's default settings read CT14lo and CT14nlo: without them its `make install` cannot write
# its repository (L15), so they go in right after LHAPDF.
build_herwig_pdfs() { pdf_install CT14lo CT14nlo; }

build_hepmc3() {
    local py; py=$(python_tag)
    fetch "$HEPMC3_URL" "HepMC3-$HEPMC3_VERSION.tar.gz"
    unpack "HepMC3-$HEPMC3_VERSION.tar.gz" "HepMC3-$HEPMC3_VERSION"
    # The Python install dir must be given as HEPMC3_Python_SITEARCH<XY> (HEPMC3_PYTHON_INSTALL_DIR is
    # ignored), and LTO strips the pybind11 symbols: -fno-lto.
    run cmake -S "$SRC/HepMC3-$HEPMC3_VERSION" -B "$BUILD/hepmc3" \
        -DCMAKE_INSTALL_PREFIX="$INSTALL/hepmc3" -DCMAKE_BUILD_TYPE=Release \
        -DHEPMC3_ENABLE_PYTHON=ON -DHEPMC3_PYTHON_VERSIONS="$py" \
        -DHEPMC3_Python_SITEARCH"${py/./}"="$VENV/lib/python$py/site-packages" \
        -DHEPMC3_ENABLE_ROOTIO=OFF -DHEPMC3_ENABLE_SEARCH=ON -DHEPMC3_BUILD_EXAMPLES=OFF \
        -DCMAKE_CXX_FLAGS="$CXXFLAGS_ALL -fno-lto" -DCMAKE_SHARED_LINKER_FLAGS="-fno-lto"
    run cmake --build "$BUILD/hepmc3" -j"$JOBS"
    run cmake --install "$BUILD/hepmc3"
}

build_fastjet() {
    fetch "$FASTJET_URL" "fastjet-$FASTJET_VERSION.tar.gz"
    unpack "fastjet-$FASTJET_VERSION.tar.gz" "fastjet-$FASTJET_VERSION"
    if [ "$FASTJET_SISCONE_PATCH" = 1 ]; then
        # SISCone keeps one random-number state for the process: threads clustering at once get other
        # jets (L16, L29). The patch makes it per thread; one thread draws exactly what it did before.
        [ -f "$FASTJET_PATCH" ] || die "FASTJET_SISCONE_PATCH=1 but no patch at $FASTJET_PATCH"
        if [ "$DRY_RUN" = 1 ] || ! grep -q 'thread_local ranlux_state_t' \
                "$SRC/fastjet-$FASTJET_VERSION/plugins/SISCone/siscone/siscone/ranlux.cpp" 2>/dev/null; then
            at "$SRC/fastjet-$FASTJET_VERSION" patch -p0 -N -i "$FASTJET_PATCH"
        fi
    fi
    at "$SRC/fastjet-$FASTJET_VERSION" ./configure --prefix="$INSTALL/fastjet" --enable-shared \
        --enable-allcxxplugins CXXFLAGS="$CXXFLAGS_ALL"
    at "$SRC/fastjet-$FASTJET_VERSION" make -j"$JOBS"
    at "$SRC/fastjet-$FASTJET_VERSION" make install
    fetch "$FJCONTRIB_URL" "fjcontrib-$FJCONTRIB_VERSION.tar.gz"
    unpack "fjcontrib-$FJCONTRIB_VERSION.tar.gz" "fjcontrib-$FJCONTRIB_VERSION"
    at "$SRC/fjcontrib-$FJCONTRIB_VERSION" ./configure --fastjet-config="$INSTALL/fastjet/bin/fastjet-config" \
        --prefix="$INSTALL/fastjet" CXXFLAGS="$CXXFLAGS_ALL -fPIC"
    at "$SRC/fjcontrib-$FJCONTRIB_VERSION" make -j"$JOBS"
    at "$SRC/fjcontrib-$FJCONTRIB_VERSION" make install
    at "$SRC/fjcontrib-$FJCONTRIB_VERSION" make fragile-shared-install   # libfastjetcontribfragile.so
}

root_jobs() {
    [ "$ROOT_JOBS" != auto ] && { echo "$ROOT_JOBS"; return; }
    local kb; kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 8000000)
    local n=$(( kb / 3000000 )); [ "$n" -lt 1 ] && n=1; [ "$n" -gt "$JOBS" ] && n=$JOBS
    echo "$n"
}

build_root() {
    local gfx=$ROOT_GRAPHICS
    fetch "$ROOT_URL" "root_v$ROOT_VERSION.source.tar.gz"
    unpack "root_v$ROOT_VERSION.source.tar.gz" "root-$ROOT_VERSION"
    # FindPython3 (Python3_EXECUTABLE, not PYTHON_EXECUTABLE); its own xrootd (builtin_xrootd), not an
    # external 6.x one; one C++ standard for the stack.
    # shellcheck disable=SC2086
    run cmake -S "$SRC/root-$ROOT_VERSION" -B "$BUILD/root" \
        -DCMAKE_INSTALL_PREFIX="$INSTALL/root" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD="$CXX_STD" \
        -DPython3_EXECUTABLE="$VENV/bin/python" -Dpyroot=ON \
        -Dmathmore=ON -Droofit=ON -Dtmva=ON -Dfftw3=ON -Dsqlite=ON -Dxml=ON -Dgdml=ON -Dhttp=ON -Dimt=ON \
        -Dssl=ON -Dvdt=ON -Dx11="$gfx" -Dopengl="$gfx" -Dwebgui="$gfx" -Dasimage="$gfx" \
        -Dbuiltin_freetype=ON -Dbuiltin_pcre=ON -Dxrootd=ON -Dbuiltin_xrootd=ON -Ddavix=OFF \
        $ROOT_EXTRA
    # LLVM/Cling OOM-kills cc1plus at high parallelism and leaves truncated objects behind that fail
    # later links for unrelated-looking reasons: few jobs here, every other package is light.
    run cmake --build "$BUILD/root" -j"$(root_jobs)"
    run cmake --install "$BUILD/root"
}

build_yoda() {
    fetch "$YODA_URL" "YODA-$YODA_VERSION.tar.gz"
    unpack "YODA-$YODA_VERSION.tar.gz" "YODA-$YODA_VERSION"
    at "$SRC/YODA-$YODA_VERSION" env PYTHON="$VENV/bin/python" ./configure --prefix="$INSTALL/yoda" \
        CXXFLAGS="$CXXFLAGS_ALL"
    at "$SRC/YODA-$YODA_VERSION" make -j"$JOBS"
    at "$SRC/YODA-$YODA_VERSION" make install
}

build_rivet() {
    fetch "$RIVET_URL" "Rivet-$RIVET_VERSION.tar.gz"
    unpack "Rivet-$RIVET_VERSION.tar.gz" "Rivet-$RIVET_VERSION"
    at "$SRC/Rivet-$RIVET_VERSION" env PYTHON="$VENV/bin/python" ./configure --prefix="$INSTALL/rivet" \
        --with-hepmc3="$INSTALL/hepmc3" --with-yoda="$INSTALL/yoda" --with-fastjet="$INSTALL/fastjet" \
        CXXFLAGS="$CXXFLAGS_ALL"
    at "$SRC/Rivet-$RIVET_VERSION" make -j"$JOBS"
    at "$SRC/Rivet-$RIVET_VERSION" make install
}

build_pythia8() {
    local py inc extra=()
    py=$(python_tag)
    inc=$("$(venv_python)" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')
    # Built after ROOT and Rivet, so that both plugins (Pythia8Plugins/RivetHooks.h) are there.
    if check root || [[ " $SELECTED " == *" root "* ]]; then extra+=(--with-root="$INSTALL/root"); fi
    if check rivet || [[ " $SELECTED " == *" rivet "* ]]; then extra+=(--with-rivet="$INSTALL/rivet"); fi
    fetch "$PYTHIA8_URL" "pythia$PYTHIA8_VERSION.tgz"
    unpack "pythia$PYTHIA8_VERSION.tgz" "pythia$PYTHIA8_VERSION"
    at "$SRC/pythia$PYTHIA8_VERSION" ./configure --prefix="$INSTALL/pythia8" \
        --with-lhapdf6="$INSTALL/LHAPDF" --with-hepmc3="$INSTALL/hepmc3" --with-fastjet3="$INSTALL/fastjet" \
        "${extra[@]}" --with-python-bin="$VENV/bin/" --with-python-lib="$VENV/lib/python$py" \
        --with-python-include="$inc" --cxx-common="$CXXFLAGS_ALL -fPIC"
    at "$SRC/pythia$PYTHIA8_VERSION" make -j"$JOBS"
    at "$SRC/pythia$PYTHIA8_VERSION" make install
}

build_herwig() {
    fetch "$THEPEG_URL" "ThePEG-$THEPEG_VERSION.tar.bz2"
    unpack "ThePEG-$THEPEG_VERSION.tar.bz2" "ThePEG-$THEPEG_VERSION"
    # --with-hepmcversion=3: ThePEG otherwise looks for HepMC2 under the HepMC3 prefix.
    at "$SRC/ThePEG-$THEPEG_VERSION" ./configure --prefix="$INSTALL/herwig7" \
        --with-hepmc="$INSTALL/hepmc3" --with-hepmcversion=3 --with-fastjet="$INSTALL/fastjet" \
        --with-lhapdf="$INSTALL/LHAPDF" CXXFLAGS="$CXXFLAGS_ALL"
    at "$SRC/ThePEG-$THEPEG_VERSION" make -j"$JOBS"
    at "$SRC/ThePEG-$THEPEG_VERSION" make install
    fetch "$HERWIG_URL" "Herwig-$HERWIG_VERSION.tar.bz2"
    unpack "Herwig-$HERWIG_VERSION.tar.bz2" "Herwig-$HERWIG_VERSION"
    at "$SRC/Herwig-$HERWIG_VERSION" ./configure --prefix="$INSTALL/herwig7" \
        --with-thepeg="$INSTALL/herwig7" --with-fastjet="$INSTALL/fastjet" --with-lhapdf="$INSTALL/LHAPDF" \
        CXXFLAGS="$CXXFLAGS_ALL"
    at "$SRC/Herwig-$HERWIG_VERSION" make -j"$JOBS"
    at "$SRC/Herwig-$HERWIG_VERSION" env LHAPDF_DATA_PATH="$INSTALL/LHAPDF/share/LHAPDF" make install
}

build_delphes() {
    fetch "$DELPHES_URL" "Delphes-$DELPHES_VERSION.tar.gz"
    unpack "Delphes-$DELPHES_VERSION.tar.gz" "delphes-$DELPHES_VERSION"
    # PYTHIA8 in the environment: DelphesPythia8 is built too when Pythia is there.
    run env PYTHIA8="$INSTALL/pythia8" cmake -S "$SRC/delphes-$DELPHES_VERSION" -B "$BUILD/delphes" \
        -DCMAKE_INSTALL_PREFIX="$INSTALL/delphes" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_STANDARD="$CXX_STD" -DROOT_DIR="$INSTALL/root/cmake"
    run cmake --build "$BUILD/delphes" -j"$JOBS"
    run cmake --install "$BUILD/delphes"
}

build_sherpa() {
    fetch "$SHERPA_URL" "sherpa-$SHERPA_VERSION.tar.gz"
    unpack "sherpa-$SHERPA_VERSION.tar.gz" "sherpa-v$SHERPA_VERSION"
    # The _DIR spellings differ per package (HepMC3_DIR, RIVET_DIR, …): Sherpa's own, not typos.
    # shellcheck disable=SC2086
    run cmake -S "$SRC/sherpa-v$SHERPA_VERSION" -B "$BUILD/sherpa" \
        -DCMAKE_INSTALL_PREFIX="$INSTALL/sherpa" -DCMAKE_BUILD_TYPE=Release \
        -DSHERPA_ENABLE_HEPMC3=ON -DHepMC3_DIR="$INSTALL/hepmc3/share/HepMC3/cmake" \
        -DSHERPA_ENABLE_RIVET=ON -DRIVET_DIR="$INSTALL/rivet" \
        -DSHERPA_ENABLE_FASTJET=ON -DFASTJET_DIR="$INSTALL/fastjet" \
        -DSHERPA_ENABLE_LHAPDF=ON -DLHAPDF_DIR="$INSTALL/LHAPDF" \
        -DSHERPA_ENABLE_INTERNAL_PDFS=ON -DSHERPA_ENABLE_EXAMPLES=ON $SHERPA_EXTRA
    run cmake --build "$BUILD/sherpa" -j"$JOBS"
    run cmake --install "$BUILD/sherpa"
}

build_madgraph() {
    local dir="MG5_aMC_v${MADGRAPH_VERSION//./_}"
    fetch "$MADGRAPH_URL" "MG5_aMC_v$MADGRAPH_VERSION.tar.gz"
    unpack "MG5_aMC_v$MADGRAPH_VERSION.tar.gz" "$dir"
    # Not a build: a Python/Fortran tree, pointed at this stack's LHAPDF and Pythia8.
    run rm -rf "$INSTALL/madgraph"
    run cp -a "$SRC/$dir" "$INSTALL/madgraph"
    local conf=$INSTALL/madgraph/input/mg5_configuration.txt
    run sed -i -e "s|^#* *lhapdf *=.*|lhapdf = $INSTALL/LHAPDF/bin/lhapdf-config|" \
               -e "s|^#* *pythia8_path *=.*|pythia8_path = $INSTALL/pythia8|" \
               -e "s|^#* *automatic_html_opening *=.*|automatic_html_opening = False|" "$conf"
}

build_whizard() {
    command -v ocamlfind >/dev/null || [ "$DRY_RUN" = 1 ] || die "Whizard needs OCaml (O'Mega): ocaml and ocaml-findlib"
    fetch "$WHIZARD_URL" "whizard-$WHIZARD_VERSION.tar.gz"
    unpack "whizard-$WHIZARD_VERSION.tar.gz" "whizard-$WHIZARD_VERSION"
    # --enable-hepmc/--with-hepmc take HepMC3 (no *hepmc3 options); LHAPDF is found by lhapdf-config.
    at "$SRC/whizard-$WHIZARD_VERSION" env PATH="$INSTALL/LHAPDF/bin:$PATH" ./configure \
        --prefix="$INSTALL/whizard" --enable-lhapdf --enable-hepmc --with-hepmc="$INSTALL/hepmc3" \
        --enable-fastjet --with-fastjet="$INSTALL/fastjet" --enable-pythia8 --with-pythia8="$INSTALL/pythia8" \
        --disable-dependency-tracking FC=gfortran CXXFLAGS="$CXXFLAGS_ALL"
    at "$SRC/whizard-$WHIZARD_VERSION" make -j"$JOBS"
    at "$SRC/whizard-$WHIZARD_VERSION" make install
}

build_onnxruntime() {
    local arch url
    case "$(uname -m)" in x86_64) arch=x64 ;; aarch64|arm64) arch=aarch64 ;; *) die "no ONNX Runtime build for $(uname -m)" ;; esac
    url=${ONNXRUNTIME_URL:-https://github.com/microsoft/onnxruntime/releases/download/v$ONNXRUNTIME_VERSION/onnxruntime-linux-$arch-$ONNXRUNTIME_VERSION.tgz}
    # A released binary: it links nothing of the stack, so there is no ABI to match.
    fetch "$url" "onnxruntime-linux-$arch-$ONNXRUNTIME_VERSION.tgz"
    unpack "onnxruntime-linux-$arch-$ONNXRUNTIME_VERSION.tgz" "onnxruntime-linux-$arch-$ONNXRUNTIME_VERSION"
    run rm -rf "$INSTALL/onnxruntime"
    run cp -a "$SRC/onnxruntime-linux-$arch-$ONNXRUNTIME_VERSION" "$INSTALL/onnxruntime"
}

build_geant4() {
    fetch "$GEANT4_URL" "geant4-$GEANT4_VERSION.tar.gz"
    unpack "geant4-$GEANT4_VERSION.tar.gz" "geant4-$GEANT4_VERSION"
    # Its own CLHEP, Expat and zlib (kept apart from the system's, as ROOT's xrootd).
    run cmake -S "$SRC/geant4-$GEANT4_VERSION" -B "$BUILD/geant4" \
        -DCMAKE_INSTALL_PREFIX="$INSTALL/geant4" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD="$CXX_STD" \
        -DGEANT4_BUILD_MULTITHREADED="$GEANT4_MT" -DGEANT4_INSTALL_DATA="$GEANT4_DATA" -DGEANT4_USE_GDML=ON \
        -DGEANT4_USE_OPENGL_X11="$GEANT4_X11" -DGEANT4_USE_SYSTEM_CLHEP=OFF -DGEANT4_USE_SYSTEM_EXPAT=OFF \
        -DGEANT4_USE_SYSTEM_ZLIB=OFF -DGEANT4_INSTALL_DATA_TIMEOUT=1500
    run cmake --build "$BUILD/geant4" -j"$JOBS"
    run cmake --install "$BUILD/geant4"
}

build_xrootd() {
    fetch "$XROOTD_URL" "xrootd-$XROOTD_VERSION.tar.gz"
    unpack "xrootd-$XROOTD_VERSION.tar.gz" "xrootd-$XROOTD_VERSION"
    run cmake -S "$SRC/xrootd-$XROOTD_VERSION" -B "$BUILD/xrootd" -DCMAKE_INSTALL_PREFIX="$INSTALL/xrootd" \
        -DCMAKE_BUILD_TYPE=Release -DENABLE_PYTHON=OFF -DENABLE_TESTS=OFF
    run cmake --build "$BUILD/xrootd" -j"$JOBS"
    run cmake --install "$BUILD/xrootd"
}

# shellcheck disable=SC2086
build_pdfsets() { pdf_install $PDF_SETS; }

# shellcheck disable=SC2086
build_pyextras() { [ -z "$PYTHON_EXTRAS" ] || run "$VENV/bin/pip" install $PYTHON_EXTRAS; }

# ── checks after each package ──────────────────────────────────────────────────────────────────

check() {
    local b=$INSTALL
    case "$1" in
        venv) [ -x "$VENV/bin/python" ] ;;
        lhapdf) [ -x "$b/LHAPDF/bin/lhapdf-config" ] ;;
        hepmc3) [ -x "$b/hepmc3/bin/HepMC3-config" ] ;;
        fastjet) [ -x "$b/fastjet/bin/fastjet-config" ] ;;
        root) [ -x "$b/root/bin/root-config" ] ;;
        yoda) [ -x "$b/yoda/bin/yoda-config" ] ;;
        rivet) [ -x "$b/rivet/bin/rivet" ] ;;
        pythia8) [ -x "$b/pythia8/bin/pythia8-config" ] ;;
        herwig) [ -x "$b/herwig7/bin/Herwig" ] ;;
        delphes) [ -x "$b/delphes/bin/DelphesHepMC3" ] ;;
        sherpa) [ -x "$b/sherpa/bin/Sherpa" ] ;;
        madgraph) [ -x "$b/madgraph/bin/mg5_aMC" ] ;;
        whizard) [ -x "$b/whizard/bin/whizard" ] ;;
        onnxruntime) ls "$b"/onnxruntime/lib/libonnxruntime.so* >/dev/null 2>&1 ;;
        geant4) [ -x "$b/geant4/bin/geant4-config" ] ;;
        xrootd) [ -x "$b/xrootd/bin/xrootd" ] ;;
        *) true ;;
    esac
}

# ── the environment script ─────────────────────────────────────────────────────────────────────

# repo: a stub that sources the High-Energy repository's utils/Env/hep_env.sh, as the lab PC's
# ~/HEP/setup.sh does; standalone: the paths, the venv and the data variables, with nothing else.
write_setup() {
    local style=$SETUP_STYLE repo=${HEKIT_ROOT:-$REPO_ROOT} file=$HEP_PREFIX/setup.sh
    if [ "$style" = auto ]; then
        if [ -f "$repo/utils/Env/hep_env.sh" ]; then style=repo; else style=standalone; fi
    fi
    say "setup.sh ($style) → $file"
    [ "$DRY_RUN" = 1 ] && return 0
    if [ "$style" = repo ]; then
        cat > "$file" <<EOF
#!/bin/bash
# $file — source this once per session. Written by docs/stack/build_stack.sh.
# The environment itself is versioned in the repository: \$HEKIT_ROOT/utils/Env/hep_env.sh.
export HEP=$HEP_PREFIX
export HEP_INSTALL=\$HEP/install
export HEKIT_ROOT=\${HEKIT_ROOT:-$repo}
source "\$HEKIT_ROOT/utils/Env/hep_env.sh"
EOF
    else
        cat > "$file" <<'EOF'
#!/bin/bash
# setup.sh — the HEP stack's environment; source it once per session. Written by build_stack.sh.
[ -n "${HEP_ENV_LOADED-}" ] && return 0
export HEP=__HEP_PREFIX__
export HEP_INSTALL=$HEP/install
[ -f "$HEP/.venv/bin/activate" ] && source "$HEP/.venv/bin/activate"
_hep_prepend() { [ -d "$2" ] || return 0; case ":${!1-}:" in *":$2:"*) ;; *) export "$1=$2${!1:+:${!1}}" ;; esac; }
_py=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
for pkg in LHAPDF hepmc3 fastjet xrootd root yoda pythia8 rivet herwig7 delphes sherpa madgraph whizard onnxruntime geant4; do
    _hep_prepend PATH              "$HEP_INSTALL/$pkg/bin"
    _hep_prepend LD_LIBRARY_PATH   "$HEP_INSTALL/$pkg/lib"
    _hep_prepend LD_LIBRARY_PATH   "$HEP_INSTALL/$pkg/lib64"
    _hep_prepend PYTHONPATH        "$HEP_INSTALL/$pkg/lib/python$_py/site-packages"
    _hep_prepend PYTHONPATH        "$HEP_INSTALL/$pkg/lib64/python$_py/site-packages"
    _hep_prepend CMAKE_PREFIX_PATH "$HEP_INSTALL/$pkg"
    _hep_prepend PKG_CONFIG_PATH   "$HEP_INSTALL/$pkg/lib/pkgconfig"
done
_hep_prepend PYTHONPATH "$HEP_INSTALL/root/lib"
unset -f _hep_prepend; unset _py
export LHAPDF_DATA_PATH=$HEP_INSTALL/LHAPDF/share/LHAPDF
export ONNXRUNTIME_DIR=$HEP_INSTALL/onnxruntime
[ -f "$HEP_INSTALL/geant4/bin/geant4.sh" ] && source "$HEP_INSTALL/geant4/bin/geant4.sh"
export HEP_ENV_LOADED=1
EOF
        sed -i "s|__HEP_PREFIX__|$HEP_PREFIX|" "$file"
    fi
    chmod +x "$file"
}

# ── main ───────────────────────────────────────────────────────────────────────────────────────

case "$PACKAGES" in
    core) WANTED=$CORE ;;
    all) WANTED=$ALL ;;
    *) WANTED=$PACKAGES ;;
esac
for p in $WANTED; do [[ " $ORDER " == *" $p "* ]] || die "no package '$p' (--list shows them)"; done
SELECTED=""
for p in $ORDER; do [[ " $WANTED " == *" $p "* ]] && SELECTED="$SELECTED $p"; done
SELECTED="${SELECTED# }"

if [ "$ACTION" = list ]; then
    printf '%-12s %-18s %s\n' PACKAGE VERSION STATE
    for p in $ORDER; do
        state="—"; is_done "$p" && state="built"
        [[ " $SELECTED " == *" $p "* ]] && ! is_done "$p" && state="to build"
        printf '%-12s %-18s %s\n' "$p" "$(version_of "$p")" "$state"
    done
    echo; echo "core: $CORE"; echo "all:  $ALL"
    exit 0
fi

for p in $SELECTED; do                      # before anything runs: a build never stops halfway for this
    gap=$(missing "$p")
    [ -z "$gap" ] || die "$p needs $gap: add it to PACKAGES (or PACKAGES=core / all), or build it first"
done

say "HEP stack → $HEP_PREFIX   packages: $SELECTED"
say "C++$CXX_STD $OPT_FLAGS, $JOBS jobs (ROOT: $(root_jobs))$( [ "$DRY_RUN" = 1 ] && echo ', dry run: nothing is run')"
[ "$DRY_RUN" = 1 ] || mkdir -p "$SRC" "$BUILD" "$INSTALL" "$LOGS" "$STAMPS"
LOG=/dev/null
system_deps

export PATH="$INSTALL/LHAPDF/bin:$INSTALL/hepmc3/bin:$INSTALL/fastjet/bin:$INSTALL/root/bin:$INSTALL/yoda/bin:$INSTALL/rivet/bin:$INSTALL/pythia8/bin:$INSTALL/herwig7/bin:$PATH"
export LD_LIBRARY_PATH="$INSTALL/LHAPDF/lib:$INSTALL/hepmc3/lib:$INSTALL/fastjet/lib:$INSTALL/root/lib:$INSTALL/yoda/lib:$INSTALL/rivet/lib:$INSTALL/pythia8/lib:$INSTALL/herwig7/lib:${LD_LIBRARY_PATH-}"
export CMAKE_PREFIX_PATH="$INSTALL/hepmc3:$INSTALL/fastjet:$INSTALL/root:$INSTALL/LHAPDF:${CMAKE_PREFIX_PATH-}"
export LHAPDF_DATA_PATH="$INSTALL/LHAPDF/share/LHAPDF"

for CURRENT in $SELECTED; do
    if is_done "$CURRENT"; then say "$CURRENT $(version_of "$CURRENT"): built already (FORCE=\"$CURRENT\" rebuilds)"; continue; fi
    say "$CURRENT $(version_of "$CURRENT")"
    LOG=$LOGS/$CURRENT.log
    [ "$DRY_RUN" = 1 ] || { : > "$LOG"; rm -f "$STAMPS/$CURRENT"-*; }   # a forced rebuild is undone until it succeeds
    started=$SECONDS
    "build_$CURRENT"
    if [ "$DRY_RUN" != 1 ]; then
        check "$CURRENT" || die "$CURRENT installed nothing it should have; see $LOG"
        touch "$(stamp "$CURRENT")"
        [ "$KEEP_BUILD" = 1 ] || rm -rf "${BUILD:?}/$CURRENT"
        say "$CURRENT done in $(( (SECONDS - started) / 60 )) min"
    fi
done

write_setup
say "done: source $HEP_PREFIX/setup.sh"
