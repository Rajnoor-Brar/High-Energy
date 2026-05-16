#pragma once

#include "Pythia8/Pythia.h"
#include "Types.hh"
#include "Monitor/Timer.hh"
namespace Lambda{
    struct Particle{
        Lorentz     lorentz;
        std::size_t protonIndex{};
        std::size_t pionIndex{};
        Double_t    massDiff{};
    };

    inline Double_t cosTheta(const Lorentz& proton, const Lorentz& pion, const Lorentz& lambda) {
        namespace VectorUtil = ROOT::Math::VectorUtil;

        const auto beta     = lambda.BoostToCM();
        const auto protonCM = VectorUtil::boost(proton, beta);
        const auto pionCM   = VectorUtil::boost(pion, beta);
        return (protonCM.Px() * pionCM.Px() +
                protonCM.Py() * pionCM.Py() +
                protonCM.Pz() * pionCM.Pz()) /
               (protonCM.P() * pionCM.P());
    }

    inline std::pair<std::vector<Lorentz>, std::vector<Lorentz>> harvestParticles(const Pythia8::Pythia& pythia) {
        std::vector<Lorentz> protons;
        std::vector<Lorentz> pions;
        protons.reserve(pythia.event.size());
        pions.reserve(pythia.event.size());

        for (int i = 0; i < pythia.event.size(); ++i) {
            const auto& particle = pythia.event[i];
            if (!particle.isFinal()) continue;

            if (particle.id() == ProtonPid) {
                protons.emplace_back( particle.px(), particle.py(), particle.pz(), particle.e());
            } else if (particle.id() == PionPid) {
                pions.emplace_back( particle.px(), particle.py(), particle.pz(), particle.e());
            }
        }

        return {std::move(protons), std::move(pions)};
    }

    inline Candidates reconstructCandidates(const std::vector<Lorentz>& protons, const std::vector<Lorentz>& pions, const Parameters& parameters){
        // BlockTimer timer("Candidate Reconstruction");
        Candidates result;
        const std::size_t candidateTarget = protons.size() > parameters.reservedProtons
            ? protons.size() - parameters.reservedProtons : 0;

        std::vector<bool> pionTaken(pions.size(), false);
        std::vector<bool> protonsTaken(protons.size(), false);
        std::vector<Particle> candidates;

        for (std::size_t iProton = 0; iProton < protons.size(); ++iProton) {
            const Lorentz& proton = protons[iProton];

            for (std::size_t iPion = 0; iPion < pions.size(); ++iPion) {
                const Lorentz& pion = pions[iPion];
                const Lorentz lambda = proton + pion;

                // result.unvalidated.push_back(lambda);

                // const Double_t theta = cosTheta(proton, pion, lambda);
                const bool massAccepted = lambda.M() > (kLambdaMass - parameters.massTolerance) && lambda.M() < (kLambdaMass + parameters.massTolerance);
                // const bool thetaAccepted =  theta > (-1 - parameters.cosThetaTolerance) && theta < (-1 + parameters.cosThetaTolerance);

                if (!(massAccepted /*&& thetaAccepted*/))  continue; 

                result.validated.push_back(lambda);
                const Double_t delta = std::abs(lambda.M() - kLambdaMass);
                candidates.push_back(Particle{lambda, iProton, iPion, delta});
            }
        }

        if (candidateTarget == 0) return result;

        std::sort( candidates.begin(), candidates.end(), [](const Particle& a, const Particle& b) { return a.massDiff < b.massDiff; } );

        for (const auto& candidate : candidates) {
            if (!protonsTaken[candidate.protonIndex] && !pionTaken[candidate.pionIndex]) {
                protonsTaken[candidate.protonIndex] = true;
                pionTaken[candidate.pionIndex] = true;
                result.selected.push_back(candidate.lorentz);
                if (result.selected.size() >= candidateTarget) break;
            }
        }
        return result;
    }


}
