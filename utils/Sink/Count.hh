#pragma once

// ── Sink/Count.hh ────────────────────────────────────────────────────────────
// The sink that consumes nothing. It exists for three real uses, not as a placeholder:
//
//   * `hep-run` with no sinks at all (a generation-only benchmark, P6-S03);
//   * `--list N`, where the events are inspected rather than analysed (06 §5);
//   * the equivalence gate's generation-only leg (P2-S06).
//
// It also documents the interface by implementing the smallest possible sink.

#include <cstdint>
#include <string>
#include <vector>

#include "Sink/Types.hh"

namespace Sink {

    class Count : public Sink {
      public:
        std::string name() const override { return "count"; }

        Needs needs() const override { return {}; }
        Concurrency concurrency() const override { return Concurrency::Serial; }

        void event(Events::View& view) override {
            events_ += 1;
            weight_ += view.weights().nominal();
        }

        std::int64_t events() const { return events_; }
        double weight() const { return weight_; }

      private:
        std::int64_t events_ = 0;
        double weight_ = 0.0;
    };

}  // namespace Sink
