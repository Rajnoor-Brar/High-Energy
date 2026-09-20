#pragma once

// ── Module/Types.hh ──────────────────────────────────────────────────────────
// What a user's C++ analysis module implements (05 §5).
//
// Four verbs, in the order they happen, and each one is given exactly what it may use at that moment:
//
//   configure(Options)      — the `[[sinks.module]].options` from the config, before anything else;
//   book(Booker)            — declare the YODA objects, once, before the first event;
//   process(View, Worker)   — fill *this worker's* clones, with raw weights;
//   finalize(Final, Result) — after the merge, with σ and ΣW known: the only place scaling happens.
//
// That split is the scaling contract of 05 §5 expressed as types rather than as a rule to remember:
// a `Worker` has no `scale()` and a `Final` has no `fill()`, so "scaled during the run" and "filled
// after the merge" are not mistakes a module can make. `legacy/utils/Record` allowed both and wrote
// unscaled finals as a result (00 §4.1).
//
// A module is compiled into its own shared library and loaded with `dlopen` (`Module/Loader.hh`), so
// adding one never rebuilds `hep-run` — the same arrangement Rivet plugins have.

#include <string>

#include "Core/Types.hh"
#include "Events/Types.hh"
#include "Results/Booker.hh"
#include "Results/Merge.hh"
#include "Results/Worker.hh"
#include "Sink/Types.hh"

namespace Run {
    struct Result;
}

namespace Module {

    class Base {
      public:
        virtual ~Base() = default;

        /// `[[sinks.module]].options`. Called once, before `book`.
        virtual void configure(const Core::Options& options) { (void)options; }

        /// Declare every object this module will fill. Once, before any event.
        virtual void book(Results::Booker& booker) = 0;

        /// One event, into this worker's own clones. Raw weights only — see the header note.
        virtual void process(Events::View& view, Results::Worker& worker) = 0;

        /// After the merge, with σ and ΣW known. The only place `scale` exists.
        virtual void finalize(Results::Final& results) { (void)results; }

        /// What this module needs of an event. HepMC by default, which is what a replay can give.
        virtual Sink::Needs needs() const { return Sink::Needs{/*pythia=*/false, /*hepmc=*/true}; }

        /// May `process` be called from several worker threads at once?
        ///
        /// True by default, which is true of a module that only reads the event and fills its own
        /// worker's clones — that is the whole reason the module sink is the one sink that shards.
        ///
        /// **Say false if you cluster jets.** `Phys::cluster` and everything else built on FastJet
        /// keeps state in process-wide statics — SISCone its clustering cache and its RNG, and this
        /// FastJet is built without even limited thread safety (00/B31). A race there does not
        /// crash; it changes the jets. Say false too for anything else shared: a file, a network
        /// handle, a lazily built lookup table. The sink then runs every module under one mutex
        /// rather than forcing the whole run serial, so generation stays parallel.
        virtual bool threadSafe() const { return true; }
    };

}  // namespace Module
