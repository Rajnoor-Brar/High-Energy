"""`hep new`: the files a new analysis, module or project starts from (P10-S01).

A scaffold is worth having only if what it writes is **correct and complete enough to build**. A
template with `TODO` where the important line goes teaches nothing and costs a search through the
docs anyway, so each of these is a working example of the smallest real thing:

  * an **analysis** is a Rivet plugin with its `.info`, which `hep build` compiles and
    `[rivet].analyses` can name straight away;
  * a **module** is a `Module::Base` with the four verbs and the scaling contract already obeyed —
    filling in `process`, scaling only in `finalize` — because those are the two things a first
    module gets wrong (05 §5);
  * a **project** is a directory with a config `hep plan` accepts and a base card.

Nothing here overwrites: a scaffold that silently replaced a file someone had been editing would be
the worst possible bug in a convenience command.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..errors import HepError

KINDS = ("analysis", "module", "project")


def check_name(name: str, kind: str) -> str:
    """A name that can be a C++ identifier, a file stem and a Rivet analysis name at once."""
    if not name:
        raise HepError(f"a {kind} needs a name")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise HepError(f"{name!r} cannot be a {kind} name",
                       hint="letters, digits and underscores, not starting with a digit — it "
                            "becomes a C++ class and a file name")
    return name


def write(path: Path, text: str) -> Path:
    """Write, refusing to overwrite. See the header note."""
    if path.exists():
        raise HepError(f"{path} already exists", hint="`hep new` never overwrites; move it aside")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ── an analysis ──────────────────────────────────────────────────────────────

def analysis_source(name: str) -> str:
    return f'''// -*- C++ -*-
// {name}: a Rivet analysis. Built by `hep build`; named in a config as
//
//     [rivet]
//     analyses = ["{name}"]
//     paths = ["build/analyses/<project>"]

#include "Rivet/Analysis.hh"
#include "Rivet/Projections/FinalState.hh"

namespace Rivet {{

  class {name} : public Analysis {{
  public:

    RIVET_DEFAULT_ANALYSIS_CTOR({name});

    void init() {{
      const FinalState fs(Cuts::abseta < 5.0);
      declare(fs, "FS");

      book(_h_multiplicity, "multiplicity", 50, 0.0, 200.0);
      book(_h_pt, "pt", 40, 0.0, 20.0);
      book(_c_events, "events");
    }}

    void analyze(const Event& event) {{
      const Particles particles = apply<FinalState>(event, "FS").particles();
      for (const Particle& particle : particles) _h_pt->fill(particle.pT() / GeV);
      _h_multiplicity->fill(particles.size());
      _c_events->fill();
    }}

    void finalize() {{
      // Rivet divides by the sum of weights; the cross-section makes it a differential rate.
      // This is the only place scaling belongs -- sigma is not final until here.
      scale(_h_multiplicity, crossSection() / picobarn / sumOfWeights());
      scale(_h_pt, crossSection() / picobarn / sumOfWeights());
    }}

  private:
    Histo1DPtr _h_multiplicity, _h_pt;
    CounterPtr _c_events;
  }};

  RIVET_DECLARE_PLUGIN({name});
}}
'''


def analysis_info(name: str) -> str:
    return f'''Name: {name}
Summary: One-line description of what {name} measures
Status: UNVALIDATED
Reentrant: true
Authors:
 - Your Name <you@example.org>
References:
 - 'https://example.org/paper'
Description:
  'What this analysis selects and what it plots. Written out, because this is what
  `hep analyses` shows and what a reader of the results will see first.'
Keywords: []
'''


# ── a module ─────────────────────────────────────────────────────────────────

def module_source(name: str) -> str:
    return f'''// {name}: a user analysis module (05 §5).
//
// Built as `libhekit_{name}.so` by the ordinary CMake rule and loaded with `dlopen`, so adding one
// never rebuilds `hep-run`. Named in a config as
//
//     [[sinks.module]]
//     name = "{name}"
//     paths = ["build/modules/<project>"]
//
// The four verbs happen in this order, and each is given exactly what it may use at that moment.
// The one rule worth stating: **fills are raw weights, and scaling happens only in `finalize`**,
// where sigma and the sum of weights are finally known. A `Results::Worker` has no `scale()`, so
// that is the shape of the types rather than a convention to remember.

#include "Module/Registry.hh"
#include "Module/Types.hh"
#include "Phys.hh"

#include "HepMC3/GenEvent.h"

namespace {{

    class {name} : public Module::Base {{
      public:
        void configure(const Core::Options& options) override {{
            acceptance_.pt_min = options.number("pt_min", 0.5);
            acceptance_.eta_max = options.number("eta_max", 5.0);
        }}

        void book(Results::Booker& booker) override {{
            multiplicity_ = booker.histo1D("multiplicity", 50, 0.0, 200.0,
                                           "final-state particles per event");
            pt_ = booker.histo1D("pt", 40, 0.0, 20.0, "particle $p_T$ [GeV]");
            counted_ = booker.counter("events", "events this module saw");
        }}

        void process(Events::View& view, Results::Worker& worker) override {{
            const HepMC3::GenEvent* event = view.hepmcOrNull();
            if (event == nullptr) return;
            const double weight = view.weights().nominal();

            const Phys::Particles kept = Phys::finalState(*event, acceptance_);
            for (const Phys::Particle& particle : kept)
                worker.fill(pt_, particle->momentum().perp(), weight);
            worker.fill(multiplicity_, static_cast<double>(kept.size()), weight);
            worker.count(counted_, weight);
        }}

        void finalize(Results::Final& results) override {{
            // sigma / sum(w) turns a weight sum into a cross-section. The only scaling there is.
            results.normalise(multiplicity_);
            results.normalise(pt_);
        }}

        // Say false if this module clusters jets or touches anything else shared: FastJet keeps
        // state in process-wide statics, and `process` is called from several workers at once
        // (00/B31, 00/B36).
        bool threadSafe() const override {{ return true; }}

      private:
        Phys::Acceptance acceptance_;
        Results::Handle multiplicity_ = 0;
        Results::Handle pt_ = 0;
        Results::Handle counted_ = 0;
    }};

}}  // namespace

HEKIT_MODULE("{name}", {name})
'''


# ── a project ────────────────────────────────────────────────────────────────

def project_card(name: str) -> str:
    return f'''! {name}: the base Pythia card every point of this project starts from.
! `hep run` copies it and appends the point's own settings, so put here only what never varies.

Beams:frameType = 2
Beams:idA = 2212
Beams:idB = 11

HardQCD:all = on
PhaseSpace:pTHatMin = 5.0

Print:quiet = on
'''


def project_config(name: str, analysis: str) -> str:
    return f'''schema = 2
project = "{name}"

[run]
name = "{name.lower()}"
events = 10000
seed = 1001
threads = 4

[generator]
tool = "pythia"
card = "base.cmnd"

[beams]
ids = [2212, 11]

[rivet]
analyses = ["{analysis}"]
paths = ["build/analyses/{name}"]

[output]
tag_style = "tag"

[settle.use]
energies = "27x920"

[quantity.energies]
type = "energies"
values = [[920, 27.5]]
labels = ["27 x 920 GeV"]
tags = ["27x920"]
use = 1

[study.first]
description = "one point, to check the chain works end to end"
'''
