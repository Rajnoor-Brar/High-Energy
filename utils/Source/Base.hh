#pragma once

// ── Source/Base.hh ───────────────────────────────────────────────────────────
// What the run loop needs of a source, and nothing more (05 §1, 11 §4).
//
// There are two kinds of source and they have almost nothing in common inside: `Source::Pythia`
// generates events and owns a cross section it measures; `Source::Replay` reads events somebody else
// generated and takes σ from the store's index. What the loop needs from both is the same short list
// — configure, initialise, tell me the beams and the seeds, give me events in chunks, tell me σ and
// what you warned about — so that is the interface, and the loop knows nothing else.
//
// The chunked `run()` shape comes from the generator side (D-Q2: a chunk is where a run can be
// stopped, checkpointed and dumped) and a replay honours it for the same reason: it is where Ctrl-C
// takes effect.

#include <cstdint>
#include <functional>
#include <string>
#include <utility>
#include <vector>

#include "Core/Provenance.hh"
#include "Core/Types.hh"
#include "Events/Types.hh"
#include "Source/Types.hh"

namespace Status {
    class Writer;
}

namespace Source {

    class Base {
      public:
        virtual ~Base() = default;

        /// Read cards, open files — everything before the point of no return.
        virtual void configure() = 0;

        /// The expensive, failure-prone step: `Pythia::init()`, or opening a store's shards.
        virtual void initialise() = 0;

        virtual const Core::Beams& beams() const = 0;
        virtual int threads() const = 0;

        /// The seeds the instances really have (a replay has none, and says so with an empty list).
        virtual std::vector<std::int64_t> instanceSeeds() = 0;

        /// The chunk actually used, given what was asked for (D-Q2).
        virtual std::int64_t chunkSize(std::int64_t wanted) const = 0;

        /// Ask for the analyzers to be called from several threads (05 §3). Called after `configure()`
        /// and before `initialise()`, because both sources have to set it up before the expensive
        /// step. A source that will not do it simply keeps `slots() == 1`, and the run stays serial.
        virtual void async(bool on) { (void)on; }

        /// How many consumer slots events will arrive on. 1 unless `async(true)` was accepted, and
        /// the number a `Sharded` analyzer builds instances for. Valid after `initialise()`.
        virtual int slots() const { return 1; }

        /// Produce up to `target` events, calling `consume` for each, asking `stop` between chunks.
        virtual Core::Counts run(std::int64_t target, std::int64_t chunk,
                                 const std::function<void(Events::View&)>& consume,
                                 const std::function<bool()>& stop,
                                 const std::function<void(std::int64_t)>& checkpoint = {}) = 0;

        /// σ ± err in pb. A generator measures it; a replay reads it from the index (11 §4).
        virtual Xsec xsec() = 0;

        /// Cumulative events per worker, adding up to what the loop has seen (06 §3).
        virtual const std::vector<long long>& workers() const = 0;

        /// Report new warnings to the status stream; called at checkpoints and at the end.
        virtual void reportWarnings(Status::Writer& status) = 0;

        /// The same warnings as counts, for the run summary (07 §2).
        virtual std::vector<std::pair<std::string, long long>> warningCounts() = 0;

        /// What this source is, for the status stream and the summary.
        virtual std::string kind() const = 0;
    };

}  // namespace Source
