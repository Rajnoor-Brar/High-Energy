#pragma once
// utils/Apps/Paint/Page.hh — one page's config, as the runner writes it (docs/05_Tools_Reference.md §17).
//
//     [page]    name, output (path without extension), formats, title, x_label, y_label, logx, logy,
//               y_gutter, x_gutter, ratio, ratio_label, void_empty, min_entries, auto_range, range_pad
//     [style]   what differs from utils/Apps/Paint/base.toml, in its tables (Style.hh)
//     [[curve]] file, object, raw (optional: the /RAW twin, for min_entries), label
//     [data]    file, object, label                       (optional: reference data)

#include "Style.hh"

#include <toml++/toml.hpp>

#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace Paint {

    struct Source {
        std::string file, object, raw, label;
        std::string colour, line;            // a curve's own (V67: a quantity value's style); "": the style's
        double width = 0;                    // points; 0: the style's
        std::vector<Source> band;            // V69: the members whose envelope is drawn around this curve
    };

    struct Page {
        std::string name, output, xLabel, yLabel, ratioLabel = "Ratio";
        std::string title, titleLeft, titleRight, legendHeader;   // above the frame: centred, its corners; the legend's first line
        std::vector<std::string> formats{"pdf"};
        // A key the page leaves out is what ROOT does by itself (V55): no gutter, no auto range, no voiding.
        // The runner writes every key it sets (its defaults are utils/Env/schema/run.toml's), so Paint keeps none.
        bool logx = false, logy = false, ratio = false, voidEmpty = false, autoRange = false;
        bool normalise = false;                                 // "area": unit area over the bins drawn (V68)
        bool markers = false;                                   // the curves as markers, as data (type Scatter2D, V86)
        std::optional<double> yGutter, xGutter;                 // none: ROOT's own range ("default")
        int minEntries = 0, rangePad = 0;
        Style style;
        std::vector<Source> curves;
        bool hasData = false;
        Source data;
    };

    // y_gutter / x_gutter: a number ≥ 0 (0: the axis ends at the largest value, V55), or "default": none,
    // ROOT's own range.
    inline std::optional<double> gutter(toml::node_view<toml::node> node, const std::string& key,
                                        std::optional<double> fallback) {
        if (!node) return fallback;
        if (const auto text = node.value<std::string>()) {
            if (*text == "default") return std::nullopt;
        } else if (const auto value = node.value<double>(); value && *value >= 0) {
            return *value;
        }
        throw std::runtime_error("[page]." + key + " must be a number >= 0 or \"default\"");
    }

    inline Page readPage(const std::string& path) {
        toml::table doc;
        try {
            doc = toml::parse_file(path);
        } catch (const toml::parse_error& error) {
            throw std::runtime_error("cannot parse " + path + ": " + std::string(error.description()));
        }
        Page page;
        const auto& p = doc["page"];
        page.name = p["name"].value_or(std::string("page"));
        page.output = p["output"].value_or(std::string(""));
        if (page.output.empty()) throw std::runtime_error(path + ": [page].output is required");
        if (auto* formats = p["formats"].as_array()) {
            page.formats.clear();
            for (auto& f : *formats) page.formats.push_back(f.value_or(std::string("pdf")));
        }
        page.title = p["title"].value_or(std::string(""));
        page.titleLeft = p["title_left"].value_or(std::string(""));
        page.titleRight = p["title_right"].value_or(std::string(""));
        page.legendHeader = p["legend_header"].value_or(std::string(""));
        page.xLabel = p["x_label"].value_or(std::string(""));
        page.yLabel = p["y_label"].value_or(std::string(""));
        page.ratioLabel = p["ratio_label"].value_or(page.ratioLabel);
        page.logx = p["logx"].value_or(false);
        page.logy = p["logy"].value_or(false);
        page.ratio = p["ratio"].value_or(false);
        page.voidEmpty = p["void_empty"].value_or(false);
        page.autoRange = p["auto_range"].value_or(false);
        page.markers = p["markers"].value_or(false);
        if (const auto node = p["normalise"]; node) {
            if (node.value<std::string>() == std::optional<std::string>("area")) page.normalise = true;
            else if (node.value<bool>() != std::optional<bool>(false))
                throw std::runtime_error(path + ": [page].normalise must be \"area\" or false");
        }
        page.yGutter = gutter(p["y_gutter"], "y_gutter", page.yGutter);
        page.xGutter = gutter(p["x_gutter"], "x_gutter", page.xGutter);
        page.minEntries = p["min_entries"].value_or(0);
        page.rangePad = p["range_pad"].value_or(0);
        page.style = readStyle(doc["style"].as_table());
        if (auto* curves = doc["curve"].as_array()) {
            for (auto& node : *curves) {
                const auto& c = *node.as_table();
                Source source{c["file"].value_or(std::string("")), c["object"].value_or(std::string("")),
                              c["raw"].value_or(std::string("")), c["label"].value_or(std::string(""))};
                if (const auto* look = c["style"].as_table()) {
                    source.colour = (*look)["colour"].value_or(std::string(""));
                    if (const auto number = (*look)["colour"].value<int64_t>()) source.colour = std::to_string(*number);
                    source.line = (*look)["line"].value_or(std::string(""));
                    source.width = (*look)["width"].value_or(0.0);
                    if (!source.line.empty() && source.line != "solid" && source.line != "dashed" &&
                        source.line != "dotted" && source.line != "dashdot")
                        throw std::runtime_error(path + ": a curve's style.line must be solid, dashed, dotted or dashdot");
                }
                if (const auto* members = c["band"].as_array())
                    for (const auto& m : *members)
                        if (const auto* t = m.as_table())
                            source.band.push_back({(*t)["file"].value_or(std::string("")), (*t)["object"].value_or(std::string("")),
                                                   (*t)["raw"].value_or(std::string("")), ""});
                page.curves.push_back(source);
            }
        }
        if (page.curves.empty()) throw std::runtime_error(path + ": a page needs at least one [[curve]]");
        if (auto* data = doc["data"].as_table()) {
            page.hasData = true;
            page.data = {(*data)["file"].value_or(std::string("")), (*data)["object"].value_or(std::string("")), "",
                         (*data)["label"].value_or(std::string("Data"))};
        }
        return page;
    }

}  // namespace Paint
