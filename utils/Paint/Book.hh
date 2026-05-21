#pragma once

#include <algorithm>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "Paint/Types.hh"
#include "Paint/Style.hh"

namespace Paint {

    inline constexpr const char* kDefaultStylePath = "configs/defaults/Paint.toml";

    namespace detail {

        inline void mergeTomlTables(toml::table& dst, const toml::table& src) {
            for (const auto& [key, value] : src) {
                const std::string k{key.str()};
                toml::node* existing = dst.get(k);
                if (existing != nullptr && existing->is_table() && value.is_table()) {
                    mergeTomlTables(*existing->as_table(), *value.as_table());
                } else {
                    dst.insert_or_assign(k, value);
                }
            }
        }

        inline std::string readDefaultStylePath(const toml::table& userConfig) {
            const toml::table* paint = getTable(userConfig, "paint");
            if (paint == nullptr) return kDefaultStylePath;
            return (*paint)["default_style"].value_or(std::string{kDefaultStylePath});
        }

        // parseBookConfig — mirrors Config::parseConfig for the Paint layer.
        // Returns a merged table when configPath is a directory of *.toml files,
        // or a single parsed table when it is a regular file.
        inline toml::table parseBookConfig(const std::string& configPath) {
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
                    "Paint config directory '" + configPath + "' contains no .toml files");

            std::sort(paths.begin(), paths.end());
            toml::table master;
            for (const auto& p : paths) {
                toml::table t = toml::parse_file(p);
                mergeTomlTables(master, t);
            }
            return master;
        }

    } // namespace detail

    inline PaintBook loadBook(const std::string& configPath) {
        namespace fs = std::filesystem;

        if (!fs::exists(configPath)) {
            throw std::runtime_error("Paint config does not exist: " + configPath);
        }

        toml::table userConfig = detail::parseBookConfig(configPath);
        const std::string defaultStylePath = detail::readDefaultStylePath(userConfig);

        toml::table merged;
        if (defaultStylePath.empty()) {
            // Opt-out: use the user config directly, without any defaults file.
            merged = userConfig;
        } else {
            if (!fs::exists(defaultStylePath)) {
                throw std::runtime_error("Paint default style does not exist: " + defaultStylePath);
            }
            merged = toml::parse_file(defaultStylePath);
            detail::mergeTomlTables(merged, userConfig);
        }

        if (detail::getTable(merged, "paint") == nullptr) {
            throw std::runtime_error("Paint config must contain a [paint] table");
        }

        PaintBook book;
        book.configPath = configPath;
        book.defaultStylePath = defaultStylePath;
        book.config = std::move(merged);
        return book;
    }

} // namespace Paint
