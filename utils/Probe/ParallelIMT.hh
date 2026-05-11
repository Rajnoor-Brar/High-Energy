#pragma once

// ── Probe/ParallelIMT.hh ─────────────────────────────────────────────────────
// ProbeIMT — `TTreeProcessorMT`-based read path for multi-tree inputs.
//
// Phase 2 of docs/ROOTMT.md.  Sibling to ProbeParallel with the same public
// interface (drop-in substitution at the driver site).  Spike (2026-05-11)
// measured 5.3× wall-time speed-up at 8 threads on the 10M-event Lambda
// input, breaking the ~150% CPU floor that the manual-thread path hits.
//
// Algorithm — Option 2 (full-buffer two-pass, per docs/ROOTMT.md choice):
//   1. Allocate a per-event buffer indexed by (event_index - firstKey),
//      with one inner vector per ParticleSpec.
//   2. For each ParticleSpec, run TTreeProcessorMT in parallel.  Each task
//      builds a thread-local map (event_index → vector<Lorentz>), then
//      hands it off to the orchestrator under a lock.  After Process()
//      joins, the orchestrator merges all task buffers into the per-event
//      buffer single-threaded (cheap; the costly part was decompression).
//   3. Serial flush: walk the per-event buffer, construct an Event for
//      each slot, call the user callback.
//
// Memory cost (10M events, 4 protons + 5 pions per event, 32-byte Lorentz):
//   - Per-event skeleton buffer: ~500 MB
//   - Particle data:             ~3 GB peak after both passes
//   - Task-local buffers:        ~500 MB transient during each spec read
//   Total peak: ~4 GB.  Acceptable on the target hardware (16+ GB).
//
// Caveats:
//   - Flush is serial today.  If the user callback (mass cut + TH1::Fill via
//     Writer queue) becomes the bottleneck, parallelise via TThreadExecutor.
//   - Within an event, particle order across thread-boundaries is NOT
//     preserved.  Reconstruction code that does all-vs-all pairing (our
//     case) is unaffected.  If a "leading particle" convention is needed,
//     tag entries with their tree-row index and sort after merge.
//   - Vector-stream specs (no indexBranches) are NOT supported in IMT mode.
//     Falls through to a clear error at configureProbe time.
//
// Driver substitution:
//     Probe::ProbeIMT probe;            // was: Probe::ProbeParallel
//     Config::configure(...);            // unchanged (template overload)
//     probe.run([&](const Event&, int){ ... });
// ─────────────────────────────────────────────────────────────────────────────

#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <iostream>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <vector>

#include "TChain.h"
#include "TROOT.h"
#include "TTreeReader.h"
#include "ROOT/TTreeProcessorMT.hxx"

#include "Config.hh"
#include "Probe/BranchControl.hh"
#include "Probe/Event.hh"
#include "Probe/EventCount.hh"
#include "Probe/EventReaderMT.hh"
#include "Probe/Types.hh"

namespace Probe {

    class ProbeIMT {
      public:
        ProbeIMT() = default;

        // Same shape as ProbeParallel::configureProbe.  Shard-related args
        // are accepted for interface parity and ignored (IMT doesn't need
        // per-worker file shards — TTreeProcessorMT does cluster-aware
        // partitioning internally).
        void configureProbe(std::string inputFile,
                            std::vector<ParticleSpec> particleSpecs,
                            std::size_t threadCount,
                            std::size_t requestedEvents,
                            bool userRequestedEvents,
                            bool        /*splitInput*/     = false,
                            std::string /*tempSpace*/      = "",
                            bool        /*keepShards*/     = false,
                            std::string /*shardKeyPrefix*/ = "")
        {
            BranchControl::enableRootThreadSafety();

            inputFile_     = std::move(inputFile);
            specs_         = std::move(particleSpecs);
            threadCount_   = Config::resolveThreadCount(threadCount);
            configured_    = false;
            eventCount_    = 0;
            firstEventKey_ = 0;

            if (inputFile_.empty())
                throw std::runtime_error("[Probe::IMT] empty input file");
            if (specs_.empty())
                throw std::runtime_error("[Probe::IMT] no particle specs");
            if (threadCount_ == 0)
                throw std::runtime_error("[Probe::IMT] thread count is zero");

            for (const auto& s : specs_) {
                if (s.indexBranches.empty())
                    throw std::runtime_error(
                        "[Probe::IMT] vector-stream specs not supported in IMT "
                        "mode (spec '" + s.label + "' has no index branch)");
            }

            if (userRequestedEvents) eventCount_ = requestedEvents;
            else                     eventCount_ = Probe::resolveEventCount(inputFile_);

            if (eventCount_ == 0) {
                configured_ = true;
                return;
            }

            firstEventKey_ = BranchControl::probeFirstKey(inputFile_, specs_);
            configured_    = true;
        }

        const std::string& inputFile() const { return inputFile_; }
        std::size_t threadCount()    const { return threadCount_; }
        std::size_t eventCount()     const { return eventCount_; }
        StreamType  streamType()     const { return StreamType::Events; }

        std::string stats() const {
            std::ostringstream out;
            out << "ProbeIMT{streamType=Events"
                << ", threadCount=" << threadCount_
                << ", eventCount="  << eventCount_
                << ", firstKey="    << firstEventKey_
                << ", consumed="    << consumed_.load()
                << "}";
            return out.str();
        }

        template<typename Callback>
        void run(Callback&& callback) {
            if (!configured_)
                throw std::runtime_error("[Probe::IMT] run() before configureProbe");
            if (eventCount_ == 0) return;

            ROOT::EnableImplicitMT(static_cast<UInt_t>(threadCount_));
            consumed_ = 0;

            using clk = std::chrono::steady_clock;
            const auto t0 = clk::now();

            // ── allocate buffer ───────────────────────────────────────────
            // buffer[eventOffset][specOrdinal] = vector<Lorentz>
            BufferT buffer(eventCount_,
                           std::vector<std::vector<Lorentz>>(specs_.size()));

            const auto t1 = clk::now();

            // ── parallel reads, one spec at a time ────────────────────────
            for (std::size_t p = 0; p < specs_.size(); ++p)
                readSpecInto(specs_[p], p, buffer);

            const auto t2 = clk::now();

            // ── parallel flush ────────────────────────────────────────────
            // Distribute event slots across threadCount_ workers.  Each
            // worker constructs the Event, moves the buffered particles in,
            // and invokes the user callback with a stable workerIndex.
            //
            // Every spec.label is created in ev.particles unconditionally —
            // matches EventStream/ProbeParallel semantics so user callbacks
            // can ev["protons"] / ev.n("protons") even when an event has no
            // particles of that kind.
            flushParallel(buffer, std::forward<Callback>(callback));

            const auto t3 = clk::now();

            auto ms = [](auto a, auto b) {
                return std::chrono::duration_cast<std::chrono::milliseconds>(b - a).count();
            };
            std::cerr << "[Probe::IMT] timing (ms): allocate=" << ms(t0, t1)
                      << " read=" << ms(t1, t2)
                      << " flush=" << ms(t2, t3)
                      << " total=" << ms(t0, t3)
                      << " (eventCount=" << eventCount_
                      << ", threads=" << threadCount_ << ")\n";
        }

      private:
        // [eventOffset][specOrdinal] -> particles
        using BufferT = std::vector<std::vector<std::vector<Lorentz>>>;

        // ── parallel flush ────────────────────────────────────────────────
        // Distribute event slots across threadCount_ std::thread workers.
        // Each worker handles a contiguous slice [start, end) of the buffer,
        // builds an Event per slot, invokes the user callback with its
        // worker index, and atomically increments consumed_.
        //
        // Caveat: the user callback MUST be safe to invoke concurrently from
        // multiple threads with distinct worker indices.  This matches the
        // semantics of ProbeParallel's CallbackMode::WorkerThread mode.
        template<typename Callback>
        void flushParallel(BufferT& buffer, Callback&& callback) {
            const std::size_t T = threadCount_;
            std::vector<std::thread>        workers;
            std::vector<std::exception_ptr> errors(T);
            workers.reserve(T);

            for (std::size_t t = 0; t < T; ++t) {
                workers.emplace_back([&, t]() {
                    try {
                        const std::size_t start = (t * eventCount_) / T;
                        const std::size_t end   = ((t + 1) * eventCount_) / T;
                        for (std::size_t i = start; i < end; ++i) {
                            Event ev;
                            ev.index = firstEventKey_ + Long64_t(i);
                            for (std::size_t p = 0; p < specs_.size(); ++p)
                                ev.particles[specs_[p].label] =
                                    std::move(buffer[i][p]);
                            callback(ev, static_cast<int>(t));
                            consumed_.fetch_add(1, std::memory_order_relaxed);
                        }
                    } catch (...) {
                        errors[t] = std::current_exception();
                    }
                });
            }

            for (auto& w : workers) w.join();
            for (const auto& e : errors)
                if (e) std::rethrow_exception(e);
        }

        // One IMT pass over one tree.  Task-local partial buffers protect
        // against cluster-boundary races where two tasks touch the same
        // event_index; merge is single-threaded after Process() joins.
        //
        // Range filtering is done INSIDE the read loop, not at merge time:
        //   - K < first  : skip (entry belongs to events before our range)
        //   - K > last   : break out of task (sorted data — nothing more
        //                  in range within this cluster)
        //   - K in range : accumulate into local map
        //
        // Without this filter, a 100k-event request on a 10M-event input
        // (88 GB) would buffer all 304 M proton entries into task-local
        // maps before the merge check runs — guaranteed OOM.  The break
        // on `K > last` also short-circuits clusters that lie entirely
        // past our range, so we only pay basket decompression for the
        // actual slice we need (plus at most one out-of-range entry per
        // straddling cluster).  Assumes the index branch is sorted
        // ascending; documented in [probe.index] of the user config.
        void readSpecInto(const ParticleSpec& spec,
                          std::size_t         specOrdinal,
                          BufferT&            buffer)
        {
            using PartialMap = std::unordered_map<Long64_t, std::vector<Lorentz>>;

            const Long64_t first = firstEventKey_;
            const Long64_t last  = first + Long64_t(eventCount_) - 1;

            std::mutex                               collectMutex;
            std::vector<std::unique_ptr<PartialMap>> collected;

            TChain chain(spec.tree.c_str());
            chain.Add(inputFile_.c_str());

            ROOT::TTreeProcessorMT processor(chain);
            processor.Process([&](TTreeReader& reader) {
                EventReaderMT er(reader, spec);
                auto local = std::make_unique<PartialMap>();

                Long64_t K = 0;
                Lorentz  p;
                while (er.readOne(reader, K, p)) {
                    if (K > last)   break;       // past our range: short-circuit
                    if (K < first)  continue;    // before our range
                    (*local)[K].push_back(p);
                }

                std::lock_guard<std::mutex> lock(collectMutex);
                collected.push_back(std::move(local));
            });

            // ── single-threaded merge ─────────────────────────────────────
            // All entries in `collected` are already in-range (filtered
            // above).  No bounds check needed here, just merge.
            for (auto& partial : collected) {
                for (auto& [K, particles] : *partial) {
                    auto& target = buffer[std::size_t(K - first)][specOrdinal];
                    target.insert(target.end(),
                                  std::make_move_iterator(particles.begin()),
                                  std::make_move_iterator(particles.end()));
                }
            }
        }

        bool                       configured_    = false;
        std::string                inputFile_;
        std::vector<ParticleSpec>  specs_;
        std::size_t                threadCount_   = 0;
        std::size_t                eventCount_    = 0;
        Long64_t                   firstEventKey_ = 0;
        std::atomic<std::size_t>   consumed_{0};
    };

} // namespace Probe
