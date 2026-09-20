#pragma once

// ── Results/Merge.hh ─────────────────────────────────────────────────────────
// Adding the workers' clones together, and the one place scaling is allowed (05 §5).
//
// The merge is addition, and that is not an implementation detail — it is the contract that makes a
// sharded run give the same answer as a serial one. Every object a module can book is fillable, and
// fills add, so k workers' clones sum to what one worker would have had. P6-S01 found the other half
// of this rule the hard way: an object that is `set` rather than filled cannot be merged at all, and
// no amount of care in the merge can fix it.
//
// `Final` is the only type here that can scale, and it is only reachable from `Module::finalize`,
// which runs once, after the merge, with σ and ΣW known. That is the scaling contract of 05 §5
// written as a type rather than as a comment: during the event loop a module *has* no scale(), so
// "scaled twice" and "scaled by a σ that was not final yet" are not mistakes it can make.

#include <string>
#include <vector>

#include "Core/Errors.hh"
#include "Results/Booker.hh"
#include "Results/Worker.hh"

namespace Results {

    /// Add `other` into `into`, slot by slot. Both must come from the same `Booker`.
    inline void merge(std::vector<Slot>& into, const std::vector<Slot>& other) {
        if (into.size() != other.size())
            throw Core::Error{Core::Exit::Internal,
                              "two module workers hold different numbers of objects (" +
                                  std::to_string(into.size()) + " and " +
                                  std::to_string(other.size()) + ")"};
        for (std::size_t index = 0; index < into.size(); ++index) {
            Slot& target = into[index];
            const Slot& source = other[index];
            if (target.kind != source.kind)
                throw Core::Error{Core::Exit::Internal,
                                  "two module workers disagree about what object " +
                                      std::to_string(index) + " is"};
            switch (target.kind) {
                case Kind::Histo1D:   *target.histo1d   += *source.histo1d;   break;
                case Kind::Histo2D:   *target.histo2d   += *source.histo2d;   break;
                case Kind::Profile1D: *target.profile1d += *source.profile1d; break;
                case Kind::Counter:   *target.counter   += *source.counter;   break;
            }
        }
    }

    /// What a module is given in `finalize()`: the merged objects, the numbers that were not known
    /// before, and the only verb that can change a result after the fact.
    class Final {
      public:
        Final(std::vector<Slot>& slots, double xsec_pb, double sum_of_weights, long long events)
            : slots_(slots), xsec_pb_(xsec_pb), sum_of_weights_(sum_of_weights), events_(events) {}

        /// The run's cross-section in pb, as the run measured it (D-Q1).
        double crossSection() const { return xsec_pb_; }

        /// Σw over every event the run kept — the denominator of a normalisation.
        double sumOfWeights() const { return sum_of_weights_; }

        long long events() const { return events_; }

        /// σ / Σw: the factor that turns a weight sum into a cross-section. The common case, spelled
        /// out so every module does not spell it differently.
        double perEventCrossSection() const {
            return sum_of_weights_ > 0.0 ? xsec_pb_ / sum_of_weights_ : 0.0;
        }

        /// Multiply an object's contents. The only way to change a result after the merge.
        void scale(Handle handle, double factor) {
            Slot& slot = at(handle);
            switch (slot.kind) {
                case Kind::Histo1D:   slot.histo1d->scaleW(factor);   return;
                case Kind::Histo2D:   slot.histo2d->scaleW(factor);   return;
                case Kind::Profile1D: slot.profile1d->scaleW(factor); return;
                case Kind::Counter:   slot.counter->scaleW(factor);   return;
            }
        }

        /// `scale(handle, perEventCrossSection())`, which is what "normalise to σ" means.
        void normalise(Handle handle) { scale(handle, perEventCrossSection()); }

        /// For a module that needs the object itself — a derived quantity, say. Borrowed, not owned.
        YODA::AnalysisObject* object(Handle handle) { return at(handle).object(); }

      private:
        Slot& at(Handle handle) {
            if (handle >= slots_.size())
                throw Core::Error{Core::Exit::Internal,
                                  "a module finalized an object it never booked (handle " +
                                      std::to_string(handle) + ")"};
            return slots_[handle];
        }

        std::vector<Slot>& slots_;
        double xsec_pb_ = 0.0;
        double sum_of_weights_ = 0.0;
        long long events_ = 0;
    };

}  // namespace Results
