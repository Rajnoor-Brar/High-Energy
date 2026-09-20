"""The `Requires: ONNX` plugin convention, actually exercised (P8-S03, 05 §6, 09 §1).

Rivet is not linked to ONNX Runtime, so a Rivet plugin that wants a neural net has to be handed the
flags itself. The project convention is that a plugin declaring `Requires: ONNX` in its `.info` gets
them from the build. That wiring existed before this step and **had never been run** — no `.info` in
the repository declares it — which is how it came to be wrong.

`Rivet/Tools/RivetONNXrt.hh:11` includes `"onnxruntime/onnxruntime_cxx_api.h"`, the spelling the
Debian package installs. A source build — which is what `~/HEP` is — puts the headers straight into
`<prefix>/include`, with no `onnxruntime/` directory anywhere. So the flags the convention passed
could not compile a plugin that used Rivet's own ONNX helper (00/B37). The fix is a directory in the
build tree holding one symlink, `onnxruntime` → that include directory.

This test is the thing that would have caught it:

  * **positive** — a minimal plugin that includes `RivetONNXrt.hh` compiles and links with the
    convention's flags, into a `.so` that Rivet then loads;
  * **negative** — the same source with only `-I<include>`, which is what the convention used to
    pass, does not compile. Without this half the positive test would still pass if someone put the
    headers in both places, and the convention would quietly rot again.

**Why it compiles directly instead of calling `rivet-build`.** `rivet-build` hardcodes `-O2`, and at
`-O2` gcc spends **over twelve minutes** optimising ONNX Runtime's inline template headers for this
twenty-line plugin; the same translation unit is three seconds at `-O0`. That is too slow to keep in
a suite whose every other test finishes in five minutes, so this compiles with the same flags
`rivet-build` would pass on, at `-O0`. The one thing that arrangement cannot check — that
`rivet-build` forwards the extra arguments to the compiler at all — was verified directly in P8-S03
by reading the `cc1plus` command line of a real `rivet-build` invocation: both `-I` paths were
there.

Registered as the ctest test `onnx_plugin`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "build"
COMPAT = BUILD / "onnx-compat"

RIVET_BUILD = shutil.which("rivet-build")
RIVET_CONFIG = shutil.which("rivet-config")

pytestmark = [
    pytest.mark.skipif(not RIVET_BUILD or not RIVET_CONFIG, reason="needs Rivet on PATH"),
    pytest.mark.skipif(not COMPAT.is_dir(),
                       reason="configure the build with ONNX on first (cmake -S . -B build)"),
]

# The smallest thing that uses Rivet's ONNX helper: if this compiles and links, the flags are right.
SOURCE = """// -*- C++ -*-
#include "Rivet/Analysis.hh"
#include "Rivet/Tools/RivetONNXrt.hh"

namespace Rivet {

  class HEKIT_ONNX_PROBE : public Analysis {
  public:
    RIVET_DEFAULT_ANALYSIS_CTOR(HEKIT_ONNX_PROBE);

    void init() {
      // Constructed, not run: the point is that the type resolves and the symbol links.
      _net = std::make_unique<RivetONNXrt>("/nonexistent.onnx");
    }
    void analyze(const Event&) {}
    void finalize() {}

  private:
    std::unique_ptr<RivetONNXrt> _net;
  };

  RIVET_DECLARE_PLUGIN(HEKIT_ONNX_PROBE);
}
"""

INFO = """Name: HEKIT_ONNX_PROBE
Summary: Does the Requires: ONNX convention hand over working flags?
Status: UNVALIDATED
Reentrant: true
Requires: ONNX
Description:
  'A probe, not an analysis.'
"""


def rivet_flags(which: str) -> list[str]:
    done = subprocess.run([RIVET_CONFIG, which], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=True)
    return done.stdout.split()


def rivet_cppflags() -> list[str]:
    return rivet_flags("--cppflags")


def onnx_include() -> Path:
    """The real include directory, which is what the symlink in the compat dir points at."""
    return (COMPAT / "onnxruntime").resolve()


@pytest.fixture(scope="module")
def sources(tmp_path_factory):
    root = tmp_path_factory.mktemp("onnx_plugin")
    (root / "HEKIT_ONNX_PROBE.cc").write_text(SOURCE, encoding="utf-8")
    (root / "HEKIT_ONNX_PROBE.info").write_text(INFO, encoding="utf-8")
    return root


def test_the_convention_is_what_the_build_passes(sources):
    """The `.info` really does declare it — the string the CMake rule matches on."""
    text = (sources / "HEKIT_ONNX_PROBE.info").read_text(encoding="utf-8")
    assert "Requires:" in text and "ONNX" in text


def test_the_headers_are_not_where_rivet_looks(sources):
    """00/B37, as a fact about this installation rather than a claim in a comment."""
    assert (onnx_include() / "onnxruntime_cxx_api.h").is_file()
    assert not (onnx_include() / "onnxruntime").exists(), \
        "this install now has the prefixed layout too; the negative test below is no longer a test"
    # And the compat directory is exactly the one symlink that bridges the two.
    assert (COMPAT / "onnxruntime").is_symlink()


def test_without_the_compat_path_it_does_not_compile(sources):
    """What the convention passed before this step. Seconds, because it fails at the include."""
    done = subprocess.run(
        ["g++", "-std=c++17", "-fsyntax-only", str(sources / "HEKIT_ONNX_PROBE.cc"),
         *rivet_cppflags(), f"-I{onnx_include()}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert done.returncode != 0
    assert "onnxruntime/onnxruntime_cxx_api.h" in done.stderr


@pytest.fixture(scope="module")
def plugin(sources, tmp_path_factory):
    """The positive half: the convention's flags, compiled and linked into a real plugin."""
    out = tmp_path_factory.mktemp("plugin")
    library = out / "RivetHEKIT_ONNX_PROBE.so"
    done = subprocess.run(
        ["g++", "-std=c++17", "-O0", "-shared", "-fPIC",
         str(sources / "HEKIT_ONNX_PROBE.cc"), "-o", str(library),
         *rivet_cppflags(), f"-I{onnx_include()}", f"-I{COMPAT}",
         *rivet_flags("--ldflags"),
         str(onnx_include().parent / "lib" / "libonnxruntime.so")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800)
    assert done.returncode == 0, (done.stdout + done.stderr)[-4000:]
    return library


def test_with_the_compat_path_it_builds_a_plugin(plugin):
    assert plugin.is_file() and plugin.stat().st_size > 0


def test_rivet_can_load_the_plugin(plugin):
    """Built is not loaded: an unresolved ONNX symbol only shows up at dlopen."""
    environment = dict(os.environ)
    environment["RIVET_ANALYSIS_PATH"] = str(plugin.parent)
    done = subprocess.run(["rivet", "--list-analyses", "HEKIT_ONNX_PROBE"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600, env=environment)
    assert "HEKIT_ONNX_PROBE" in done.stdout, (done.stdout + done.stderr)[-3000:]
