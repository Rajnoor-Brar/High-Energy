#pragma once

#include <atomic>
#include <cstddef>
#include <string>
#include <vector>

#include "Probe/Types.hh"

namespace Probe {

    // ProbeIMT — ROOT-managed ImplicitMT bulk reader.
    //
    // The deliberate alternative to ProbeParallel, not a twin:
    //   ProbeParallel — explicit partition-per-thread readers + queue/collector
    //     modes; throughput capped (~150% CPU) by ROOT's global thread-safety
    //     lock, which serializes branch reads across independent TFiles.
    //   ProbeIMT — hands the read to ROOT::TTreeProcessorMT (tbb pool with
    //     fine-grained locks built for parallel basket decompression); the
    //     Phase-2 spike measured 5.3× at 8 threads on the same access pattern
    //     (see tests/spike_imt_read.cc and the decision matrix in its header).
    //
    // Trade-offs: callback delivery is window-bulk (not streaming), event
    // order is ascending within a window, and memory scales with
    // chunkEvents × specs × multiplicity — bounded by setChunkEvents(),
    // which replaced the original whole-file buffering.
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

        // Events buffered per read window. 0 = whole file (legacy behavior;
        // unbounded memory). Default keeps memory roughly
        // 200k × nSpecs × multiplicity × sizeof(Lorentz).
        void setChunkEvents(std::size_t n) { chunkEvents_ = n; }
        std::size_t chunkEvents() const { return chunkEvents_; }

        template<typename Callback>
        void run(Callback&& callback);

      private:
        using BufferT = std::vector<std::vector<std::vector<Lorentz>>>;

        template<typename Callback>
        void flushParallel(BufferT& buffer, Long64_t windowFirstKey,
                           std::size_t windowCount, Callback& callback);

        void readSpecInto(const EventParticleSpec& spec,
                          std::size_t specOrdinal,
                          BufferT& buffer,
                          Long64_t windowFirstKey,
                          std::size_t windowCount);

        bool                           configured_    = false;
        std::string                    inputFile_;
        std::vector<EventParticleSpec> specs_;
        std::size_t                    threadCount_   = 0;
        std::size_t                    eventCount_    = 0;
        std::size_t                    chunkEvents_   = 200000;
        Long64_t                       firstEventKey_ = 0;
        std::atomic<std::size_t>       consumed_{0};
    };

} // namespace Probe
