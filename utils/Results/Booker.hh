#pragma once

// ── Results/Booker.hh ────────────────────────────────────────────────────────
// What a module declares before the first event (05 §5).
//
// Booking is separate from filling for the same reason Rivet separates them: it is the only moment
// when every object is known and nothing has happened yet, so it is the only moment when a mistake is
// cheap. A duplicate name, an empty name, a histogram with no bins or with its edges the wrong way
// round are all caught here — before a run, not after one.
//
// A module gets back a **handle**, not a pointer. Three reasons, and the third is the important one:
//
//   1. a handle is an index, so filling costs an array lookup rather than a map lookup or a
//      `dynamic_cast`;
//   2. the module never owns an object, so it cannot keep one across a merge and be surprised;
//   3. **there is one object per worker, not one object.** `Analyzer::Modules` is sharded (05 §3), so a
//      module that held a pointer would be holding one of k clones and filling only that one. A
//      handle names "the thing I booked", and which clone that is depends on which worker is asking.
//
// This is `legacy/utils/Record/Declaration.hh`'s idea, kept, with its defects left behind: Record
// validated at fill time and could write unscaled finals (00 §4.1).

#include <string>
#include <vector>

#include "Core/Errors.hh"

namespace Results {

    /// An index into a worker's objects. Cheap to copy, meaningless outside its module.
    using Handle = std::size_t;

    enum class Kind { Histo1D, Histo2D, Profile1D, Counter };

    /// One declared object, in the form both the booker and every worker's clone need.
    struct Declaration {
        Kind kind = Kind::Counter;
        std::string name;
        std::string title;
        std::size_t bins_x = 0;
        double low_x = 0.0;
        double high_x = 0.0;
        std::size_t bins_y = 0;
        double low_y = 0.0;
        double high_y = 0.0;
    };

    class Booker {
      public:
        /// `prefix` is the module's namespace in the YODA file: `/<module>` (07 §1).
        explicit Booker(std::string prefix) : prefix_(std::move(prefix)) {}

        Handle histo1D(const std::string& name, std::size_t bins, double low, double high,
                       const std::string& title = "") {
            Declaration declared;
            declared.kind = Kind::Histo1D;
            declared.name = name;
            declared.title = title;
            declared.bins_x = bins;
            declared.low_x = low;
            declared.high_x = high;
            return add(declared);
        }

        Handle histo2D(const std::string& name, std::size_t bins_x, double low_x, double high_x,
                       std::size_t bins_y, double low_y, double high_y,
                       const std::string& title = "") {
            Declaration declared;
            declared.kind = Kind::Histo2D;
            declared.name = name;
            declared.title = title;
            declared.bins_x = bins_x;
            declared.low_x = low_x;
            declared.high_x = high_x;
            declared.bins_y = bins_y;
            declared.low_y = low_y;
            declared.high_y = high_y;
            return add(declared);
        }

        Handle profile1D(const std::string& name, std::size_t bins, double low, double high,
                         const std::string& title = "") {
            Declaration declared;
            declared.kind = Kind::Profile1D;
            declared.name = name;
            declared.title = title;
            declared.bins_x = bins;
            declared.low_x = low;
            declared.high_x = high;
            return add(declared);
        }

        Handle counter(const std::string& name, const std::string& title = "") {
            Declaration declared;
            declared.kind = Kind::Counter;
            declared.name = name;
            declared.title = title;
            return add(declared);
        }

        const std::vector<Declaration>& declarations() const { return declared_; }
        const std::string& prefix() const { return prefix_; }

        /// `/<module>/<name>`, which is where it lands in `analysis.yoda` (07 §1).
        std::string path(const Declaration& declared) const {
            return prefix_ + "/" + declared.name;
        }

      private:
        Handle add(const Declaration& declared) {
            check(declared);
            declared_.push_back(declared);
            return declared_.size() - 1;
        }

        // Everything that can be known now. A run is minutes; a typo found afterwards costs all of
        // them, and a histogram with reversed edges silently keeps nothing.
        void check(const Declaration& declared) const {
            if (declared.name.empty())
                throw Core::Error{Core::Exit::Config,
                                  "a module booked an object with no name",
                                  "it becomes a path in analysis.yoda, so it needs one"};
            if (declared.name.find('/') != std::string::npos)
                throw Core::Error{Core::Exit::Config,
                                  "the module object '" + declared.name + "' has a '/' in its name",
                                  "the module's own prefix supplies that"};
            for (const Declaration& existing : declared_)
                if (existing.name == declared.name)
                    throw Core::Error{Core::Exit::Config,
                                      "the module booked '" + declared.name + "' twice",
                                      "two objects cannot share a path; the second would overwrite "
                                      "the first in the YODA"};
            if (declared.kind == Kind::Counter) return;
            requireAxis(declared.name, "x", declared.bins_x, declared.low_x, declared.high_x);
            if (declared.kind == Kind::Histo2D)
                requireAxis(declared.name, "y", declared.bins_y, declared.low_y, declared.high_y);
        }

        static void requireAxis(const std::string& name, const std::string& axis,
                                std::size_t bins, double low, double high) {
            if (bins == 0)
                throw Core::Error{Core::Exit::Config,
                                  "the module object '" + name + "' has no " + axis + " bins"};
            if (!(high > low))
                throw Core::Error{Core::Exit::Config,
                                  "the module object '" + name + "' has " + axis + " edges the wrong "
                                  "way round (" + std::to_string(low) + " to " +
                                      std::to_string(high) + ")",
                                  "low must be below high; an inverted range keeps nothing"};
        }

        std::string prefix_;
        std::vector<Declaration> declared_;
    };

}  // namespace Results
