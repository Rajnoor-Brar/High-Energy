// modules/Lambda/Lambda.cc — Λ → p π⁻ candidates from HepMC3 events, as a plain program.
// requires: root   (Module.hh adds hepmc3 toml)
//
//     Lambda.exe CONFIG.toml --input=EVENTS.hepmc --output=lambda.root
//
// The same measurement as the Rivet analysis Rivet/Lamriv.cc, through the other door, from the
// same shared Reconstruction.hh. Run on the same events (App_Pythia fans out to both), the two
// agree to floating-point precision, which is the check that both frameworks are wired right.
//
// Three nested candidate sets (unvalidated ⊇ validated ⊇ selected), each with the same six
// distributions and the per-event candidate count, as Lambda/<set>_<property> in the ROOT file.
// They are densities, dσ/dx in pb per unit of x, as Rivet writes them (L21, v1's 00/B42): filled
// raw, scaled once by σ/ΣW and divided by the bin width.
//
// Config (the tool table's [config], or a swept quantity with target = "<tag>"):
//   mass_tolerance 0.15, cos_theta_tolerance 0, reserved_protons 2, track_pt_min 0, track_eta_max 8,
//   bins 100, mass_axis 0.4, energy_axis 200, momentum_axis 200, pt_axis 20, eta_axis 8, count_axis 50
// — the defaults and meanings of Lamriv's options (MASSTOL, COSTHETATOL, RESERVED, …).

#include "Module.hh"
#include "Reconstruction.hh"

#include "TH1D.h"

#include <cmath>
#include <string>
#include <vector>

namespace {

    struct Tracks {
        double ptMin = 0.0, etaMax = 8.0;
        // Rivet's FinalState with Cuts::abseta < etaMax && Cuts::pT > ptMin, written out.
        std::vector<Lambda::FourVector> of(const HepMC3::GenEvent& event, int pid) const {
            std::vector<Lambda::FourVector> found;
            for (const auto& particle : event.particles()) {
                if (particle->status() != 1 || particle->pid() != pid) continue;
                const HepMC3::FourVector& p = particle->momentum();
                if (!(p.perp() > ptMin) || !(std::fabs(p.eta()) < etaMax)) continue;
                found.push_back(p);
            }
            return found;
        }
    };

    struct Set {
        TH1D *mass, *energy, *momentum, *pt, *pz, *eta, *count;
    };

}  // namespace

int main(int argc, char** argv) {
    Module::Job job(argc, argv);
    const Module::Values& c = job.config();

    Lambda::Cuts cuts;
    cuts.mass_tolerance = c.get("mass_tolerance", 0.15);
    cuts.cos_theta_tolerance = c.get("cos_theta_tolerance", 0.0);
    cuts.reserved_protons = static_cast<std::size_t>(c.get("reserved_protons", 2));
    const Tracks tracks{c.get("track_pt_min", 0.0), c.get("track_eta_max", 8.0)};
    const int bins = c.get("bins", 100);
    if (bins < 1) job.fail(Module::Config, "bins must be at least 1");
    const double massAxis = c.get("mass_axis", 0.4), energyAxis = c.get("energy_axis", 200.0);
    const double momentumAxis = c.get("momentum_axis", 200.0), ptAxis = c.get("pt_axis", 20.0);
    const double etaAxis = c.get("eta_axis", 8.0);
    const int countAxis = c.get("count_axis", 50);

    Module::RootOut out(job.output());
    Set sets[Lambda::kSetCount];
    for (std::size_t s = 0; s < Lambda::kSetCount; ++s) {
        const std::string tag = std::string("Lambda/") + Lambda::kSetNames[s] + "_";
        sets[s] = {out.book<TH1D>(tag + "mass", ";m(p#pi^{-}) [GeV];d#sigma/dm [pb/GeV]", bins,
                                  Lambda::kLambdaMass - massAxis, Lambda::kLambdaMass + massAxis),
                   out.book<TH1D>(tag + "energy", ";E [GeV];d#sigma/dE [pb/GeV]", bins, 0.0, energyAxis),
                   out.book<TH1D>(tag + "momentum", ";|p| [GeV];d#sigma/d|p| [pb/GeV]", bins, 0.0, momentumAxis),
                   out.book<TH1D>(tag + "pt", ";p_{T} [GeV];d#sigma/dp_{T} [pb/GeV]", bins, 0.0, ptAxis),
                   out.book<TH1D>(tag + "pz", ";p_{z} [GeV];d#sigma/dp_{z} [pb/GeV]", bins, -momentumAxis, momentumAxis),
                   out.book<TH1D>(tag + "eta", ";#eta;d#sigma/d#eta [pb]", bins, -etaAxis, etaAxis),
                   out.book<TH1D>(tag + "count", ";candidates per event;d#sigma/dN [pb]", countAxis + 1, -0.5, countAxis + 0.5)};
    }

    for (const Module::Event& event : job.events()) {
        const auto protons = tracks.of(event.hepmc(), Lambda::kProtonPid);
        const auto pions = tracks.of(event.hepmc(), Lambda::kPionPid);
        const Lambda::Candidates found = Lambda::reconstruct(protons, pions, cuts);
        const double w = event.weight();
        for (std::size_t s = 0; s < Lambda::kSetCount; ++s) {
            const auto& candidates = found.of(static_cast<Lambda::Set>(s));
            for (const Lambda::FourVector& p : candidates) {
                sets[s].mass->Fill(p.m(), w);
                sets[s].energy->Fill(p.e(), w);
                sets[s].momentum->Fill(p.p3mod(), w);
                sets[s].pt->Fill(p.perp(), w);
                sets[s].pz->Fill(p.pz(), w);
                if (std::isfinite(p.eta())) sets[s].eta->Fill(p.eta(), w);   // along the beam: no η
            }
            sets[s].count->Fill(static_cast<double>(candidates.size()), w);
        }
    }

    if (job.sumW() > 0) out.scale(job.crossSectionPb() / job.sumW(), "width");
    return job.finish();
}
