#pragma once

// ── Utility/Toml.hh ───────────────────────────────────────────────────────────
// Shared TOML helpers used by Config and Paint (previously duplicated):
//
//   mergeTables       — recursive table merge (later keys overwrite earlier)
//   parseConfigTable  — file OR directory-of-*.toml loader with merge
//   requirePositive / requireNonNegative — numeric config validation
// ─────────────────────────────────────────────────────────────────────────────

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

namespace Utility::Toml {

    // mergeTables — recursive TOML table merge (src into dst).
    // Sub-tables are merged key-by-key; all other node types overwrite.
    // Arrays are replaced wholesale (not element-merged) so that
    //   results = ["a","b"]  in a later file replaces  results = ["x"]
    // from an earlier file.
    inline void mergeTables(toml::table& dst, const toml::table& src) {
        for (const auto& [key, val] : src) {
            const std::string k{key.str()};
            toml::node* existing = dst.get(k);
            if (existing && existing->is_table() && val.is_table())
                mergeTables(*existing->as_table(), *val.as_table());
            else
                dst.insert_or_assign(k, val);
        }
    }

    // parseConfigTable — unified config loader used instead of bare
    // toml::parse_file().
    //
    // If configPath is a regular file: equivalent to toml::parse_file(configPath).
    //
    // If configPath is a directory: reads every *.toml file in the directory
    // (non-recursive, alphabetical by filename) and merges them left-to-right
    // into a single master table, so splitting a config across files works
    // naturally and later files override earlier ones.
    inline toml::table parseConfigTable(const std::string& configPath) {
        namespace fs = std::filesystem;
        if (!fs::is_directory(configPath))
            return toml::parse_file(configPath);

        std::vector<std::string> paths;
        for (const auto& entry : fs::directory_iterator(configPath)) {
            if (entry.is_regular_file() && entry.path().extension() == ".toml")
                paths.push_back(entry.path().string());
        }

        if (paths.empty())
            throw std::runtime_error(
                "[Toml] directory '" + configPath + "' contains no .toml files");

        std::sort(paths.begin(), paths.end());

        toml::table master;
        for (const auto& p : paths) {
            toml::table t = toml::parse_file(p);
            mergeTables(master, t);
        }
        return master;
    }

    // requirePositive / requireNonNegative — reject physically invalid
    // numeric config values at parse time, before a size_t cast wraps a
    // negative into ~1.8e19 or ROOT crashes on a 0-bin histogram.
    inline std::int64_t requirePositive(std::int64_t value, const char* key) {
        if (value <= 0)
            throw std::runtime_error(std::string("[Config] '") + key +
                                     "' must be > 0 (got " + std::to_string(value) + ")");
        return value;
    }
    inline std::int64_t requireNonNegative(std::int64_t value, const char* key) {
        if (value < 0)
            throw std::runtime_error(std::string("[Config] '") + key +
                                     "' must be >= 0 (got " + std::to_string(value) + ")");
        return value;
    }
    inline double requirePositive(double value, const char* key) {
        if (!(value > 0.0))
            throw std::runtime_error(std::string("[Config] '") + key +
                                     "' must be > 0 (got " + std::to_string(value) + ")");
        return value;
    }

} // namespace Utility::Toml
