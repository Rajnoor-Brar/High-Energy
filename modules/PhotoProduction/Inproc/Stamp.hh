#pragma once
// modules/PhotoProduction/Inproc/Stamp.hh — what every event gets before Rivet sees it: App_Pythia's own
// stamping, utils/PythiaRun.hh (V63: one numbering, one run info, the combined σ, the last σ stamped;
// L1, L2, L28), so the integrated run's events are the chain's by construction.

#include "PythiaRun.hh"

#include <utility>
#include <vector>

namespace Inproc {

    using Xsec = PythiaRun::Xsec;
    using Stamper = PythiaRun::Stamper;

    // Per weight, {σ, error} in pb, as Rivet would read them from the last event stamped (L28).
    inline std::vector<std::pair<double, double>> lastSigma(const Stamper& stamper) {
        const PythiaRun::Stamp last = stamper.last();
        std::vector<std::pair<double, double>> out;
        for (size_t i = 0; i < last.xs.size() && i < last.err.size(); ++i) out.emplace_back(last.xs[i], last.err[i]);
        return out;
    }

}  // namespace Inproc
