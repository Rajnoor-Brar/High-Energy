#pragma once

#include <algorithm>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "Paint/Types.hh"
#include "Paint/Style.hh"
#include "Utility/Toml.hh"
#include "Utility/Paths.hh"

namespace Paint {

    inline constexpr const char* kDefaultStylePath = "configs/defaults/Paint.toml";

    namespace detail {

        inline std::string readDefaultStylePath(const toml::table& userConfig) {
            const toml::table* paint = getTable(userConfig, "paint");
            const std::string path = paint == nullptr
                ? std::string{kDefaultStylePath}
                : (*paint)["default_style"].value_or(std::string{kDefaultStylePath});
            if (path.empty()) return path;  // opt-out stays opt-out
            // Anchor to the project root so binaries launched outside the
            // repo root still find the defaults file.
            return Utility::Paths::resolveProjectPath(path);
        }

    } // namespace detail

    inline PaintBook loadBook(const std::string& configPath) {
        namespace fs = std::filesystem;

        if (!fs::exists(configPath)) {
            throw std::runtime_error("Paint config does not exist: " + configPath);
        }

        toml::table userConfig = Utility::Toml::parseConfigTable(configPath);
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
            Utility::Toml::mergeTables(merged, userConfig);
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
