#pragma once

// ── Events/Convert.hh ────────────────────────────────────────────────────────
// Pythia → HepMC3, on demand and once per event (05 §1).
//
// `Pythia8ToHepMC` is the conversion Rivet's own examples use, and the one the legacy `generator.cc`
// used to write the FIFO, so in-process analysis sees exactly the events the old pipeline did (D4).
// The converter is stateful, so each worker owns one: sharing one across threads is how you get two
// events interleaved in the same `GenEvent`.

#include <memory>

#include "Pythia8/Pythia.h"
#include "Pythia8Plugins/HepMC3.h"

#include "Core/Errors.hh"
#include "Events/Types.hh"

namespace Events {

    class Converter {
      public:
        // One converter per worker. No output file: this fills a GenEvent in memory.
        Converter() : bridge_(std::make_unique<Pythia8::Pythia8ToHepMC>()) {}

        // Fill (and own) the GenEvent for this view, then hand it over. Returns nullptr when the
        // conversion fails, which the caller reports as a source error rather than silently skipping.
        HepMC3::GenEvent* fill(View& view) {
            if (!view.hasPythia()) return view.hepmcOrNull();
            if (!bridge_->fillNextEvent(*view.pythia())) return nullptr;
            event_ = bridge_->getEventPtr();
            view.adoptHepMC(event_.get());
            return event_.get();
        }

        const std::shared_ptr<HepMC3::GenEvent>& last() const { return event_; }

      private:
        std::unique_ptr<Pythia8::Pythia8ToHepMC> bridge_;
        std::shared_ptr<HepMC3::GenEvent> event_;
    };

    // The GenEvent of a view, converting a live Pythia event if needed.
    inline HepMC3::GenEvent* hepmc(View& view, Converter& converter) {
        if (HepMC3::GenEvent* existing = view.hepmcOrNull()) return existing;
        HepMC3::GenEvent* filled = converter.fill(view);
        if (filled == nullptr)
            throw Core::Error{Core::Exit::Source, "HepMC3 conversion failed for event " +
                                                      std::to_string(view.index())};
        return filled;
    }

}  // namespace Events
