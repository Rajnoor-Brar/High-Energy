// -*- C++ -*-
// Lamriv — Λ → p π⁻ reconstruction as a Rivet analysis.
//
// The same measurement as modules/Lambda/Lambda.cc, through the other door, from the one shared
// modules/Lambda/Reconstruction.hh (on the include path: the build passes -I modules/<project>).
// On the same events the two agree to floating-point precision, so a disagreement is in the
// frameworks, not in the reconstruction.
//
// **Cuts** are analysis options, set from the run TOML (a swept quantity with
// target = "<tag>/Lamriv"); the module takes the same ones from its config:
//
//   MASSTOL     |m(pπ) − m(Λ)| accepted, GeV            (default 0.15)
//   COSTHETATOL 0 = off; else |cosθ* + 1| tolerance      (default 0.0)
//   RESERVED    beam protons per event, 2 × Z            (default 2, i.e. pp)
//   TRACKPTMIN  track pT threshold, GeV                  (default 0.0)
//   TRACKETAMAX track |eta| acceptance                   (default 8.0)
//   BINS        bins per distribution                    (default 100)
//   MASSAXIS    half-width of the mass axis about m(Λ)   (default 0.4)
//   ENERGYAXIS, MOMENTUMAXIS, PTAXIS, ETAAXIS, COUNTAXIS   the other axes (200, 200, 20, 8, 50)
//   SET         all | unvalidated | validated | selected (default all)
//
// Rivet's FinalState does the status-1 selection and the track cuts; its FourMomentum becomes a
// HepMC3::FourVector at the boundary, which is what the shared reconstruction speaks.

#include "Rivet/Analysis.hh"
#include "Rivet/Projections/FinalState.hh"

#include "Reconstruction.hh"          // modules/Lambda/, on the include path via the build

namespace Rivet {

  /// @brief Λ → p π⁻ candidates: every pair, the mass window, and the one-to-one matching
  class Lamriv : public Analysis {
  public:

    RIVET_DEFAULT_ANALYSIS_CTOR(Lamriv);

    void init() {
      const Lambda::Cuts defaults;                           // the cuts' defaults live in Reconstruction.hh
      _cuts.mass_tolerance     = getOption<double>("MASSTOL", defaults.mass_tolerance);
      _cuts.cos_theta_tolerance = getOption<double>("COSTHETATOL", defaults.cos_theta_tolerance);
      _cuts.reserved_protons   = static_cast<std::size_t>(getOption<int>("RESERVED", static_cast<int>(defaults.reserved_protons)));
      _ptmin                   = getOption<double>("TRACKPTMIN", 0.0);
      _etamax                  = getOption<double>("TRACKETAMAX", 8.0);
      const int bins           = getOption<int>("BINS", 100);

      // SET turns "which candidate set" into an analysis option, so a quantity can sweep it and
      // the three sets become curves on one page: [quantities.set] target = "lamriv/Lamriv",
      // key = "SET". SET = "all" (the default) books every set, prefixed (validated_mass); a named
      // set books the same seven distributions unprefixed, because the variant path already says
      // which set it is (/Lamriv:SET=validated/mass).
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

      const double energyAxis = getOption<double>("ENERGYAXIS", 200.0), momentumAxis = getOption<double>("MOMENTUMAXIS", 200.0);
      const double ptAxis = getOption<double>("PTAXIS", 20.0), etaAxis = getOption<double>("ETAAXIS", 8.0);
      const int countmax = getOption<int>("COUNTAXIS", 50);
      // One booking loop over the three sets, so a set cannot end up with a different axis from
      // its neighbours — which is the whole point of drawing them together.
      for (std::size_t set = 0; set < Lambda::kSetCount; ++set) {
        if (_only >= 0 && static_cast<int>(set) != _only) continue;
        const std::string tag = (_only >= 0) ? "" : std::string(Lambda::kSetNames[set]) + "_";
        book(_mass[set],       tag + "mass", bins, Lambda::kLambdaMass - masswin,
                                                   Lambda::kLambdaMass + masswin);
        book(_energy[set],     tag + "energy", bins, 0.0, energyAxis);
        book(_momentum[set],   tag + "momentum", bins, 0.0, momentumAxis);
        book(_pt[set],         tag + "pt", bins, 0.0, ptAxis);
        book(_pz[set],         tag + "pz", bins, -momentumAxis, momentumAxis);
        book(_eta[set],        tag + "eta", bins, -etaAxis, etaAxis);
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
      // σ / Σw, exactly as Lambda.cc scales — the two must agree or the comparison is measuring
      // the scaling rather than the physics. Rivet writes the result as a density.
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

    /// Rivet's four-vector to the one the shared reconstruction speaks.
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
