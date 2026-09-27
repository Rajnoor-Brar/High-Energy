#pragma once
// utils/Apps/Paint/Page.hh — one page's config, as the runner writes it (docs/rework_v2/05_Tools.md §7).
//
//     [page]    name, output (path without extension), formats, title, x_label, y_label, logx, logy,
//               y_gutter, x_gutter, ratio, ratio_label, void_empty, min_entries, auto_range, range_pad
//     [style]   what differs from utils/Apps/Paint/base.toml, in its tables (Style.hh)
//     [[curve]] file, object, raw (optional: the /RAW twin, for min_entries), label
//     [data]    file, object, label                       (optional: reference data)

#include "Style.hh"

#include <toml++/toml.hpp>

#include <stdexcept>
#include <string>
#include <vector>

namespace Paint {

    struct Source {
        std::string file, object, raw, label;
    };

    struct Page {
        std::string name, output, title, xLabel, yLabel, ratioLabel = "Ratio";
        std::vector<std::string> formats{"pdf"};
        bool logx = false, logy = false, ratio = false, voidEmpty = false, autoRange = true;
        double yGutter = 1.5, xGutter = 1.0;
        int minEntries = 0, rangePad = 0;
        Style style;
        std::vector<Source> curves;
        bool hasData = false;
        Source data;
    };

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
        page.xLabel = p["x_label"].value_or(std::string(""));
        page.yLabel = p["y_label"].value_or(std::string(""));
        page.ratioLabel = p["ratio_label"].value_or(page.ratioLabel);
        page.logx = p["logx"].value_or(false);
        page.logy = p["logy"].value_or(false);
        page.ratio = p["ratio"].value_or(false);
        page.voidEmpty = p["void_empty"].value_or(false);
        page.autoRange = p["auto_range"].value_or(true);
        page.yGutter = p["y_gutter"].value_or(1.5);
        page.xGutter = p["x_gutter"].value_or(1.0);
        page.minEntries = p["min_entries"].value_or(0);
        page.rangePad = p["range_pad"].value_or(0);
        page.style = readStyle(doc["style"].as_table());
        if (auto* curves = doc["curve"].as_array()) {
            for (auto& node : *curves) {
                const auto& c = *node.as_table();
                page.curves.push_back({c["file"].value_or(std::string("")), c["object"].value_or(std::string("")),
                                       c["raw"].value_or(std::string("")), c["label"].value_or(std::string(""))});
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
