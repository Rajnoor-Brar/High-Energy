#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include <toml++/toml.hpp>

#include "TColor.h"
#include "Paint/Types.hh"

namespace Paint {

    inline Color_t parseColor(const std::string& spec) {
        static const std::unordered_map<std::string, Color_t> kNamedColors = {
            {"kWhite",   kWhite},   {"kBlack",   kBlack},   {"kGray",    kGray},
            {"kRed",     kRed},     {"kGreen",   kGreen},   {"kBlue",    kBlue},
            {"kYellow",  kYellow},  {"kMagenta", kMagenta}, {"kCyan",    kCyan},
            {"kOrange",  kOrange},  {"kSpring",  kSpring},  {"kTeal",    kTeal},
            {"kAzure",   kAzure},   {"kViolet",  kViolet},  {"kPink",    kPink},
        };

        std::string s = spec;
        s.erase(std::remove_if(s.begin(), s.end(), [](unsigned char ch) {
            return std::isspace(ch);
        }), s.end());
        if (s.empty()) return kBlack;

        if (s[0] != 'k') {
            try { return static_cast<Color_t>(std::stoi(s)); }
            catch (...) { return kBlack; }
        }

        const std::size_t opPos = s.find_first_of("+-", 1);
        const std::string base = (opPos == std::string::npos) ? s : s.substr(0, opPos);
        int offset = 0;
        if (opPos != std::string::npos) {
            try { offset = std::stoi(s.substr(opPos)); }
            catch (...) { offset = 0; }
        }

        const auto it = kNamedColors.find(base);
        if (it == kNamedColors.end())
            throw std::runtime_error("unknown color token: '" + base + "' in '" + spec + "'");
        const int raw = it->second + offset;
        if (raw < std::numeric_limits<Color_t>::min() || raw > std::numeric_limits<Color_t>::max())
            throw std::runtime_error("color offset out of Color_t range: " + spec);
        return static_cast<Color_t>(raw);
    }

    namespace detail {

        inline const toml::table* asTable(const toml::node_view<const toml::node>& node) {
            return node ? node.as_table() : nullptr;
        }

        inline const toml::table* getTable(const toml::table& table, const std::string& key) {
            const toml::node* node = table.get(key);
            return node == nullptr ? nullptr : node->as_table();
        }

        inline bool hasKey(const toml::table& table, const std::string& key) {
            return table.get(key) != nullptr;
        }

        template <typename T>
        inline void readValue(const toml::table& table, const std::string& key, T& out) {
            const toml::node_view<const toml::node> node = table[key];
            if (!node) return;
            auto value = node.value<T>();
            if (!value)
                throw std::runtime_error("type mismatch for key '" + key + "'");
            out = *value;
        }

        inline void readString(const toml::table& table, const std::string& key, std::string& out) {
            const toml::node_view<const toml::node> node = table[key];
            if (!node) return;
            if (auto value = node.value<std::string>()) out = *value;
        }

        inline void readColor(const toml::table& table, const std::string& key, Color_t& out) {
            const toml::node_view<const toml::node> node = table[key];
            if (!node) return;
            if (node.is_string()) {
                out = parseColor(node.value<std::string>().value_or(""));
            } else if (node.is_integer()) {
                out = static_cast<Color_t>(node.value<int64_t>().value_or(out));
            }
        }

        inline std::vector<std::string> readStringArray(const toml::node_view<const toml::node>& node,
                                                        const std::vector<std::string>& fallback = {}) {
            const toml::array* array = node ? node.as_array() : nullptr;
            if (array == nullptr) return fallback;

            std::vector<std::string> values;
            values.reserve(array->size());
            for (const toml::node& item : *array) {
                if (const auto value = item.value<std::string>()) values.push_back(*value);
            }
            return values.empty() ? fallback : values;
        }

    } // namespace detail

    inline void mergeAxis(const toml::table& table, AxisSpec& axis) {
        detail::readString(table, "title_x", axis.titleX);
        detail::readString(table, "title_y", axis.titleY);
        detail::readString(table, "title_z", axis.titleZ);
        detail::readValue(table, "title_font", axis.titleFont);
        detail::readValue(table, "label_font", axis.labelFont);
        detail::readValue(table, "title_size", axis.titleSize);
        detail::readValue(table, "label_size", axis.labelSize);
        detail::readValue(table, "offset_x", axis.offsetX);
        detail::readValue(table, "offset_y", axis.offsetY);
        detail::readValue(table, "offset_z", axis.offsetZ);
        detail::readValue(table, "center_titles", axis.centerTitles);
        detail::readValue(table, "max_digits_y", axis.maxDigitsY);
    }

    inline void mergeCanvas(const toml::table& table, CanvasSpec& canvas) {
        detail::readValue(table, "width", canvas.width);
        detail::readValue(table, "height", canvas.height);
        detail::readValue(table, "margin_l", canvas.marginL);
        detail::readValue(table, "margin_r", canvas.marginR);
        detail::readValue(table, "margin_b", canvas.marginB);
        detail::readValue(table, "margin_t", canvas.marginT);
        detail::readValue(table, "ticks_x", canvas.ticksX);
        detail::readValue(table, "ticks_y", canvas.ticksY);
    }

    inline void mergeStats(const toml::table& table, StatsSpec& stats) {
        detail::readValue(table, "show", stats.show);
        detail::readString(table, "opt_stat", stats.optStat);
        detail::readValue(table, "x", stats.x);
        detail::readValue(table, "y", stats.y);
        detail::readValue(table, "width", stats.width);
        detail::readValue(table, "height", stats.height);
        detail::readValue(table, "text_font", stats.textFont);
        detail::readValue(table, "text_size", stats.textSize);
        detail::readValue(table, "border_size", stats.borderSize);
        detail::readColor(table, "fill_color", stats.fillColor);
        detail::readValue(table, "fill_style", stats.fillStyle);
    }

    inline void mergeLegend(const toml::table& table, LegendSpec& legend) {
        detail::readValue(table, "show", legend.show);
        detail::readValue(table, "x1", legend.x1);
        detail::readValue(table, "y1", legend.y1);
        detail::readValue(table, "x2", legend.x2);
        detail::readValue(table, "y2", legend.y2);
        detail::readValue(table, "text_font", legend.textFont);
        detail::readValue(table, "text_size", legend.textSize);
        detail::readValue(table, "border_size", legend.borderSize);
        detail::readValue(table, "fill_style", legend.fillStyle);
    }

    inline void mergeTitleBox(const toml::table& table, TitleBoxSpec& titleBox) {
        detail::readValue(table, "show", titleBox.show);
        detail::readValue(table, "text_font", titleBox.textFont);
        detail::readValue(table, "text_size", titleBox.textSize);
        detail::readValue(table, "border_size", titleBox.borderSize);
        detail::readValue(table, "fill_style", titleBox.fillStyle);
    }

    inline void mergeStyle(const toml::table& table, Style& style) {
        detail::readColor(table, "line_color", style.line.color);
        detail::readValue(table, "line_width", style.line.width);
        detail::readValue(table, "line_style", style.line.style);

        detail::readColor(table, "fill_color", style.fill.color);
        detail::readValue(table, "fill_style", style.fill.style);

        detail::readColor(table, "marker_color", style.marker.color);
        detail::readValue(table, "marker_style", style.marker.style);
        detail::readValue(table, "marker_size", style.marker.size);

        detail::readString(table, "draw_option", style.drawOption);
        if (detail::hasKey(table, "minimum")) {
            detail::readValue(table, "minimum", style.minimum);
            style.hasMinimum = true;
        }
        if (detail::hasKey(table, "maximum")) {
            detail::readValue(table, "maximum", style.maximum);
            style.hasMaximum = true;
        }

        detail::readValue(table, "log_x", style.logX);
        detail::readValue(table, "log_y", style.logY);
        detail::readValue(table, "log_z", style.logZ);
        detail::readValue(table, "grid_x", style.gridX);
        detail::readValue(table, "grid_y", style.gridY);

        if (const toml::table* axis = detail::getTable(table, "axis")) {
            mergeAxis(*axis, style.axis);
        }
        if (const toml::table* canvas = detail::getTable(table, "canvas")) {
            mergeCanvas(*canvas, style.canvas);
        }
        if (const toml::table* stats = detail::getTable(table, "stats")) {
            mergeStats(*stats, style.stats);
        }
        if (const toml::table* legend = detail::getTable(table, "legend")) {
            mergeLegend(*legend, style.legend);
        }
        if (const toml::table* titleBox = detail::getTable(table, "title_box")) {
            mergeTitleBox(*titleBox, style.titleBox);
        }
    }

    inline std::string modeName(Mode mode) {
        switch (mode) {
            case Mode::Single:  return "single";
            case Mode::Overlay: return "overlay";
            case Mode::Grid:    return "grid";
        }
        throw std::logic_error("Paint: unhandled Mode enum value");
    }

    inline Mode parseMode(const std::string& value, const std::string& context) {
        if (value == "single") return Mode::Single;
        if (value == "overlay") return Mode::Overlay;
        if (value == "grid") return Mode::Grid;
        throw std::runtime_error(context + ": invalid mode '" + value + "'");
    }

    inline std::string objectKindName(ObjectKind kind) {
        switch (kind) {
            case ObjectKind::Hist1D:    return "TH1";
            case ObjectKind::Hist2D:    return "TH2";
            case ObjectKind::TProfile:  return "TProfile";
            case ObjectKind::Graph:     return "TGraph";
        }
        throw std::logic_error("Paint: unhandled ObjectKind enum value");
    }

} // namespace Paint
