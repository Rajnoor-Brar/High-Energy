#pragma once

#include <filesystem>
#include <stdexcept>
#include <string>

#include <toml++/toml.hpp>

#include "Paint/Types.hh"
#include "Paint/Style.hh"

namespace Paint {

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
            if (paint == nullptr) return "configs/defaults/Paint.toml";
            return (*paint)["default_style"].value_or(std::string{"configs/defaults/Paint.toml"});
        }

    } // namespace detail

    inline PaintBook loadBook(const std::string& configPath) {
        namespace fs = std::filesystem;

        if (!fs::exists(configPath)) {
            throw std::runtime_error("Paint config does not exist: " + configPath);
        }

        toml::table userConfig = toml::parse_file(configPath);
        const std::string defaultStylePath = detail::readDefaultStylePath(userConfig);
        if (!fs::exists(defaultStylePath)) {
            throw std::runtime_error("Paint default style does not exist: " + defaultStylePath);
        }

        toml::table merged = toml::parse_file(defaultStylePath);
        detail::mergeTomlTables(merged, userConfig);

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
