#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
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
        if (it == kNamedColors.end()) return kBlack;
        return static_cast<Color_t>(it->second + offset);
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
            if (auto value = node.value<T>()) out = *value;
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

        inline void mergeAxis(const toml::table& table, AxisSpec& axis) {
            readString(table, "title_x", axis.titleX);
            readString(table, "title_y", axis.titleY);
            readString(table, "title_z", axis.titleZ);
            readValue(table, "title_font", axis.titleFont);
            readValue(table, "label_font", axis.labelFont);
            readValue(table, "title_size", axis.titleSize);
            readValue(table, "label_size", axis.labelSize);
            readValue(table, "offset_x", axis.offsetX);
            readValue(table, "offset_y", axis.offsetY);
            readValue(table, "offset_z", axis.offsetZ);
            readValue(table, "center_titles", axis.centerTitles);
            readValue(table, "max_digits_y", axis.maxDigitsY);
        }

        inline void mergeCanvas(const toml::table& table, CanvasSpec& canvas) {
            readValue(table, "width", canvas.width);
            readValue(table, "height", canvas.height);
            readValue(table, "margin_l", canvas.marginL);
            readValue(table, "margin_r", canvas.marginR);
            readValue(table, "margin_b", canvas.marginB);
            readValue(table, "margin_t", canvas.marginT);
            readValue(table, "ticks_x", canvas.ticksX);
            readValue(table, "ticks_y", canvas.ticksY);
        }

        inline void mergeStats(const toml::table& table, StatsSpec& stats) {
            readValue(table, "show", stats.show);
            readString(table, "opt_stat", stats.optStat);
            readValue(table, "x", stats.x);
            readValue(table, "y", stats.y);
            readValue(table, "width", stats.width);
            readValue(table, "height", stats.height);
            readValue(table, "text_font", stats.textFont);
            readValue(table, "text_size", stats.textSize);
            readValue(table, "border_size", stats.borderSize);
        }

        inline void mergeLegend(const toml::table& table, LegendSpec& legend) {
            readValue(table, "show", legend.show);
            readValue(table, "x1", legend.x1);
            readValue(table, "y1", legend.y1);
            readValue(table, "x2", legend.x2);
            readValue(table, "y2", legend.y2);
            readValue(table, "text_font", legend.textFont);
            readValue(table, "text_size", legend.textSize);
            readValue(table, "border_size", legend.borderSize);
            readValue(table, "fill_style", legend.fillStyle);
        }

        inline void mergeTitleBox(const toml::table& table, TitleBoxSpec& titleBox) {
            readValue(table, "show", titleBox.show);
            readValue(table, "text_font", titleBox.textFont);
            readValue(table, "text_size", titleBox.textSize);
            readValue(table, "border_size", titleBox.borderSize);
            readValue(table, "fill_style", titleBox.fillStyle);
        }

    } // namespace detail

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
            style.hasMaximum = std::abs(style.maximum) > 0.0;
        }

        detail::readValue(table, "log_x", style.logX);
        detail::readValue(table, "log_y", style.logY);
        detail::readValue(table, "log_z", style.logZ);
        detail::readValue(table, "grid_x", style.gridX);
        detail::readValue(table, "grid_y", style.gridY);

        if (const toml::table* axis = detail::getTable(table, "axis")) {
            detail::mergeAxis(*axis, style.axis);
        }
        if (const toml::table* canvas = detail::getTable(table, "canvas")) {
            detail::mergeCanvas(*canvas, style.canvas);
        }
        if (const toml::table* stats = detail::getTable(table, "stats")) {
            detail::mergeStats(*stats, style.stats);
        }
        if (const toml::table* legend = detail::getTable(table, "legend")) {
            detail::mergeLegend(*legend, style.legend);
        }
        if (const toml::table* titleBox = detail::getTable(table, "title_box")) {
            detail::mergeTitleBox(*titleBox, style.titleBox);
        }
    }

    inline std::string modeName(Mode mode) {
        switch (mode) {
            case Mode::Single:  return "single";
            case Mode::Overlay: return "overlay";
            case Mode::Grid:    return "grid";
        }
        return "single";
    }

    inline Mode parseMode(const std::string& value, const std::string& context) {
        if (value == "single") return Mode::Single;
        if (value == "overlay") return Mode::Overlay;
        if (value == "grid") return Mode::Grid;
        throw std::runtime_error(context + ": invalid mode '" + value + "'");
    }

    inline std::string objectKindName(ObjectKind kind) {
        switch (kind) {
            case ObjectKind::Hist1D: return "TH1";
            case ObjectKind::Hist2D: return "TH2";
            case ObjectKind::Graph:  return "TGraph";
        }
        return "unknown";
    }

} // namespace Paint
