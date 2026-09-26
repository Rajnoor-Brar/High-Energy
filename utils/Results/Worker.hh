#pragma once

// ── Results/Worker.hh ────────────────────────────────────────────────────────
// One worker's own copy of everything a module booked (05 §5).
//
// `Analyzer::Modules` is sharded, so each slot fills its own clones and nothing is shared or locked
// during the event loop. That is the whole reason this type exists: a module with one set of
// objects would need a mutex per fill, and a mutex per fill is the thing sharding was for.
//
// **The scaling contract lives here, by omission.** A `Worker` can only *fill*, with the event's own
// weight; it has no `scale`. Scaling needs σ and ΣW, neither of which is known until the last event,
// so it belongs in `finalize` (`Results::Final`) and nowhere else. `legacy/Record` let both happen
// anywhere and produced unscaled finals as a result (00 §4.1).
//
// It is also the rule P6-S01 arrived at from the other direction: **`fill` merges, `set` does not.**
// Every object here is a fillable one, so k workers' clones add up to what one worker would have
// had — which is what makes the sharded answer equal the serial one.

#include <memory>
#include <string>
#include <vector>

#include "YODA/Counter.h"
#include "YODA/Histo.h"
#include "YODA/Profile.h"

#include "Core/Errors.hh"
#include "Results/Booker.hh"

namespace Results {

    /// One booked object, as one worker holds it. Exactly one pointer is non-null; the kind says
    /// which, so filling never needs a `dynamic_cast`.
    struct Slot {
        Kind kind = Kind::Counter;
        std::unique_ptr<YODA::Histo1D> histo1d;
        std::unique_ptr<YODA::Histo2D> histo2d;
        std::unique_ptr<YODA::Profile1D> profile1d;
        std::unique_ptr<YODA::Counter> counter;

        YODA::AnalysisObject* object() const {
            switch (kind) {
                case Kind::Histo1D:   return histo1d.get();
                case Kind::Histo2D:   return histo2d.get();
                case Kind::Profile1D: return profile1d.get();
                case Kind::Counter:   return counter.get();
            }
            return nullptr;                                   // unreachable; keeps compilers quiet
        }
    };

    /// Build one set of objects from what was booked. Called once per worker, before any event.
    inline std::vector<Slot> clonesOf(const Booker& booker) {
        std::vector<Slot> slots;
        slots.reserve(booker.declarations().size());
        for (const Declaration& declared : booker.declarations()) {
            const std::string path = booker.path(declared);
            Slot slot;
            slot.kind = declared.kind;
            switch (declared.kind) {
                case Kind::Histo1D:
                    slot.histo1d = std::make_unique<YODA::Histo1D>(
                        declared.bins_x, declared.low_x, declared.high_x, path, declared.title);
                    break;
                case Kind::Histo2D:
                    slot.histo2d = std::make_unique<YODA::Histo2D>(
                        declared.bins_x, declared.low_x, declared.high_x,
                        declared.bins_y, declared.low_y, declared.high_y, path, declared.title);
                    break;
                case Kind::Profile1D:
                    slot.profile1d = std::make_unique<YODA::Profile1D>(
                        declared.bins_x, declared.low_x, declared.high_x, path, declared.title);
                    break;
                case Kind::Counter:
                    slot.counter = std::make_unique<YODA::Counter>(path, declared.title);
                    break;
            }
            slots.push_back(std::move(slot));
        }
        return slots;
    }

    /// What a module is given in `process()`: its own objects, and only the verbs that make sense
    /// during an event.
    class Worker {
      public:
        Worker(std::vector<Slot>& slots, int slot_index)
            : slots_(slots), index_(slot_index) {}

        /// A 1D histogram, or a counter's weight when the module calls it that way.
        void fill(Handle handle, double x, double weight = 1.0) {
            Slot& slot = at(handle);
            switch (slot.kind) {
                case Kind::Histo1D: slot.histo1d->fill(x, weight); return;
                case Kind::Counter: slot.counter->fill(x); return;   // x *is* the weight here
                default:
                    throw Core::Error{Core::Exit::Internal,
                                      "module object " + name(handle) + " needs two coordinates"};
            }
        }

        /// A 2D histogram or a profile — the same call, because both take (x, y, weight).
        void fill(Handle handle, double x, double y, double weight) {
            Slot& slot = at(handle);
            switch (slot.kind) {
                case Kind::Histo2D:   slot.histo2d->fill(x, y, weight); return;
                case Kind::Profile1D: slot.profile1d->fill(x, y, weight); return;
                default:
                    throw Core::Error{Core::Exit::Internal,
                                      "module object " + name(handle) + " takes one coordinate"};
            }
        }

        /// A counter, said plainly.
        void count(Handle handle, double weight = 1.0) {
            Slot& slot = at(handle);
            if (slot.kind != Kind::Counter)
                throw Core::Error{Core::Exit::Internal,
                                  "module object " + name(handle) + " is not a counter"};
            slot.counter->fill(weight);
        }

        /// Which worker this is, for a module that wants to know (it almost never should).
        int slot() const { return index_; }

      private:
        Slot& at(Handle handle) {
            if (handle >= slots_.size())
                throw Core::Error{Core::Exit::Internal,
                                  "a module filled an object it never booked (handle " +
                                      std::to_string(handle) + ")"};
            return slots_[handle];
        }

        std::string name(Handle handle) const {
            const YODA::AnalysisObject* object =
                handle < slots_.size() ? slots_[handle].object() : nullptr;
            return object != nullptr ? object->path() : std::to_string(handle);
        }

        std::vector<Slot>& slots_;
        int index_ = 0;
    };

}  // namespace Results
