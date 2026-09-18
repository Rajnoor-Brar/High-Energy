#pragma once

// ── Core/Types.hh ────────────────────────────────────────────────────────────
// The few types other namespaces need from Core. Keeping them here means a higher layer can include
// `Core/Types.hh` alone rather than the whole facade (house style, 13 §1).

#include <cstdint>
#include <string>
#include <vector>

#include "Core/Errors.hh"

namespace Core {

    // How a run ended, in the form the summary and the terminal both want.
    struct Outcome {
        Exit exit = Exit::Ok;
        std::string message;
        bool stopped = false;
    };

    // Beams, as every adapter and sink needs them (03 §1: ids and energies are separate).
    struct Beams {
        std::vector<int> ids;                    // PDG, [A, B]
        std::vector<double> energies;            // GeV, [E_A, E_B]; one entry means √s
        double sqrtS = 0.0;                      // filled in by the source once it knows

        bool centreOfMass() const { return energies.size() == 1; }
    };

    // Counted the way P0-S04 found Pythia counts: attempts are not successes.
    struct Counts {
        long long attempted = 0;
        long long accepted = 0;
        long long written = 0;

        double acceptance() const {
            return attempted > 0 ? static_cast<double>(accepted) / static_cast<double>(attempted) : 0.0;
        }
    };

}  // namespace Core
