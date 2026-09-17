//For centre of mass energies 140.7 GeV
// -*- C++ -*-
#include "Rivet/Analysis.hh"
#include "Rivet/Projections/Beam.hh"
#include "Rivet/Projections/DISKinematics.hh"
#include "Rivet/Projections/FastJets.hh"
#include "fastjet/SISConePlugin.hh"
#include "Rivet/Projections/FinalState.hh"
#include "Rivet/Projections/ChargedFinalState.hh"


namespace Rivet {

  /// @brief ZEUS inclusive jet photoproduction study used to measure alpha_s  /// @author Jon Butterworth
  //Following analysis has been modified to predict similar events for eic energies
  class photo_18x275 : public Analysis {
  public:

    /// Constructor
    RIVET_DEFAULT_ANALYSIS_CTOR(photo_18x275);

    /// @name Analysis methods
    /// @{

    // Book projections and histograms
    void init() {

      // Projections
	ChargedFinalState cfs(Cuts::abseta < 3.5 && Cuts::pT > 0.1*GeV);
      declare(cfs, "CFS");

      // Jet schemes checked with original code, M.Wing, A.Geiser
      FinalState fs;
      double jet_radius = 1.0;
      declare(FastJets(fs, fastjet::JetAlgorithm::kt_algorithm, fastjet::RecombinationScheme::Et_scheme, jet_radius), "Jets");
      declare(FastJets(fs, fastjet::JetAlgorithm::antikt_algorithm, fastjet::RecombinationScheme::Et_scheme, jet_radius), "Jets_akt");

      // bit of messing about to use the correct recombnation scheme for SISCone.
      double overlap_threshold = 0.75;
      fastjet::SISConePlugin * plugin = new fastjet::SISConePlugin(jet_radius, overlap_threshold);
      plugin->set_use_jet_def_recombiner(true);
      JetDefinition siscone(plugin);
      siscone.set_recombination_scheme(fastjet::RecombinationScheme::Et_scheme);
      declare(FastJets(fs, siscone), "Jets_sis");

      declare(DISKinematics(), "Kinematics");
      
     std::vector<double> bin_edges = {5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41,43,45,47,49,51,56,61,66,71,76};
      std::vector<double> bin_edges2 = {5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,41};
     std::vector<double> bin_edge_pt ={0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0,2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 3.8, 4.0, 4.4, 4.8, 5.2, 5.6, 6.0, 6.4, 6.8, 7.2, 7.6, 8.0, 8.6, 9.3, 10.0, 10.8, 11.6, 12.4, 13.6, 15.0, 17,19,22};
     std::vector<double> bin_edge_nch={0,2,4,6,7,8,9,10,11,13,14,15,16, 17.0, 18.0, 19.0, 20.0, 21.0, 22.0,23.0, 24.0, 25.0, 26.0, 27.0, 28.0, 29.0, 30.0, 31.0,32.0, 33.0, 34.0, 35.0, 36.0,38,40,42,44,46,48,50,52,54,56,58,60,65,70,75,80}; 
      book(_h_1,"d01-x01-y01",bin_edges);
      book(_h_2,"d04-x01-y01",bin_edges2);
      book(_h_3,"d05-x01-y01",bin_edges);
      book(_h_4,"d06-x01-y01",bin_edges);
      book(_h_5,"d07-x01-y01",bin_edges);
      book(_h_6,"d08-x01-y01",bin_edges);
      book(_h_7,"d09-x01-y01",bin_edges);
      book(_h_8,"d10-x01-y01",bin_edges);
      book(_h_9,"d13-x01-y01",bin_edges);
      book(_h_10,"d14-x01-y01",bin_edges);
      
      book(_h_1a,"d02-x01-y01",28,-3.5,3.5);
      book(_h_2a,"d03-x01-y01",28,-3.5,3.5);
      book(_h_3a,"d11-x01-y01",28,-3.5,3.5);
      book(_h_4a,"d12-x01-y01",28,-3.5,3.5);
      
      book(_h_11,"d15-x01-y01",bin_edge_pt); //pT range upto 15 GeV
      book(_h_12,"d16-x01-y01",bin_edge_nch); //Nch range till 80
	book(_h_13,"d17-x01-y01",28,-3.5,3.5); //Total eta range    
    }

    // Do the analysis
    void analyze(const Event& event) {

      // Determine kinematics, including event orientation since ZEUS coord system is for +z = proton direction
      const DISKinematics& kin = apply<DISKinematics>(event, "Kinematics");
      const int orientation = kin.orientation();

      // Q2 and inelasticity cuts
      if (kin.Q2() > 1*GeV2) vetoEvent;
      if (!inRange(sqrt(kin.W2()), 62.7969, 129.5892)) vetoEvent; //y values are extracted from HERA range,  lower limit y=0.1992 and upper limit y=0.8483.  Formula for W=sqrt(sy) 

      // Jet selection
      /// @todo check the recombination scheme
      const Jets jets = apply<FastJets>(event, "Jets")          \
        .jets(Cuts::Et > 5*GeV && Cuts::etaIn(-3.5*orientation, 3.5*orientation), cmpMomByEt); //Modified from 17 GeV to 5 GeV this and below
      MSG_DEBUG("kT Jet multiplicity = " << jets.size());

      const Jets jets_akt = apply<FastJets>(event, "Jets_akt")		\
        .jets(Cuts::Et > 5*GeV && Cuts::etaIn(-3.5*orientation, 3.5*orientation), cmpMomByEt);

      const Jets jets_sis = apply<FastJets>(event, "Jets_sis")          \
        .jets(Cuts::Et > 5*GeV && Cuts::etaIn(-3.5*orientation, 3.5*orientation), cmpMomByEt);
	 
      const ChargedFinalState& charged = apply<ChargedFinalState>(event, "CFS");
      
	// Fill histograms
	
	_h_12->fill(charged.size());
      
      for (const Particle& p : charged.particles()) {
      _h_11->fill(p.pT()); //Momentum cut
      _h_13->fill(p.eta()); //eta range
      }

      for (const Jet& jet : jets ){
        _h_1->fill(jet.pt());
        _h_1a->fill(orientation*jet.eta());
        if (jet.pt()>10*GeV) { //changed from 21 GeV to 10 GeV
          _h_2a->fill(orientation*jet.eta());
        }
        if (orientation*jet.eta() < 0) {
          _h_2->fill(jet.pt());
        } else if (orientation*jet.eta() < 1) {
          _h_3->fill(jet.pt());
        } else if (orientation*jet.eta() < 1.5) {
          _h_4->fill(jet.pt());
        } else if (orientation*jet.eta() < 2) {
          _h_5->fill(jet.pt());
	} else if(orientation*jet.eta() <2.5) {
	 _h_9->fill(jet.pt());
	} else if(orientation*jet.eta() <3) {
	 _h_10->fill(jet.pt());
        } else {
          _h_6->fill(jet.pt());
        }
      }

      for (const Jet& jet : jets_akt ){
        _h_7->fill(jet.pt());
        _h_3a->fill(orientation*jet.eta());
      }
      for (const Jet& jet : jets_sis ){
        _h_8->fill(jet.pt());
        _h_4a->fill(orientation*jet.eta());
      }

    }

    // Finalize
    void finalize() {
      const double sf = crossSection()/picobarn/sumOfWeights();
        scale(_h_1, sf);
        scale(_h_2, sf);
        scale(_h_3, sf);
        scale(_h_4, sf);
        scale(_h_5, sf);
        scale(_h_6, sf);
        scale(_h_7, sf);
        scale(_h_8, sf);
	scale(_h_9, sf);
	scale(_h_10, sf);
        scale(_h_1a, sf);
        scale(_h_2a, sf);
        scale(_h_3a, sf);
        scale(_h_4a, sf);
	
	normalize(_h_11);
        normalize(_h_12);
	normalize(_h_13); 
   }

    /// @}

  private:

    /// @name Histograms
    /// @{
    Histo1DPtr _h_1,_h_2,_h_3,_h_4,_h_5,_h_6,_h_7,_h_8,_h_9,_h_10,_h_11,_h_12,_h_13,_h_1a,_h_2a,_h_3a,_h_4a;
      };
    RIVET_DECLARE_PLUGIN(photo_18x275);

}

