#pragma once

// ── ML/Features.hh ───────────────────────────────────────────────────────────
// The names of a model's inputs, and a row filled in by name rather than by position (05 §6).
//
// This exists because of one bug, which every project that feeds a network from an event loop
// writes at least once: the model was trained on `[pt, eta, phi, m]` and the module fills
// `[pt, phi, eta, m]`. Nothing throws. The tensor is the right width and the right type, the
// network is happy to evaluate it, and the answer is wrong in a way that looks like bad training.
//
// So a `Features` is an ordered list of names, `Row::set` takes one of those names, and
// `Row::values()` refuses to hand over a row that is not completely filled — an unset feature is a
// zero that means "no signal" and is indistinguishable from a real zero once it is in the tensor.
// `Features::matches(model)` closes the other half: the schema's size against the model's input
// width, checked once when the module starts.
//
// There is no ONNX here, on purpose. Features are built in a build with `HEKIT_WITH_ONNX` off
// exactly as they are with it on; only the call that consumes them goes away.

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

#include "Core/Errors.hh"
#include "ML/Types.hh"

namespace ML {

    class Row;

    /// An ordered, named schema. Build it once, next to the model it belongs to.
    class Features {
      public:
        Features() = default;
        explicit Features(std::vector<std::string> names) : names_(std::move(names)) {
            if (names_.empty())
                throw Core::Error{Core::Exit::Config, "a feature schema with no features"};
            std::vector<std::string> sorted = names_;
            std::sort(sorted.begin(), sorted.end());
            const auto duplicate = std::adjacent_find(sorted.begin(), sorted.end());
            if (duplicate != sorted.end())
                throw Core::Error{Core::Exit::Config,
                                  "the feature '" + *duplicate + "' is named twice",
                                  "a row is filled by name, so two features cannot share one"};
            for (const std::string& name : names_)
                if (name.empty())
                    throw Core::Error{Core::Exit::Config, "a feature with no name"};
        }

        std::size_t size() const { return names_.size(); }
        const std::vector<std::string>& names() const { return names_; }

        /// Where this feature sits in a row, or −1.
        int index(const std::string& name) const {
            for (std::size_t at = 0; at < names_.size(); ++at)
                if (names_[at] == name) return static_cast<int>(at);
            return -1;
        }

        /// A fresh, empty row of this schema.
        Row row() const;

        /// The schema against the model that will be fed it. Once, when the module starts.
        template <typename Model>
        void matches(const Model& model) const {
            if (model.features() != size())
                throw Core::Error{Core::Exit::Config,
                                  model.path() + " takes " + std::to_string(model.features()) +
                                      " features and this schema names " + std::to_string(size()),
                                  joined()};
        }

        std::string joined() const {
            std::string out;
            for (const std::string& name : names_) out += (out.empty() ? "" : ", ") + name;
            return out;
        }

      private:
        std::vector<std::string> names_;
    };

    /// One row of features, filled by name. Reuse one per worker: `clear` keeps the storage.
    class Row {
      public:
        explicit Row(const Features& schema)
            : schema_(&schema), values_(schema.size(), 0.0f), set_(schema.size(), 0) {}

        void set(const std::string& name, double value) {
            const int at = schema_->index(name);
            if (at < 0)
                throw Core::Error{Core::Exit::Config,
                                  "no feature called '" + name + "'", schema_->joined()};
            set(static_cast<std::size_t>(at), value);
        }

        void set(std::size_t index, double value) {
            if (index >= values_.size())
                throw Core::Error{Core::Exit::Internal,
                                  "feature " + std::to_string(index) + " is past the end of a row"};
            if (!std::isfinite(value))
                throw Core::Error{Core::Exit::Config,
                                  "the feature '" + schema_->names()[index] + "' is not finite",
                                  "a NaN or an infinity reaches the network as one and comes back "
                                  "as a plausible number"};
            values_[index] = static_cast<float>(value);
            set_[index] = 1;
        }

        /// Empty again, storage kept.
        void clear() { std::fill(set_.begin(), set_.end(), static_cast<char>(0)); }

        bool complete() const {
            return std::find(set_.begin(), set_.end(), static_cast<char>(0)) == set_.end();
        }

        /// The row, or a `Core::Error` naming what was left out. An unset feature is a zero that
        /// means "no signal", which is not what the caller meant and not what the model was trained
        /// on.
        Floats values() const {
            if (!complete()) {
                std::string missing;
                for (std::size_t at = 0; at < set_.size(); ++at)
                    if (set_[at] == 0)
                        missing += (missing.empty() ? "" : ", ") + schema_->names()[at];
                throw Core::Error{Core::Exit::Config, "these features were never set: " + missing};
            }
            return Floats{values_.data(), values_.size()};
        }

        const Features& schema() const { return *schema_; }

      private:
        const Features* schema_;
        std::vector<float> values_;
        std::vector<char> set_;
    };

    inline Row Features::row() const { return Row(*this); }

}  // namespace ML
