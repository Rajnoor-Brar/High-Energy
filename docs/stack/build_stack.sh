#!/usr/bin/env bash
# docs/stack/build_stack.sh — build the HEP stack from source, with the lab PC's versions and fixes.
#
#   bash docs/stack/build_stack.sh                           # the core stack into ~/HEP
#   bash docs/stack/build_stack.sh PACKAGES=all JOBS=8       # everything, 8 jobs
#   bash docs/stack/build_stack.sh PACKAGES="rivet pythia8" RIVET_VERSION=4.1.4
#   bash docs/stack/build_stack.sh --dry-run                 # print the commands, run nothing
#
# A setting is any variable below, given as VAR=value here or in the environment. A finished step is
# stamped ($HEP_PREFIX/.stamps/<step>-<version>) and skipped after, so rerunning resumes; delete a
# stamp to redo its step. Each step logs to $HEP_PREFIX/logs/<step>.log. README.md explains the flags.

set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

for arg; do
    case "$arg" in
        -n|--dry-run) DRY_RUN=1 ;;
        -h|--help) sed -n '2,/^$/s/^# \{0,1\}//p' "${BASH_SOURCE[0]}"; exit ;;
        [A-Z]*=*) export "$arg" ;;
        *) echo "unknown argument '$arg' (see --help)" >&2; exit 2 ;;
    esac
done

# ── settings ───────────────────────────────────────────────────────────────────────────────────

: "${HEP_PREFIX:=$HOME/HEP}"          # src/ build/ install/ .venv/ logs/ setup.sh
: "${PACKAGES:=core}"                 # core | all | a list: "lhapdf hepmc3 fastjet" (built in table order)
: "${JOBS:=$(nproc)}"
: "${ROOT_JOBS:=$(awk -v j="$JOBS" '/MemTotal/ {n = int($2 / 3e6); print (n < 1 ? 1 : n > j ? j : n)}' /proc/meminfo)}"
#                                       ROOT's LLVM/Cling needs ~3 GB a job, or cc1plus is OOM-killed
: "${CXX_STD:=17}"                    # one C++ standard for the whole stack: ROOT, Rivet, Pythia share ABIs
: "${OPT_FLAGS:=-O2}"
: "${PYTHON:=python3}"                # the interpreter the venv is made from
: "${SYSTEM_DEPS:=1}"                 # 1: apt-get the system packages first; 0: they are installed
: "${GRAPHICS:=ON}"                   # ROOT's x11/opengl/webgui/asimage, Geant4's OpenGL: OFF when headless
: "${GEANT4_DATA:=ON}"                # Geant4's physics datasets (~4 GB), downloaded during its build
: "${ROOT_EXTRA:=}"                   # more ROOT cmake arguments: "-Droofit=OFF"
: "${FASTJET_PATCH:=$REPO/utils/Env/patches/fastjet-3.5.0-siscone-thread-local-ranlux.patch}"
#                                       thread-local SISCone state (L29); "" for none
: "${HEKIT_ROOT:=$REPO}"              # the High-Energy checkout that setup.sh loads utils/Env/hep_env.sh from
: "${DRY_RUN:=0}"
: "${PYTHON_PACKAGES:=numpy cython tomli_w rich pyyaml pillow matplotlib uproot awkward pytest}"
: "${PDF_SETS:=CT14lo CT14nlo CT10 CT18NLO CT18NNLO cteq6l1 MSHT20nlo_as118 MSTW2008lo68cl MSTW2008lo90cl \
MSTW2008lo68cl_nf3 MSTW2008lo68cl_nf4 MSTW2008lo68cl_nf4as5 MSTW2008lo90cl_nf3 MSTW2008lo90cl_nf4 \
MSTW2008lo90cl_nf4as5 NNPDF23_lo_as_0130_qed NNPDF23_nlo_as_0119_qed NNPDF40_nlo_as_01180 PDF4LHC21_40 \
PDF4LHC21_40_pdfas nNNPDF30_nlo_as_0118_A208_Z82}"
: "${APT_PACKAGES:=build-essential gfortran cmake git curl ca-certificates patch pkg-config libtool \
autoconf automake python3-venv python3-dev libxml2-dev libfftw3-dev libsqlite3-dev libx11-dev libxpm-dev \
libxft-dev libxext-dev liblzma-dev libpcre3-dev libglew-dev libgif-dev libftgl-dev libgraphviz-dev \
libcurl4-openssl-dev uuid-dev libkrb5-dev libssl-dev libgsl-dev libboost-all-dev libyaml-cpp-dev libzstd-dev \
zlib1g-dev libbz2-dev libzip-dev libtomlplusplus-dev texlive-latex-base texlive-latex-extra ocaml \
ocaml-findlib libgc-dev libxerces-c-dev libgl1-mesa-dev libglu1-mesa-dev libxmu-dev libxi-dev}"

# Sources: <NAME>_VERSION and <NAME>_URL override a row ($v is the version).
ARCH=$(uname -m); ARCH=${ARCH/x86_64/x64}
SOURCES='
lhapdf       6.5.6    https://lhapdf.hepforge.org/downloads/?f=LHAPDF-$v.tar.gz
hepmc3       3.3.1    https://hepmc.web.cern.ch/hepmc/releases/HepMC3-$v.tar.gz
fastjet      3.5.0    https://fastjet.fr/repo/fastjet-$v.tar.gz
fjcontrib    1.104    https://fastjet.hepforge.org/contrib/downloads/fjcontrib-$v.tar.gz
root         6.40.04  https://root.cern/download/root_v$v.source.tar.gz
yoda         2.1.3    https://yoda.hepforge.org/downloads?f=YODA-$v.tar.gz
rivet        4.1.3    https://rivet.hepforge.org/downloads/?f=Rivet-$v.tar.gz
pythia8      8317     https://pythia.org/download/pythia${v:0:2}/pythia$v.tgz
thepeg       2.3.0    https://thepeg.hepforge.org/downloads/?f=ThePEG-$v.tar.bz2
herwig       7.3.0    https://herwig.hepforge.org/downloads/?f=Herwig-$v.tar.bz2
delphes      3.5.1    https://github.com/delphes/delphes/archive/refs/tags/$v.tar.gz
sherpa       3.0.5    https://gitlab.com/sherpa-team/sherpa/-/archive/v$v/sherpa-v$v.tar.gz
madgraph     3.7.3    https://launchpad.net/mg5amcnlo/3.0/${v%.*}.x/+download/MG5_aMC_v$v.tar.gz
whizard      3.1.8    https://whizard.hepforge.org/downloads/?f=whizard-$v.tar.gz
onnxruntime  1.29.0   https://github.com/microsoft/onnxruntime/releases/download/v$v/onnxruntime-linux-$ARCH-$v.tgz
geant4       11.4.2   https://github.com/Geant4/geant4/archive/refs/tags/v$v.tar.gz
'
declare -A VER URL
while read -r p v u; do
    [ -n "$p" ] || continue
    V=${p^^}_VERSION U=${p^^}_URL
    v=${!V:-$v}; eval "u=\"$u\""
    VER[$p]=$v URL[$p]=${!U:-$u}
done <<< "$SOURCES"

CORE="python lhapdf hepmc3 fastjet root yoda rivet pythia8 herwig delphes pdfsets"
ALL="python lhapdf hepmc3 fastjet root yoda rivet pythia8 herwig delphes sherpa madgraph whizard onnxruntime geant4 pdfsets"

SRC=$HEP_PREFIX/src BUILD=$HEP_PREFIX/build INSTALL=$HEP_PREFIX/install VENV=$HEP_PREFIX/.venv
LOGS=$HEP_PREFIX/logs STAMPS=$HEP_PREFIX/.stamps LOG=/dev/null PKG=setup

# ── helpers ────────────────────────────────────────────────────────────────────────────────────

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf '\033[31merror: %s\033[0m\n' "$*" >&2; exit 1; }

# run CMD…: into the step's log; on failure, the log's tail and stop. A dry run only prints it.
run() {
    if [ "$DRY_RUN" = 1 ]; then echo "    $*"; return; fi
    echo "+ $*" >> "$LOG"
    "$@" >> "$LOG" 2>&1 || { tail -n 30 "$LOG" >&2; die "$PKG: '$*' failed; the whole log is $LOG"; }
}

# get NAME [DIR]: NAME's tarball (downloaded unless it is in src/), unpacked afresh into DIR (src/NAME).
get() {
    local file=$SRC/${URL[$1]##*[/=]} dir=${2:-$SRC/$1}
    [ -s "$file" ] || { run curl -fL --retry 3 -o "$file.part" "${URL[$1]}"; run mv "$file.part" "$file"; }
    run rm -rf "$dir"
    run mkdir -p "$dir"
    run tar xf "$file" -C "$dir" --strip-components=1
}

# ac NAME CONFIGURE-ARGS…: configure, make, make install, in src/NAME.
ac() {
    local dir=$SRC/$1; shift
    run env -C "$dir" ./configure "$@"
    run make -C "$dir" -j"$JOBS"
    run make -C "$dir" install
}

# cm NAME CMAKE-ARGS…: src/NAME built in build/NAME, installed into install/NAME.
cm() {
    local p=$1; shift
    run cmake -S "$SRC/$p" -B "$BUILD/$p" -DCMAKE_INSTALL_PREFIX="$INSTALL/$p" -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_STANDARD="$CXX_STD" "$@"
    run cmake --build "$BUILD/$p" -j"$JOBS"
    run cmake --install "$BUILD/$p"
}

# step NAME: build_NAME, logged and stamped; skipped when its stamp is there.
step() {
    PKG=$1 LOG=$LOGS/$1.log
    local v=${VER[$1]-} stamp=$STAMPS/$1${VER[$1]:+-${VER[$1]}}
    if [ -e "$stamp" ]; then say "$PKG${v:+ $v}: done already"; return; fi
    say "$PKG${v:+ $v}"
    [ "$DRY_RUN" = 1 ] || : > "$LOG"
    "build_$PKG"
    [ "$DRY_RUN" = 1 ] || touch "$stamp"
}

# ── the steps ──────────────────────────────────────────────────────────────────────────────────

build_system() {
    command -v apt-get >/dev/null || die "no apt-get: install the equivalents of APT_PACKAGES, then SYSTEM_DEPS=0"
    local sudo=; [ "$(id -u)" = 0 ] || sudo=sudo
    [ -z "$sudo" ] || [ "$DRY_RUN" = 1 ] || sudo -v          # its password prompt, before the log takes stderr
    run $sudo apt-get update
    # shellcheck disable=SC2086
    run $sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends $APT_PACKAGES
}

build_python() {
    [ -x "$VENV/bin/python" ] || run "$PYTHON" -m venv "$VENV"
    # shellcheck disable=SC2086
    run "$VENV/bin/pip" install $PYTHON_PACKAGES
}

build_lhapdf() { get lhapdf; ac lhapdf --prefix="$INSTALL/LHAPDF"; }

build_hepmc3() {
    get hepmc3
    # The Python dir must be HEPMC3_Python_SITEARCH<XY> (HEPMC3_PYTHON_INSTALL_DIR is ignored); LTO strips
    # the pybind11 symbols.
    cm hepmc3 -DHEPMC3_ENABLE_PYTHON=ON -DHEPMC3_PYTHON_VERSIONS="$PY" \
        -DHEPMC3_Python_SITEARCH"${PY/./}"="$VENV/lib/python$PY/site-packages" \
        -DHEPMC3_ENABLE_ROOTIO=OFF -DHEPMC3_ENABLE_SEARCH=ON -DHEPMC3_BUILD_EXAMPLES=OFF \
        -DCMAKE_CXX_FLAGS="$CXXFLAGS -fno-lto" -DCMAKE_SHARED_LINKER_FLAGS=-fno-lto
}

build_fastjet() {
    get fastjet
    # SISCone's random-number state is one per process: threads clustering at once get other jets (L29).
    [ -z "$FASTJET_PATCH" ] || run patch -d "$SRC/fastjet" -p0 -i "$FASTJET_PATCH"
    ac fastjet --prefix="$INSTALL/fastjet" --enable-shared --enable-allcxxplugins
    get fjcontrib
    ac fjcontrib --fastjet-config="$INSTALL/fastjet/bin/fastjet-config" --prefix="$INSTALL/fastjet" \
        CXXFLAGS="$CXXFLAGS -fPIC"
    run make -C "$SRC/fjcontrib" fragile-shared-install     # libfastjetcontribfragile.so
}

build_root() {
    local JOBS=$ROOT_JOBS g=$GRAPHICS
    get root
    # shellcheck disable=SC2086
    cm root -DPython3_EXECUTABLE="$VENV/bin/python" -Dpyroot=ON -Dmathmore=ON -Droofit=ON -Dtmva=ON \
        -Dfftw3=ON -Dsqlite=ON -Dxml=ON -Dgdml=ON -Dhttp=ON -Dimt=ON -Dssl=ON -Dvdt=ON \
        -Dx11="$g" -Dopengl="$g" -Dwebgui="$g" -Dasimage="$g" -Dbuiltin_freetype=ON -Dbuiltin_pcre=ON \
        -Dxrootd=ON -Dbuiltin_xrootd=ON -Ddavix=OFF $ROOT_EXTRA
}

build_yoda() { get yoda; ac yoda --prefix="$INSTALL/yoda"; }

build_rivet() {
    get rivet
    ac rivet --prefix="$INSTALL/rivet" --with-hepmc3="$INSTALL/hepmc3" --with-yoda="$INSTALL/yoda" \
        --with-fastjet="$INSTALL/fastjet"
}

build_pythia8() {
    local with=() p
    for p in root rivet; do                                     # their plugins, when they are there
        if [ -d "$INSTALL/$p" ] || [[ " $STEPS " == *" $p "* ]]; then with+=("--with-$p=$INSTALL/$p"); fi
    done
    get pythia8
    ac pythia8 --prefix="$INSTALL/pythia8" --with-lhapdf6="$INSTALL/LHAPDF" --with-hepmc3="$INSTALL/hepmc3" \
        --with-fastjet3="$INSTALL/fastjet" "${with[@]}" --with-python-bin="$VENV/bin/" \
        --with-python-lib="$VENV/lib/python$PY" --with-python-include="$PYINC" --cxx-common="$CXXFLAGS -fPIC"
}

build_herwig() {
    get thepeg
    # --with-hepmcversion=3: else ThePEG looks for HepMC2 under the HepMC3 prefix.
    ac thepeg --prefix="$INSTALL/herwig7" --with-hepmc="$INSTALL/hepmc3" --with-hepmcversion=3 \
        --with-fastjet="$INSTALL/fastjet" --with-lhapdf="$INSTALL/LHAPDF"
    get herwig
    run lhapdf install CT14lo CT14nlo        # Herwig's defaults read them: its make install needs them (L15)
    ac herwig --prefix="$INSTALL/herwig7" --with-thepeg="$INSTALL/herwig7" --with-fastjet="$INSTALL/fastjet" \
        --with-lhapdf="$INSTALL/LHAPDF"
}

build_delphes() {
    local -x PYTHIA8=$INSTALL/pythia8          # DelphesPythia8 too
    get delphes
    cm delphes -DROOT_DIR="$INSTALL/root/cmake"
}

build_sherpa() {
    get sherpa
    cm sherpa -DSHERPA_ENABLE_HEPMC3=ON -DHepMC3_DIR="$INSTALL/hepmc3/share/HepMC3/cmake" \
        -DSHERPA_ENABLE_RIVET=ON -DRIVET_DIR="$INSTALL/rivet" -DSHERPA_ENABLE_FASTJET=ON \
        -DFASTJET_DIR="$INSTALL/fastjet" -DSHERPA_ENABLE_LHAPDF=ON -DLHAPDF_DIR="$INSTALL/LHAPDF" \
        -DSHERPA_ENABLE_INTERNAL_PDFS=ON -DSHERPA_ENABLE_EXAMPLES=ON
}

build_madgraph() {                                 # a Python/Fortran tree: unpacked, pointed at the stack
    get madgraph "$INSTALL/madgraph"
    run sed -i -e "s|^#* *lhapdf *=.*|lhapdf = $INSTALL/LHAPDF/bin/lhapdf-config|" \
        -e "s|^#* *pythia8_path *=.*|pythia8_path = $INSTALL/pythia8|" \
        -e "s|^#* *automatic_html_opening *=.*|automatic_html_opening = False|" \
        "$INSTALL/madgraph/input/mg5_configuration.txt"
}

build_whizard() {
    get whizard
    # --enable-hepmc takes HepMC3 (there are no *hepmc3 options).
    ac whizard --prefix="$INSTALL/whizard" --enable-lhapdf --enable-hepmc --with-hepmc="$INSTALL/hepmc3" \
        --enable-fastjet --with-fastjet="$INSTALL/fastjet" --enable-pythia8 --with-pythia8="$INSTALL/pythia8" \
        --disable-dependency-tracking FC=gfortran
}

build_onnxruntime() { get onnxruntime "$INSTALL/onnxruntime"; }      # a released binary: no ABI to match

build_geant4() {
    get geant4
    cm geant4 -DGEANT4_BUILD_MULTITHREADED=ON -DGEANT4_INSTALL_DATA="$GEANT4_DATA" -DGEANT4_USE_GDML=ON \
        -DGEANT4_USE_OPENGL_X11="$GRAPHICS" -DGEANT4_USE_SYSTEM_CLHEP=OFF -DGEANT4_USE_SYSTEM_EXPAT=OFF \
        -DGEANT4_USE_SYSTEM_ZLIB=OFF -DGEANT4_INSTALL_DATA_TIMEOUT=1500
}

# shellcheck disable=SC2086
build_pdfsets() { run lhapdf install $PDF_SETS; }     # a set already there is skipped

# ── main ───────────────────────────────────────────────────────────────────────────────────────

case "$PACKAGES" in core) PACKAGES=$CORE ;; all) PACKAGES=$ALL ;; esac
for p in $PACKAGES; do [[ " $ALL " == *" $p "* ]] || die "no package '$p'; there are: $ALL"; done
STEPS=""
for p in $ALL; do [[ " $PACKAGES " != *" $p "* ]] || STEPS+=" $p"; done

say "HEP stack → $HEP_PREFIX:$STEPS"
say "C++$CXX_STD $OPT_FLAGS, $JOBS jobs (ROOT $ROOT_JOBS)$([ "$DRY_RUN" = 1 ] && echo ', dry run')"
[ "$DRY_RUN" = 1 ] || mkdir -p "$SRC" "$BUILD" "$INSTALL" "$LOGS" "$STAMPS"
[ "$SYSTEM_DEPS" = 0 ] || step system

# The build's environment: the venv first, every install on the paths (what setup.sh gives later).
PYTHON=$(command -v "$PYTHON") || die "no $PYTHON: install Python 3, or set PYTHON"
PY=$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
PYINC=$("$PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["include"])')
for d in LHAPDF hepmc3 fastjet root yoda rivet pythia8 herwig7; do
    PATH=$INSTALL/$d/bin:$PATH
    LD_LIBRARY_PATH=$INSTALL/$d/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
    PYTHONPATH=$INSTALL/$d/lib/python$PY/site-packages${PYTHONPATH:+:$PYTHONPATH}
done
export PATH=$VENV/bin:$PATH VIRTUAL_ENV=$VENV LD_LIBRARY_PATH PYTHONPATH \
    LHAPDF_DATA_PATH=$INSTALL/LHAPDF/share/LHAPDF CXXFLAGS="$OPT_FLAGS -std=c++$CXX_STD"

for p in $STEPS; do step "$p"; done

# setup.sh: the lab PC's stub, loading the checkout's hep_env.sh. One already there is kept.
if [ "$DRY_RUN" != 1 ] && [ ! -e "$HEP_PREFIX/setup.sh" ]; then
    cat > "$HEP_PREFIX/setup.sh" <<EOF
#!/bin/bash
# $HEP_PREFIX/setup.sh — source it once per session (written by docs/stack/build_stack.sh).
export HEP=$HEP_PREFIX
export HEP_INSTALL=\$HEP/install
export HEKIT_ROOT=\${HEKIT_ROOT:-$HEKIT_ROOT}
source "\$HEKIT_ROOT/utils/Env/hep_env.sh"
EOF
fi
say "done: source $HEP_PREFIX/setup.sh"
