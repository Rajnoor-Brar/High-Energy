// utils/Apps/Paint/main.cc — the ROOT plotting app (docs/05_Tools_Reference.md §17).
// requires: root toml
//
//     Paint.exe PAGE.toml [PAGE.toml …] [--ranges | --ranges-only]
//     Paint.exe PAGE.toml --dump-ranges
//     Paint.exe [PAGE.toml] --dump-style
//
// Each page in the order v1 found load-bearing: load → void → align data → normalise (V68) →
// auto-range → gutters → draw → save. Many pages are drawn in one process (V64: ROOT starts once, not once per page), and
// with more than one page every page's outcome is a JSON line on stdout, {"page": …, "ok": …,
// "error": …}, so one bad page does not stop the rest. `--ranges` also writes each page's final
// ranges and voided bins beside its config, <PAGE>.ranges.json, for the other backends; `--ranges-only`
// writes them and draws nothing (a run whose only backend is yoda).
// `--dump-ranges` prints one page's ranges as JSON and draws nothing, which is how the arithmetic is
// tested without looking at pixels. `--dump-style` prints the page's style — utils/Apps/Paint/base.toml
// with the page's [style] over it — as TOML; with no page, base.toml's.
// Exit codes: utils/Kit.hh's one table (V73): 0 ok, 1 page config, 2 usage, 4 input, 5 output (with
// several pages: 1 when any failed).

#include "Kit.hh"
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
            return {Kit::Config, error.what()};
        }
        if (page.heatmap) {                                   // V87: one 2D object; no ranges for another backend
            if (dump) {
                std::printf("{\"heatmap\": true}\n");
                return {};
            }
            if (ranges) {
                std::ofstream out(pagePath + ".ranges.json");
                out << "{\"heatmap\": true}\n";
                if (!out) return {Kit::Output, "cannot write " + pagePath + ".ranges.json"};
            }
            if (!drawIt) return {};
            try {
                Paint::heatmap(page);
            } catch (const std::exception& error) {
                return {Kit::Output, error.what()};
            }
            status.summary("\"page\": " + Status::quote(page.name) + ", \"formats\": " + std::to_string(page.formats.size()));
            return {};
        }
        std::vector<Paint::Series> curves;
        std::vector<std::vector<Paint::Series>> members;      // V69: each curve's band members
        Paint::Series data;
        bool haveData = false;
        try {
            for (const auto& source : page.curves) {
                curves.push_back(Paint::load(source, false));
                members.emplace_back();
                for (const auto& member : source.band) members.back().push_back(Paint::load(member, false));
            }
            if (page.hasData) data = Paint::load(page.data, true), haveData = true;
        } catch (const std::exception& error) {
            return {Kit::Input, error.what()};
        }

        // void, across the page
        const std::vector<bool> mask = Paint::voidMask(curves, page.voidEmpty, page.minEntries);
        if ((page.voidEmpty || page.minEntries > 0) && mask.empty() && curves.size() > 1)
            status.log("warn", page.name + ": curves differ in binning; nothing voided");
        Paint::applyVoid(curves, mask);
        for (auto& band : members) Paint::applyVoid(band, mask);

        // align the reference data to the MC edges, or drop it
        if (haveData && !Paint::alignTo(data, curves.front())) {
            status.log("warn", page.name + ": no reference bin lines up with the MC binning; data dropped");
            haveData = false;
        }

        // normalise (V68): after the void and the alignment, so the area is the drawn bins'
        if (page.normalise) {
            for (auto& c : curves) Paint::normalise(c);
            for (auto& band : members)
                for (auto& m : band) Paint::normalise(m);
            if (haveData) Paint::normalise(data);
        }
        for (size_t c = 0; c < curves.size(); ++c)                 // the envelope of what is drawn (V69)
            if (!members[c].empty() && !Paint::envelope(curves[c], members[c]))
                status.log("warn", page.name + ": a band member's binning differs from its curve's; no band");

        // ranges
        std::vector<const Paint::Series*> all;
        for (const auto& c : curves) all.push_back(&c);
        for (size_t c = 0; c < curves.size(); ++c)                 // a band's extremes are drawn too
            if (!curves[c].bandLo.empty())
                for (const auto& m : members[c]) all.push_back(&m);
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
            if (!out) return {Kit::Output, "cannot write " + pagePath + ".ranges.json"};
        }
        if (!drawIt) return {};
        try {
            Paint::draw(page, curves, haveData ? &data : nullptr, x, y);
        } catch (const std::exception& error) {
            return {Kit::Output, error.what()};
        }
        status.summary("\"page\": " + Status::quote(page.name) + ", \"formats\": " + std::to_string(page.formats.size()));
        return {};
    }

}  // namespace

int main(int argc, char** argv) {
    const Kit::Args args(argc, argv, {}, {"dump-ranges", "dump-style", "ranges", "ranges-only"});
    const std::vector<std::string>& pages = args.positional();
    const bool dump = args.has("dump-ranges"), dumpStyle = args.has("dump-style");
    const bool ranges = args.has("ranges") || args.has("ranges-only"), drawIt = !args.has("ranges-only");
    if (!args.ok() || (pages.empty() && !dumpStyle) || ((dump || dumpStyle) && pages.size() > 1)) {
        if (!args.error().empty()) std::fprintf(stderr, "Paint: %s\n", args.error().c_str());
        std::fputs("usage: Paint.exe PAGE.toml [PAGE.toml …] [--ranges | --ranges-only]  |  Paint.exe PAGE.toml --dump-ranges"
                   "  |  Paint.exe [PAGE.toml] --dump-style\n", stderr);
        return Kit::Usage;
    }
    if (dumpStyle) {
        try {
            toml::table doc;
            if (!pages.empty()) doc = toml::parse_file(pages.front());
            std::cout << Paint::readStyle(doc["style"].as_table()).merged << "\n";
        } catch (const std::exception& error) {
            std::fprintf(stderr, "%s\n", error.what());
            return Kit::Config;
        }
        return Kit::Ok;
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
    return failed ? Kit::Config : Kit::Ok;
}
