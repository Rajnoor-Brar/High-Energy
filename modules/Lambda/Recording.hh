#pragma once

#include "Record/Writer.hh"
#include "Types.hh"

namespace Lambda {

    inline void fillCandidates(Record::Writer& writer, const Candidates& candidates) {
        writer.fillParticleEvent<HistogramSet>({
            {HistogramSet::Unvalidated, candidates.unvalidated},
            {HistogramSet::Validated,   candidates.validated},
            {HistogramSet::Selected,    candidates.selected},
        });
    }

} // namespace Lambda
