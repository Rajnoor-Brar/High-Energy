#pragma once

#include <cstddef>
#include <string>
#include <utility>
#include <vector>

#include "Config.hh"
#include "Probe/Event.hh"
#include "Probe/EventCount.hh"
#include "Probe/Parallel.hh"
#include "Probe/Types.hh"

namespace Probe {

    class ProbeParallel {
      public:
        std::string                 inputFile;
        std::vector<CollectionSpec> collections;
        std::size_t                 nThreads = 0;
        std::size_t                 nEvents  = 0;

        void resolveEvents() {
            if (nEvents > 0) return;
            nEvents = Probe::resolveEventCount(inputFile);
            if (nEvents == 0)
                nEvents = EventStream(inputFile, collections).nEvents();
        }

        template<typename Callback>
        void run(Callback&& callback) {
            runParallel(inputFile, collections,
                        std::forward<Callback>(callback),
                        nThreads, nEvents);
        }
    };

} // namespace Probe
