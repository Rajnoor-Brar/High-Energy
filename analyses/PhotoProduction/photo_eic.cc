// -*- C++ -*-
// photo_eic — inclusive-jet photoproduction observables for any ep beam configuration.
//
// Replaces photo_5x41 / photo_10x100 / photo_18x275, which differed only by
// their hard-coded W window (the HERA inelasticity range 0.1992 < y < 0.8483
// expressed in GeV for each sqrt(s)). Here the cuts are analysis options, set
// from the run TOML ([settle.rivet].options or [sweep.rivet.*] quantities):
//
//   YMIN, YMAX   inelasticity window (default 0.1992, 0.8483), used unless
//   WMIN, WMAX   a photon-proton W window in GeV is given (reproduces the old plugins)
//   Q2MAX        photon virtuality cut in GeV^2        (default 1.0)
//   ETMIN        jet E_T threshold in GeV               (default 5.0)
//   ETMIN2       higher E_T threshold for d03 in GeV    (default 10.0)
//   ETAMAX       jet |eta| acceptance                   (default 3.5)
//   R            jet radius for kT, anti-kT, SISCone    (default 1.0)
//   CHETAMAX     charged-particle |eta| acceptance      (default 3.5)
//   CHPTMIN      charged-particle pT threshold in GeV   (default 0.1)
//
// Based on ZEUS_2012_I1116258 (Jon Butterworth); ZEUS orientation convention:
// +z = proton direction. Histogram booking is identical to the old plugins.

#include "Rivet/Analysis.hh"
#include "Rivet/Projections/Beam.hh"
#include "Rivet/Projections/DISKinematics.hh"
#include "Rivet/Projections/FastJets.hh"
#include "fastjet/SISConePlugin.hh"
#include "Rivet/Projections/FinalState.hh"
#include "Rivet/Projections/ChargedFinalState.hh"


namespace Rivet {

  /// @brief Inclusive-jet photoproduction at EIC energies with option-driven cuts
  class photo_eic : public Analysis {
  public:

    RIVET_DEFAULT_ANALYSIS_CTOR(photo_eic);

    /// @name Analysis methods
    /// @{

    void init() {

      // Cuts from analysis options
      _wmin    = getOption<double>("WMIN", -1.0);
      _wmax    = getOption<double>("WMAX", -1.0);
      _ymin    = getOption<double>("YMIN", 0.1992);
      _ymax    = getOption<double>("YMAX", 0.8483);
      _q2max   = getOption<double>("Q2MAX", 1.0);
      _etmin   = getOption<double>("ETMIN", 5.0);
      _etmin2  = getOption<double>("ETMIN2", 10.0);
      _etamax  = getOption<double>("ETAMAX", 3.5);
      const double chEtaMax = getOption<double>("CHETAMAX", 3.5);
      const double chPtMin  = getOption<double>("CHPTMIN", 0.1);
      const double radius   = getOption<double>("R", 1.0);

      if ((_wmin < 0) != (_wmax < 0))
        throw UserError("photo_eic: WMIN and WMAX must be given together");
      _useW = _wmin >= 0;
      MSG_INFO("Cuts: " << (_useW ? "W in [" + to_str(_wmin) + ", " + to_str(_wmax) + "] GeV"
                                  : "y in [" + to_str(_ymin) + ", " + to_str(_ymax) + "]")
               << ", Q2 < " << _q2max << " GeV2, jet ET > " << _etmin << " (" << _etmin2
               << ") GeV, |eta| < " << _etamax << ", R = " << radius);

      // Projections
      ChargedFinalState cfs(Cuts::abseta < chEtaMax && Cuts::pT > chPtMin*GeV);
      declare(cfs, "CFS");

      // Jet schemes checked with original code, M.Wing, A.Geiser
      FinalState fs;
      declare(FastJets(fs, fastjet::JetAlgorithm::kt_algorithm, fastjet::RecombinationScheme::Et_scheme, radius), "Jets");
      declare(FastJets(fs, fastjet::JetAlgorithm::antikt_algorithm, fastjet::RecombinationScheme::Et_scheme, radius), "Jets_akt");

      // SISCone with the E_T recombination scheme.
      // `JetDefinition` does not own a plugin unless it is told to: without
      // `delete_plugin_when_unused()` this was leaked once per run, and once per worker in a
      // sharded run (00/B25).
      const double overlapThreshold = 0.75;
      fastjet::SISConePlugin* plugin = new fastjet::SISConePlugin(radius, overlapThreshold);
      plugin->set_use_jet_def_recombiner(true);
      JetDefinition siscone(plugin);
      siscone.delete_plugin_when_unused();
      siscone.set_recombination_scheme(fastjet::RecombinationScheme::Et_scheme);
      declare(FastJets(fs, siscone), "Jets_sis");

      declare(DISKinematics(), "Kinematics");

      const std::vector<double> etEdges = {5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51,56,61,66,71,76};
      const std::vector<double> etEdgesBackward = {5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41};
      const std::vector<double> ptEdges = {0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8,
                                           3.0, 3.2, 3.4, 3.6, 3.8, 4.0, 4.4, 4.8, 5.2, 5.6, 6.0, 6.4, 6.8, 7.2, 7.6,
                                           8.0, 8.6, 9.3, 10.0, 10.8, 11.6, 12.4, 13.6, 15.0, 17, 19, 22};
      const std::vector<double> nchEdges = {0,2,4,6,7,8,9,10,11,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,
                                            31,32,33,34,35,36,38,40,42,44,46,48,50,52,54,56,58,60,65,70,75,80};

      book(_h_1,  "d01-x01-y01", etEdges);          // kT, all eta
      book(_h_2,  "d04-x01-y01", etEdgesBackward);  // kT, eta < 0
      book(_h_3,  "d05-x01-y01", etEdges);          // kT, 0 < eta < 1
      book(_h_4,  "d06-x01-y01", etEdges);          // kT, 1 < eta < 1.5
      book(_h_5,  "d07-x01-y01", etEdges);          // kT, 1.5 < eta < 2
      book(_h_6,  "d08-x01-y01", etEdges);          // kT, eta > 3
      book(_h_7,  "d09-x01-y01", etEdges);          // anti-kT, all eta
      book(_h_8,  "d10-x01-y01", etEdges);          // SISCone, all eta
      book(_h_9,  "d13-x01-y01", etEdges);          // kT, 2 < eta < 2.5
      book(_h_10, "d14-x01-y01", etEdges);          // kT, 2.5 < eta < 3

      book(_h_1a, "d02-x01-y01", 28, -3.5, 3.5);    // kT eta, ET > ETMIN
      book(_h_2a, "d03-x01-y01", 28, -3.5, 3.5);    // kT eta, ET > ETMIN2
      book(_h_3a, "d11-x01-y01", 28, -3.5, 3.5);    // anti-kT eta
      book(_h_4a, "d12-x01-y01", 28, -3.5, 3.5);    // SISCone eta

      book(_h_11, "d15-x01-y01", ptEdges);          // charged-particle pT
      book(_h_12, "d16-x01-y01", nchEdges);         // charged multiplicity
      book(_h_13, "d17-x01-y01", 28, -3.5, 3.5);    // charged-particle eta
    }

    void analyze(const Event& event) {

      // Kinematics, including event orientation since ZEUS coordinates have +z = proton direction
      const DISKinematics& kin = apply<DISKinematics>(event, "Kinematics");
      const int orientation = kin.orientation();

      // Photoproduction and inelasticity cuts
      if (kin.Q2() > _q2max*GeV2) vetoEvent;
      if (_useW) {
        if (!inRange(sqrt(kin.W2()), _wmin, _wmax)) vetoEvent;
      } else if (!inRange(kin.y(), _ymin, _ymax)) vetoEvent;

      // Jet selection
      // The acceptance is symmetric in eta, so it is written that way: building it as
      // [-etamax*orientation, +etamax*orientation] gave an empty range when orientation = -1, and
      // every jet histogram would have come out empty without a word (00/B26). The orientation
      // still flips the eta that is *binned*, a few lines below.
      const Cut jetCut = Cuts::Et > _etmin*GeV && Cuts::abseta < _etamax;
      const Jets jets     = apply<FastJets>(event, "Jets").jets(jetCut, cmpMomByEt);
      const Jets jets_akt = apply<FastJets>(event, "Jets_akt").jets(jetCut, cmpMomByEt);
      const Jets jets_sis = apply<FastJets>(event, "Jets_sis").jets(jetCut, cmpMomByEt);
      MSG_DEBUG("kT jet multiplicity = " << jets.size());

      const ChargedFinalState& charged = apply<ChargedFinalState>(event, "CFS");

      _h_12->fill(charged.size());
      for (const Particle& p : charged.particles()) {
        _h_11->fill(p.pT());
        _h_13->fill(p.eta());
      }

      for (const Jet& jet : jets) {
        const double eta = orientation*jet.eta();
        _h_1->fill(jet.pt());
        _h_1a->fill(eta);
        if (jet.pt() > _etmin2*GeV) _h_2a->fill(eta);
        if      (eta < 0)   _h_2->fill(jet.pt());
        else if (eta < 1)   _h_3->fill(jet.pt());
        else if (eta < 1.5) _h_4->fill(jet.pt());
        else if (eta < 2)   _h_5->fill(jet.pt());
        else if (eta < 2.5) _h_9->fill(jet.pt());
        else if (eta < 3)   _h_10->fill(jet.pt());
        else                _h_6->fill(jet.pt());
      }

      for (const Jet& jet : jets_akt) {
        _h_7->fill(jet.pt());
        _h_3a->fill(orientation*jet.eta());
      }
      for (const Jet& jet : jets_sis) {
        _h_8->fill(jet.pt());
        _h_4a->fill(orientation*jet.eta());
      }
    }

    void finalize() {
      const double sf = crossSection()/picobarn/sumOfWeights();
      for (Histo1DPtr h : {_h_1, _h_2, _h_3, _h_4, _h_5, _h_6, _h_7, _h_8, _h_9, _h_10,
                           _h_1a, _h_2a, _h_3a, _h_4a})
        scale(h, sf);
      normalize(_h_11);
      normalize(_h_12);
      normalize(_h_13);
    }

    /// @}

  private:

    double _wmin = -1, _wmax = -1, _ymin = 0.1992, _ymax = 0.8483;
    double _q2max = 1.0, _etmin = 5.0, _etmin2 = 10.0, _etamax = 3.5;
    bool _useW = false;

    /// @name Histograms
    /// @{
    Histo1DPtr _h_1, _h_2, _h_3, _h_4, _h_5, _h_6, _h_7, _h_8, _h_9, _h_10, _h_11, _h_12, _h_13,
               _h_1a, _h_2a, _h_3a, _h_4a;
    /// @}
  };

  RIVET_DECLARE_PLUGIN(photo_eic);

}
