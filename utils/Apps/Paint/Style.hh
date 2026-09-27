#pragma once
// utils/Apps/Paint/Style.hh — a page's style: base.toml, with the page's [style] merged over it.
//
// base.toml (beside this file) is the one place a default lives. Paint finds it from its own
// executable (build/Paint.exe → ../utils/Apps/Paint/base.toml), else under $HEKIT_ROOT. A page's
// [style] names only what it changes, in base.toml's tables; a key base.toml does not have, or a
// value of another type, is an error. `legend.position` is a corner name or [x, y].

#include <toml++/toml.hpp>

#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <tuple>
#include <utility>
#include <vector>

namespace Paint {

    struct Style {
        double width = 0, height = 0;                    // [page], inches
        int dpi = 0;
        std::string font;
        double left = 0, right = 0, top = 0, bottom = 0;  // [page.margins], fractions of the page
        double title = 0, labels = 0, legend = 0, header = 0;   // [text], points
        std::vector<std::string> palette;                // [curves]
        double lineWidth = 0;
        std::string errors;
        std::string dataColour;                          // [data]
        int marker = 20;
        double markerSize = 0;
        bool xBars = true;
        double tick = 0, titleOffsetX = 0, titleOffsetY = 0, labelOffset = 0;   // [axes]
        bool allSides = true, atEnds = true;
        std::string corner;                              // [legend]: a corner, or placed at [x, y]
        bool placed = false;
        double atX = 0, atY = 0, insetX = 0, insetY = 0, spacing = 0, symbol = 0, gap = 0;
        double mainHeight = 0, ratioHeight = 0, rangeLo = 0, rangeHi = 0, limitLo = 0, limitHi = 0;   // [ratio]
        int divisions = 0;
        bool decimals = true;
        toml::table merged;                              // what --dump-style prints

        double px() const { return dpi / 72.0; }         // pixels per point
        int pixelsWide() const { return static_cast<int>(std::lround(width * dpi)); }
        int pixelsHigh() const { return static_cast<int>(std::lround(height * dpi)); }
        int fontCode() const { return font == "sans" ? 43 : font == "mono" ? 83 : 133; }   // precision 3: pixels
    };

    namespace detail {

        inline bool numeric(const toml::node& n) { return n.is_integer() || n.is_floating_point(); }

        inline void merge(toml::table& base, const toml::table& over, const std::string& where) {
            for (auto&& [key, value] : over) {
                const std::string name = where.empty() ? std::string(key.str()) : where + "." + std::string(key.str());
                toml::node* mine = base.get(key);
                if (!mine) throw std::runtime_error("[style] has no key '" + name + "' (utils/Apps/Paint/base.toml lists them)");
                if (mine->is_table() && value.is_table()) {
                    merge(*mine->as_table(), *value.as_table(), name);
                    continue;
                }
                const bool same = !mine->is_table() && !value.is_table() &&
                                  (mine->type() == value.type() || (numeric(*mine) && numeric(value)) ||
                                   (name == "legend.position" && (value.is_string() || value.is_array())));
                if (!same) throw std::runtime_error("[style]." + name + " is not of the type base.toml gives it");
                value.visit([&](auto&& v) { base.insert_or_assign(key, v); });
            }
        }

        inline const toml::node& at(const toml::table& t, const std::string& path) {
            const toml::node* n = t.at_path(path).node();
            if (!n) throw std::runtime_error("the style has no " + path + " (base.toml is incomplete)");
            return *n;
        }
        inline double number(const toml::table& t, const std::string& path) {
            const auto v = at(t, path).value<double>();
            if (!v) throw std::runtime_error("[style]." + path + " must be a number");
            return *v;
        }
        inline std::string text(const toml::table& t, const std::string& path) {
            const auto v = at(t, path).value<std::string>();
            if (!v) throw std::runtime_error("[style]." + path + " must be a string");
            return *v;
        }
        inline bool flag(const toml::table& t, const std::string& path) {
            const auto v = at(t, path).value<bool>();
            if (!v) throw std::runtime_error("[style]." + path + " must be true or false");
            return *v;
        }
        inline std::pair<double, double> pair(const toml::node& n, const std::string& path) {
            const auto* a = n.as_array();
            if (!a || a->size() != 2 || !(*a)[0].value<double>() || !(*a)[1].value<double>())
                throw std::runtime_error("[style]." + path + " must be two numbers");
            return {*(*a)[0].value<double>(), *(*a)[1].value<double>()};
        }
        inline void oneOf(const std::string& value, const std::vector<std::string>& allowed, const std::string& path) {
            for (const auto& a : allowed)
                if (value == a) return;
            std::string list;
            for (const auto& a : allowed) list += (list.empty() ? "" : ", ") + a;
            throw std::runtime_error("[style]." + path + " must be one of " + list + ", not '" + value + "'");
        }

    }  // namespace detail

    inline std::filesystem::path basePath() {
        namespace fs = std::filesystem;
        const fs::path rel = fs::path("utils") / "Apps" / "Paint" / "base.toml";
        std::error_code ec;
        const fs::path exe = fs::canonical("/proc/self/exe", ec);
        if (!ec && fs::exists(exe.parent_path().parent_path() / rel)) return exe.parent_path().parent_path() / rel;
        if (const char* root = std::getenv("HEKIT_ROOT"); root && fs::exists(fs::path(root) / rel)) return fs::path(root) / rel;
        throw std::runtime_error("cannot find utils/Apps/Paint/base.toml (beside build/, or under $HEKIT_ROOT)");
    }

    inline Style readStyle(const toml::table* over) {
        using namespace detail;
        const std::string path = basePath().string();
        toml::table t;
        try {
            t = toml::parse_file(path);
        } catch (const toml::parse_error& error) {
            throw std::runtime_error("cannot parse " + path + ": " + std::string(error.description()));
        }
        if (over) merge(t, *over, "");
        Style s;
        s.merged = t;
        std::tie(s.width, s.height) = pair(at(t, "page.size"), "page.size");
        s.dpi = static_cast<int>(number(t, "page.dpi"));
        s.font = text(t, "page.font");
        oneOf(s.font, {"serif", "sans", "mono"}, "page.font");
        s.left = number(t, "page.margins.left"), s.right = number(t, "page.margins.right");
        s.top = number(t, "page.margins.top"), s.bottom = number(t, "page.margins.bottom");
        s.title = number(t, "text.title"), s.labels = number(t, "text.labels");
        s.legend = number(t, "text.legend"), s.header = number(t, "text.header");
        if (const auto* palette = at(t, "curves.palette").as_array())
            for (const auto& c : *palette) {
                if (auto name = c.value<std::string>()) s.palette.push_back(*name);
                else if (auto number = c.value<int64_t>()) s.palette.push_back(std::to_string(*number));
            }
        if (s.palette.empty()) throw std::runtime_error("[style].curves.palette must name at least one colour");
        s.lineWidth = number(t, "curves.width");
        s.errors = text(t, "curves.errors");
        oneOf(s.errors, {"bars", "band", "none"}, "curves.errors");
        s.dataColour = text(t, "data.colour");
        s.marker = static_cast<int>(number(t, "data.marker"));
        s.markerSize = number(t, "data.marker_size");
        s.xBars = flag(t, "data.x_bars");
        s.tick = number(t, "axes.tick_length");
        s.allSides = flag(t, "axes.ticks_all_sides");
        s.atEnds = flag(t, "axes.titles_at_ends");
        std::tie(s.titleOffsetX, s.titleOffsetY) = pair(at(t, "axes.title_offset"), "axes.title_offset");
        s.labelOffset = number(t, "axes.label_offset");
        const toml::node& position = at(t, "legend.position");
        if (position.is_array()) {
            std::tie(s.atX, s.atY) = pair(position, "legend.position");
            s.placed = true, s.corner = "top-right";
        } else {
            s.corner = text(t, "legend.position");
            oneOf(s.corner, {"top-right", "top-left", "bottom-right", "bottom-left"}, "legend.position");
        }
        std::tie(s.insetX, s.insetY) = pair(at(t, "legend.inset"), "legend.inset");
        s.spacing = number(t, "legend.spacing"), s.symbol = number(t, "legend.symbol"), s.gap = number(t, "legend.gap");
        std::tie(s.mainHeight, s.ratioHeight) = pair(at(t, "ratio.heights"), "ratio.heights");
        std::tie(s.rangeLo, s.rangeHi) = pair(at(t, "ratio.range"), "ratio.range");
        std::tie(s.limitLo, s.limitHi) = pair(at(t, "ratio.limits"), "ratio.limits");
        s.divisions = static_cast<int>(number(t, "ratio.divisions"));
        s.decimals = flag(t, "ratio.decimals");
        if (s.dpi <= 0 || s.width <= 0 || s.height <= 0) throw std::runtime_error("[style].page: size and dpi must be positive");
        if (s.mainHeight <= 0 || s.ratioHeight <= 0) throw std::runtime_error("[style].ratio.heights must be positive");
        return s;
    }

}  // namespace Paint
