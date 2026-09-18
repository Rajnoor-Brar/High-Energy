#pragma once

// ── Sink/Types.hh ────────────────────────────────────────────────────────────
// What consumes events (05 §2). One interface, four implementations (Rivet, store, modules, Delphes),
// each arriving with its own step.
//
// Two things a sink declares up front, because the run loop has to know them before the first event:
//
//   * **what it needs** — a live Pythia instance, a `GenEvent`, or neither. A run whose sinks need no
//     HepMC never pays for the conversion (05 §1);
//   * **how it takes concurrency** — serial (called on the generation thread), locked (one mutex), or
//     sharded (one instance per worker). `auto` in the config resolves to serial unless every sink can
//     be sharded (05 §3).

#include <string>
#include <vector>

#include "Core/Types.hh"
#include "Core/Provenance.hh"   // RunRecord, named by finish()
#include "Events/Types.hh"

namespace Sink {

    enum class Concurrency {
        Serial,     // called on the callback thread, one event at a time
        Locked,     // may be called from several workers, but only under one mutex
        Sharded,    // one instance per worker, merged at the end
    };

    struct Needs {
        bool pythia = false;    // the live instance (Pythia-specific quantities)
        bool hepmc = false;     // a GenEvent (Rivet, the store, most modules)
    };

    // What a sink produced, for the summary and the terminal.
    struct Output {
        std::string kind;       // "yoda" | "store" | "delphes" | …
        std::string path;
        bool partial = false;
    };

    class Sink {
      public:
        virtual ~Sink() = default;

        virtual std::string name() const = 0;
        virtual Needs needs() const { return {}; }
        virtual Concurrency concurrency() const { return Concurrency::Serial; }

        // Before anything is generated, and before `start`: load what may not exist (a Rivet
        // analysis, a module library) so a typo costs a second rather than a whole run. `--check`
        // stops right after this, which is what makes it worth checking.
        virtual void prepare() {}

        // Once, before the first event, with everything the sink may need to book its objects.
        virtual void start(const Core::Beams& beams, long long expected_events) {
            (void)beams;
            (void)expected_events;
        }

        virtual void event(Events::View& view) = 0;

        // At a chunk boundary: a chance to write a partial result (00/B3, 00/B22 of the design).
        virtual void checkpoint(long long done) { (void)done; }

        // Once, after the last event, with how the run ended. A sink that writes files does it here,
        // under a temporary name and then renamed (D22).
        virtual void finish(const Core::RunRecord& record) { (void)record; }

        virtual std::vector<Output> outputs() const { return {}; }
    };

}  // namespace Sink
