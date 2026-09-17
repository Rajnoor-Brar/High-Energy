#pragma once

#include "Record/Writer.hh"
#include "Types.hh"

namespace Lambda {

    inline void fillCandidates(Record::Writer& writer, Candidates candidates) {
        writer.fillParticleEvent<HistogramSet>(
            std::vector<std::pair<HistogramSet, std::vector<Lorentz>>>{
                {HistogramSet::Unvalidated, std::move(candidates.unvalidated)},
                {HistogramSet::Validated,   std::move(candidates.validated)},
                {HistogramSet::Selected,    std::move(candidates.selected)},
            });
    }

} // namespace Lambda
