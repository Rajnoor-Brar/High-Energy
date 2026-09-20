#pragma once

// ── Core/Types.hh ────────────────────────────────────────────────────────────
// The few types other namespaces need from Core. Keeping them here means a higher layer can include
// `Core/Types.hh` alone rather than the whole facade (house style, 13 §1).

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "Core/Errors.hh"

namespace Core {

    // How a run ended, in the form the summary and the terminal both want.
    struct Outcome {
        Exit exit = Exit::Ok;
        std::string message;
        bool stopped = false;
    };

    // Beams, as every adapter and sink needs them (03 §1: ids and energies are separate).
    struct Beams {
        std::vector<int> ids;                    // PDG, [A, B]
        std::vector<double> energies;            // GeV, [E_A, E_B]; one entry means √s
        double sqrtS = 0.0;                      // filled in by the source once it knows

        bool centreOfMass() const { return energies.size() == 1; }
    };

    // Counted the way P0-S04 found Pythia counts: attempts are not successes.
    struct Counts {
        long long attempted = 0;
        long long accepted = 0;
        long long written = 0;

        double acceptance() const {
            return attempted > 0 ? static_cast<double>(accepted) / static_cast<double>(attempted) : 0.0;
        }
    };


    /// Free-form options a user's module is configured with (`[[sinks.module]].options`, 05 §5).
    ///
    /// Everything arrives as text, because the spec is TOML and a module's options are whatever that
    /// module invented. The typed readers say what was expected when a value is not that, which is
    /// the difference between "ptmin is not a number" and a silent zero.
    class Options {
      public:
        void set(const std::string& key, const std::string& value) { values_[key] = value; }
        bool has(const std::string& key) const { return values_.count(key) != 0; }

        std::string text(const std::string& key, const std::string& fallback = "") const {
            const auto found = values_.find(key);
            return found == values_.end() ? fallback : found->second;
        }

        double number(const std::string& key, double fallback = 0.0) const {
            const auto found = values_.find(key);
            if (found == values_.end()) return fallback;
            try {
                return std::stod(found->second);
            } catch (const std::exception&) {
                throw Error{Exit::Config, "module option " + key + " is not a number: " +
                                              found->second};
            }
        }

        long long integer(const std::string& key, long long fallback = 0) const {
            const auto found = values_.find(key);
            if (found == values_.end()) return fallback;
            try {
                return std::stoll(found->second);
            } catch (const std::exception&) {
                throw Error{Exit::Config, "module option " + key + " is not an integer: " +
                                              found->second};
            }
        }

        bool flag(const std::string& key, bool fallback = false) const {
            const auto found = values_.find(key);
            if (found == values_.end()) return fallback;
            const std::string& value = found->second;
            if (value == "true" || value == "on" || value == "1") return true;
            if (value == "false" || value == "off" || value == "0") return false;
            throw Error{Exit::Config, "module option " + key + " is not true or false: " + value};
        }

        const std::map<std::string, std::string>& all() const { return values_; }

      private:
        std::map<std::string, std::string> values_;
    };

}  // namespace Core
