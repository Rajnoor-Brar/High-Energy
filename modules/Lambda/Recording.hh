#pragma once

#include <algorithm>
#include <chrono>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>

#include "Monitor.hh"
#include "Types.hh"
#include "TypeAid.hh"
#include "TH1D.h"

namespace Lambda {
    inline RootObjects* findObjects(RootArray& objects, HistogramSet set) {
        static_assert(
            static_cast<std::size_t>(HistogramSet::Selected) == kHistogramSetCount - 1,
            "Enum out of sync");
        const std::size_t index = static_cast<std::size_t>(set);
        if (index < objects.size() && objects[index].basis == set) return &objects[index];
        return nullptr;
    }

    inline void fill(RootObjects& object, const Lorentz& particle) {
        ++object.candidateCount;
        for (auto& hist : object.hists1D) Record::fill(hist, particle);
        for (auto& tree : object.trees) Record::fill(tree, particle);
    }

    inline void fill(RootArray& objects, HistogramSet set, const Lorentz& particle) {
        if (RootObjects* object = findObjects(objects, set)) fill(*object, particle);
    }

    inline void fillCandidates(RootArray& histogramSets, const Candidates& candidates) {
        // BlockTimer timer("Candidate Filling");
        Record::resetAllCounts(histogramSets);
        for (const auto& particle : candidates.unvalidated)
            fill(histogramSets, HistogramSet::Unvalidated, particle);
        for (const auto& particle : candidates.validated)
            fill(histogramSets, HistogramSet::Validated, particle);
        for (const auto& particle : candidates.selected)
            fill(histogramSets, HistogramSet::Selected, particle);
        Record::countAll(histogramSets);
    }
}
