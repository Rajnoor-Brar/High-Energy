// utils/Apps/Paint/main.cc — the ROOT plotting app (docs/05_Tools_Reference.md §17).
// requires: root toml
//
//     Paint.exe PAGE.toml [PAGE.toml …] [--ranges | --ranges-only]
//     Paint.exe PAGE.toml --dump-ranges
//     Paint.exe [PAGE.toml] --dump-style
//
// Each page in the order v1 found load-bearing: load → void → align data → auto-range → gutters →
// draw → save. Many pages are drawn in one process (V64: ROOT starts once, not once per page), and
// with more than one page every page's outcome is a JSON line on stdout, {"page": …, "ok": …,
// "error": …}, so one bad page does not stop the rest. `--ranges` also writes each page's final
// ranges and voided bins beside its config, <PAGE>.ranges.json, for the other backends; `--ranges-only`
// writes them and draws nothing (a run whose only backend is yoda).
// `--dump-ranges` prints one page's ranges as JSON and draws nothing, which is how the arithmetic is
// tested without looking at pixels. `--dump-style` prints the page's style — utils/Apps/Paint/base.toml
// with the page's [style] over it — as TOML; with no page, base.toml's.
// Exit codes (02 §11): 0 ok, 1 page config, 2 usage, 4 input, 5 output (with several pages: 1 when any
// failed).

#include "Status.hh"

#include "Draw.hh"
#include "Page.hh"
#include "Transform.hh"

#include <cstdio>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

namespace {

    struct Outcome {
        int code = 0;
        std::string error;
    };

    std::string rangesJson(const Paint::Page& page, const std::vector<bool>& mask, const Paint::Range& x,
                           const Paint::YRange& y, bool haveData, const Paint::Series& data) {
        std::string voided;
        for (size_t i = 0; i < mask.size(); ++i)
            if (mask[i]) voided += (voided.empty() ? "" : ", ") + std::to_string(i + 1);
        // x_tool / y_tool: the range is the drawing tool's own choice, which another backend may make itself
        const bool xTool = !page.xGutter && !page.autoRange;
        char buffer[512];
        std::snprintf(buffer, sizeof buffer,
                      "{\"x\": [%.10g, %.10g], \"y\": [%.10g, %.10g], \"largest\": %.10g, \"voided\": [%s], "
                      "\"data_bins\": %zu, \"data_x\": [%.10g, %.10g], \"x_tool\": %s, \"y_tool\": %s}",
                      x.lo, x.hi, y.lo, y.hi, y.largest, voided.c_str(), haveData ? data.size() : 0,
                      haveData ? data.lo.front() : 0.0, haveData ? data.hi.back() : 0.0, xTool ? "true" : "false",
                      y.tool ? "true" : "false");
        return buffer;
    }

    // One page: its ranges printed (dump), written beside it (ranges) and/or the page drawn.
    Outcome one(const std::string& pagePath, bool dump, bool ranges, bool drawIt, Status::Reporter& status) {
        Paint::Page page;
        try {
            page = Paint::readPage(pagePath);
        } catch (const std::exception& error) {
            return {1, error.what()};
        }
        std::vector<Paint::Series> curves;
        Paint::Series data;
        bool haveData = false;
        try {
            for (const auto& source : page.curves) curves.push_back(Paint::load(source, false));
            if (page.hasData) data = Paint::load(page.data, true), haveData = true;
        } catch (const std::exception& error) {
            return {4, error.what()};
        }

        // void, across the page
        const std::vector<bool> mask = Paint::voidMask(curves, page.voidEmpty, page.minEntries);
        if ((page.voidEmpty || page.minEntries > 0) && mask.empty() && curves.size() > 1)
            status.log("warn", page.name + ": curves differ in binning; nothing voided");
        Paint::applyVoid(curves, mask);

        // align the reference data to the MC edges, or drop it
        if (haveData && !Paint::alignTo(data, curves.front())) {
            status.log("warn", page.name + ": no reference bin lines up with the MC binning; data dropped");
            haveData = false;
        }

        // ranges
        std::vector<const Paint::Series*> all;
        for (const auto& c : curves) all.push_back(&c);
        if (haveData) all.push_back(&data);
        Paint::Range x = page.autoRange ? Paint::autoRange(all, page.rangePad) : Paint::fullRange(all);
        if (!std::isfinite(x.lo) || !std::isfinite(x.hi)) x = Paint::fullRange(all);
        x = Paint::xWithGutter(x, page.xGutter, page.logx);
        const Paint::YRange y = Paint::yRange(all, x, page.yGutter, page.logy);

        const std::string json = rangesJson(page, mask, x, y, haveData, data);
        if (dump) {
            std::printf("%s\n", json.c_str());
            return {};
        }
        if (ranges) {
            std::ofstream out(pagePath + ".ranges.json");
            out << json << "\n";
            if (!out) return {5, "cannot write " + pagePath + ".ranges.json"};
        }
        if (!drawIt) return {};
        try {
            Paint::draw(page, curves, haveData ? &data : nullptr, x, y);
        } catch (const std::exception& error) {
            return {5, error.what()};
        }
        status.summary("\"page\": " + Status::quote(page.name) + ", \"formats\": " + std::to_string(page.formats.size()));
        return {};
    }

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> pages;
    bool dump = false, dumpStyle = false, ranges = false, drawIt = true, bad = false;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--dump-ranges") dump = true;
        else if (arg == "--dump-style") dumpStyle = true;
        else if (arg == "--ranges") ranges = true;
        else if (arg == "--ranges-only") ranges = true, drawIt = false;
        else if (arg.rfind("-", 0) == 0) bad = true;
        else pages.push_back(arg);
    }
    if (bad || (pages.empty() && !dumpStyle) || ((dump || dumpStyle) && pages.size() > 1)) {
        std::fputs("usage: Paint.exe PAGE.toml [PAGE.toml …] [--ranges]  |  Paint.exe PAGE.toml --dump-ranges"
                   "  |  Paint.exe [PAGE.toml] --dump-style\n", stderr);
        return 2;
    }
    if (dumpStyle) {
        try {
            toml::table doc;
            if (!pages.empty()) doc = toml::parse_file(pages.front());
            std::cout << Paint::readStyle(doc["style"].as_table()).merged << "\n";
        } catch (const std::exception& error) {
            std::fprintf(stderr, "%s\n", error.what());
            return 1;
        }
        return 0;
    }
    Status::Reporter status(0);
    if (pages.size() == 1) {                                  // one page: its exit code says how it went
        const Outcome outcome = one(pages.front(), dump, ranges, drawIt, status);
        if (outcome.code) status.log("error", outcome.error);
        return outcome.code;
    }
    int failed = 0;
    for (const auto& page : pages) {
        const Outcome outcome = one(page, false, ranges, drawIt, status);
        std::printf("{\"page\": %s, \"ok\": %s, \"error\": %s}\n", Status::quote(page).c_str(),
                    outcome.code ? "false" : "true", Status::quote(outcome.error).c_str());
        std::fflush(stdout);
        failed += outcome.code != 0;
    }
    return failed ? 1 : 0;
}
