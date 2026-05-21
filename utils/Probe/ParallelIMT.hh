#pragma once

#include <atomic>
#include <cstddef>
#include <string>
#include <vector>

#include "Probe/Types.hh"

namespace Probe {

    class ProbeIMT {
      public:
        ProbeIMT();

        void configureProbe(std::string inputFile,
                            std::vector<EventParticleSpec> particleSpecs,
                            std::size_t threadCount,
                            std::size_t requestedEvents,
                            bool userRequestedEvents);

        void configureProbe(std::string inputFile,
                            ProbeConfig config,
                            std::size_t threadCount,
                            std::size_t requestedEvents,
                            bool userRequestedEvents);

        const std::string& inputFile() const;
        std::size_t threadCount() const;
        std::size_t eventCount() const;
        std::string stats() const;

        template<typename Callback>
        void run(Callback&& callback);

      private:
        using BufferT = std::vector<std::vector<std::vector<Lorentz>>>;

        template<typename Callback>
        void flushParallel(BufferT& buffer, Callback&& callback);

        void readSpecInto(const EventParticleSpec& spec,
                          std::size_t specOrdinal,
                          BufferT& buffer);

        bool                           configured_    = false;
        std::string                    inputFile_;
        std::vector<EventParticleSpec> specs_;
        std::size_t                    threadCount_   = 0;
        std::size_t                    eventCount_    = 0;
        Long64_t                       firstEventKey_ = 0;
        std::atomic<std::size_t>       consumed_{0};
    };

} // namespace Probe
