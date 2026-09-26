// -*- C++ -*-
// Lamriv — Λ → p π⁻ reconstruction as a Rivet analysis.
//
// The same measurement as `modules/Lambda/Lambda.cc`, through the other door. They exist together
// on purpose: side by side in one `analysis.yoda` they answer "does the framework's own module path
// agree with Rivet?" — and because the *physics* is one shared header, any disagreement is in the
// framework, not in the reconstruction.
//
//   modules/Lambda/Reconstruction.hh   the pairing, the mass window, cos θ*, the greedy matching
//   modules/Lambda/Lambda.cc           calls it as a `Module::Base` (framework sink)
//   analyses/Lambda/Lamriv.cc          calls it as a `Rivet::Analysis`  ← this file
//
// The build passes `-I utils -I modules/<project> -DHEKIT_WITH_HEPMC=1` to `rivet-build`, which is
// what lets a plugin use `Phys` and the project's own headers at all. Rivet already links HepMC3,
// so no extra library is needed.
//
// **Input.** Whatever Rivet is given: Pythia in process, or an external generator's HepMC3 through
// the usual FIFO — `Sink::Rivet` is the same sink either way, and this analysis cannot tell the
// difference. Output is YODA, as for any analysis.
//
// **Cuts** are analysis options, so they come from the run TOML rather than from a recompile:
//
//   MASSTOL     |m(pπ) − m(Λ)| accepted, GeV            (default 0.15)
//   COSTHETATOL 0 = off; else |cosθ* + 1| tolerance      (default 0.0)
//   RESERVED    beam protons per event, 2 × Z            (default 2, i.e. pp)
//   TRACKPTMIN  track pT threshold, GeV                  (default 0.0)
//   TRACKETAMAX track |eta| acceptance                   (default 8.0)
//   BINS        bins per distribution                    (default 100)
//   MASSAXIS    half-width of the mass axis about m(Λ)   (default 0.4)
//
// Where this differs from the module, and why:
//
//   * **Rivet's `FinalState` does the status-1 selection**, not a hand-written loop. It is the
//     projection everyone reading a Rivet analysis expects, and it is cached across analyses.
//   * **`FourMomentum` → `HepMC3::FourVector` at the boundary.** `Phys` is built on HepMC3 so the
//     physics layer carries no ROOT (D15), and Rivet's vectors are its own type, so one conversion
//     happens here rather than a second copy of the physics existing over there.

#include "Rivet/Analysis.hh"
#include "Rivet/Projections/FinalState.hh"

#include "Reconstruction.hh"          // modules/Lambda/, on the include path via the build

namespace Rivet {

  /// @brief Λ → p π⁻ candidates: every pair, the mass window, and the one-to-one matching
  class Lamriv : public Analysis {
  public:

    RIVET_DEFAULT_ANALYSIS_CTOR(Lamriv);

    void init() {
      _cuts.mass_tolerance     = getOption<double>("MASSTOL", 0.15);
      _cuts.cos_theta_tolerance = getOption<double>("COSTHETATOL", 0.0);
      _cuts.reserved_protons   = static_cast<std::size_t>(getOption<int>("RESERVED", 2));
      _ptmin                   = getOption<double>("TRACKPTMIN", 0.0);
      _etamax                  = getOption<double>("TRACKETAMAX", 8.0);
      const int bins           = getOption<int>("BINS", 100);

      // `SET` is what makes the three candidate sets comparable *as curves*.
      //
      // A page overlays **points**, and the three sets are three histograms inside one point — so
      // by default they land on three separate figures and there is no way to draw them together.
      // Naming the set as an analysis option turns "which set" into a point-level distinction, so
      //
      //     [quantity.set] type = "option", target = "Lamriv", option = "SET"
      //     [study.sets]   across = ["set"]
      //
      // gives three points from **one** generation, three curves on one page — the same machinery
      // any other option sweep uses. Rivet runs each variant over the same events in one pass.
      //
      // `SET = "all"` (the default) keeps the prefixed booking, so an ordinary run still produces
      // every set at once and stays comparable with the module. A named set books the same seven
      // distributions *unprefixed*, because the variant name already says which set it is —
      // `/Lamriv:SET=validated/mass` rather than `/Lamriv:SET=validated/validated_mass`.
      _which = getOption<std::string>("SET", "all");
      if (_which != "all") {
        bool known = false;
        for (std::size_t set = 0; set < Lambda::kSetCount; ++set)
          if (_which == Lambda::kSetNames[set]) { _only = set; known = true; }
        if (!known)
          throw UserError("Lamriv: SET must be all, unvalidated, validated or selected, not '"
                          + _which + "'");
      }
      const double masswin     = getOption<double>("MASSAXIS", 0.4);

      if (bins < 1) throw UserError("Lamriv: BINS must be at least 1");

      // Only the tracks that can pair. The cut is on the projection, so Rivet applies it once and
      // the analysis never sees a particle it would have thrown away.
      declare(FinalState(Cuts::abseta < _etamax && Cuts::pT > _ptmin*GeV), "FS");

      // One booking loop over the three sets, so a set cannot end up with a different axis from
      // its neighbours — which is the whole point of drawing them together.
      for (std::size_t set = 0; set < Lambda::kSetCount; ++set) {
        if (_only >= 0 && static_cast<int>(set) != _only) continue;
        const std::string tag = (_only >= 0) ? "" : std::string(Lambda::kSetNames[set]) + "_";
        book(_mass[set],       tag + "mass", bins, Lambda::kLambdaMass - masswin,
                                                   Lambda::kLambdaMass + masswin);
        book(_energy[set],     tag + "energy", bins, 0.0, getOption<double>("ENERGYAXIS", 200.0));
        book(_momentum[set],   tag + "momentum", bins, 0.0, getOption<double>("MOMENTUMAXIS", 200.0));
        book(_pt[set],         tag + "pt", bins, 0.0, getOption<double>("PTAXIS", 20.0));
        book(_pz[set],         tag + "pz", bins, -getOption<double>("MOMENTUMAXIS", 200.0),
                                                  getOption<double>("MOMENTUMAXIS", 200.0));
        book(_eta[set],        tag + "eta", bins, -getOption<double>("ETAAXIS", 8.0),
                                                   getOption<double>("ETAAXIS", 8.0));
        const int countmax = getOption<int>("COUNTAXIS", 50);
        book(_count[set],      tag + "count", countmax + 1, -0.5, countmax + 0.5);
      }
    }

    void analyze(const Event& event) {
      const FinalState& fs = apply<FinalState>(event, "FS");

      std::vector<Lambda::FourVector> protons, pions;
      for (const Particle& particle : fs.particles()) {
        if (particle.pid() == Lambda::kProtonPid)      protons.push_back(convert(particle));
        else if (particle.pid() == Lambda::kPionPid)   pions.push_back(convert(particle));
      }

      const Lambda::Candidates found = Lambda::reconstruct(protons, pions, _cuts);

      for (std::size_t set = 0; set < Lambda::kSetCount; ++set) {
        if (_only >= 0 && static_cast<int>(set) != _only) continue;
        const auto& candidates = found.of(static_cast<Lambda::Set>(set));
        for (const Lambda::FourVector& p : candidates) {
          _mass[set]->fill(p.m());
          _energy[set]->fill(p.e());
          _momentum[set]->fill(p.p3mod());
          _pt[set]->fill(p.perp());
          _pz[set]->fill(p.pz());
          // A candidate exactly along the beam has infinite η; filling it would claim a value it
          // does not have, so the η plot legitimately holds fewer entries than the others.
          if (std::isfinite(p.eta())) _eta[set]->fill(p.eta());
        }
        _count[set]->fill(static_cast<double>(candidates.size()));
      }
    }

    void finalize() {
      // σ / Σw, exactly as `Module::finalize` does it — the two must agree or the comparison is
      // measuring the scaling rather than the physics.
      const double sf = crossSection()/picobarn/sumOfWeights();
      for (std::size_t set = 0; set < Lambda::kSetCount; ++set) {
        if (_only >= 0 && static_cast<int>(set) != _only) continue;
        scale(_mass[set], sf);
        scale(_energy[set], sf);
        scale(_momentum[set], sf);
        scale(_pt[set], sf);
        scale(_pz[set], sf);
        scale(_eta[set], sf);
        scale(_count[set], sf);
      }
    }

  private:

    /// Rivet's four-vector to the one `Phys` and the shared reconstruction speak.
    static Lambda::FourVector convert(const Particle& particle) {
      const FourMomentum& p = particle.momentum();
      return Lambda::FourVector(p.px(), p.py(), p.pz(), p.E());
    }

    Lambda::Cuts _cuts;
    double _ptmin = 0.0, _etamax = 8.0;
    std::string _which = "all";
    int _only = -1;                 ///< -1 = every set, prefixed; else the one set, unprefixed

    Histo1DPtr _mass[Lambda::kSetCount], _energy[Lambda::kSetCount], _momentum[Lambda::kSetCount];
    Histo1DPtr _pt[Lambda::kSetCount], _pz[Lambda::kSetCount], _eta[Lambda::kSetCount];
    Histo1DPtr _count[Lambda::kSetCount];
  };

  RIVET_DECLARE_PLUGIN(Lamriv);

}
