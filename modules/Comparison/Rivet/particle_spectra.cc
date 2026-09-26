// -*- C++ -*-
// particle_spectra — the four spectra of the user's scratch generator_comparison.cc, as a Rivet
// analysis, so any generator's events can be compared through one chain (configs/Comparison).
//
//   pt, energy, eta   every stable final-state particle, per event: (1/N) dN/dx
//   nch               the charged multiplicity, normalised to one
//
// The binning is the scratch file's: pT 0–200 GeV, E 0–500 GeV, η −10…10, N_ch 0–100, 100 bins each.
// Charged is Rivet's charge3 ≠ 0, not the scratch file's list of ten species.

#include "Rivet/Analysis.hh"
#include "Rivet/Projections/ChargedFinalState.hh"
#include "Rivet/Projections/FinalState.hh"

namespace Rivet {

  class particle_spectra : public Analysis {
  public:

    RIVET_DEFAULT_ANALYSIS_CTOR(particle_spectra);

    void init() {
      declare(FinalState(), "FS");
      declare(ChargedFinalState(), "CFS");
      book(_pt, "pt", 100, 0.0, 200.0);
      book(_energy, "energy", 100, 0.0, 500.0);
      book(_eta, "eta", 100, -10.0, 10.0);
      book(_nch, "nch", 100, 0.0, 100.0);
    }

    void analyze(const Event& event) {
      for (const Particle& p : apply<FinalState>(event, "FS").particles()) {
        _pt->fill(p.pT() / GeV);
        _energy->fill(p.E() / GeV);
        if (std::isfinite(p.eta())) _eta->fill(p.eta());
      }
      _nch->fill(apply<ChargedFinalState>(event, "CFS").size());
    }

    void finalize() {
      scale({_pt, _energy, _eta}, 1.0 / sumOfWeights());       // per event
      normalize(_nch);
    }

  private:
    Histo1DPtr _pt, _energy, _eta, _nch;
  };

  RIVET_DECLARE_PLUGIN(particle_spectra);

}
