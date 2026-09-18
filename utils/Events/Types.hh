#pragma once

// ── Events/Types.hh ──────────────────────────────────────────────────────────
// What a sink sees of one event (05 §1).
//
// The view is a *handle*, not a copy: it holds whatever the source has — a live `Pythia8::Pythia*`, or
// a `HepMC3::GenEvent` read from a store — and converts only when a sink actually asks. A run with no
// HepMC-consuming sink therefore never builds a `GenEvent`, which is the difference between the old
// FIFO pipeline and running the analysis in process (D4).
//
// The namespace is `Events`, plural, because Delphes declares a global `class Event`
// (`DelphesClasses.h:46`) and ROOT has opinions about `Event` too (13 §3).

#include <cstdint>
#include <string>
#include <vector>

namespace Pythia8 {
    class Pythia;
}

#if defined(HEKIT_WITH_HEPMC)
namespace HepMC3 {
    class GenEvent;
}
#endif

namespace Events {

    // What one event weighs and where it came from. Weights are a vector because Rivet supports
    // multi-weight events (`[rivet].weights = "all"`).
    struct Weights {
        std::vector<double> values{1.0};
        std::vector<std::string> names{"Weight"};

        double nominal() const { return values.empty() ? 1.0 : values.front(); }
    };

    class View {
      public:
        View() = default;

        // The live-Pythia case: the source owns the instance, the view only borrows it.
        View(Pythia8::Pythia* pythia, std::int64_t index, int worker)
            : pythia_(pythia), index_(index), worker_(worker) {}

        Pythia8::Pythia* pythia() const { return pythia_; }
        std::int64_t index() const { return index_; }
        int worker() const { return worker_; }
        const Weights& weights() const { return weights_; }
        Weights& weights() { return weights_; }

        bool hasPythia() const { return pythia_ != nullptr; }

#if defined(HEKIT_WITH_HEPMC)
        // Set by the source when it already has a GenEvent (store replay, a stream), or filled in
        // lazily by `Events::hepmc(view)` for a live Pythia event.
        void adoptHepMC(HepMC3::GenEvent* event) { hepmc_ = event; }
        HepMC3::GenEvent* hepmcOrNull() const { return hepmc_; }
#endif

      private:
        Pythia8::Pythia* pythia_ = nullptr;
        std::int64_t index_ = 0;
        int worker_ = 0;
        Weights weights_;
#if defined(HEKIT_WITH_HEPMC)
        HepMC3::GenEvent* hepmc_ = nullptr;
#endif
    };

}  // namespace Events
