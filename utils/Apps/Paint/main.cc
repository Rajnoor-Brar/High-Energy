// utils/Apps/Paint/main.cc — the ROOT plotting app (docs/rework_v2/05_Tools.md §7).
// requires: root toml
//
//     Paint.exe PAGE.toml [--dump-ranges]
//     Paint.exe [PAGE.toml] --dump-style
//
// One page per call, in the order v1 found load-bearing: load → void → align data → auto-range →
// gutters → draw → save. `--dump-ranges` prints the final ranges and the voided bins as JSON and
// draws nothing, which is how the arithmetic is tested without looking at pixels. `--dump-style`
// prints the page's style — utils/Apps/Paint/base.toml with the page's [style] over it — as TOML;
// with no page, base.toml's.
// Exit codes (02 §9): 0 ok, 1 page config, 2 usage, 4 input, 5 output.

#include "Status.hh"

#include "Draw.hh"
#include "Page.hh"
#include "Transform.hh"

#include <cstdio>
#include <iostream>
#include <string>
#include <vector>

int main(int argc, char** argv) {
    std::vector<std::string> positional;
    bool dump = false, dumpStyle = false, bad = false;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--dump-ranges") dump = true;
        else if (arg == "--dump-style") dumpStyle = true;
        else if (arg.rfind("-", 0) == 0) bad = true;
        else positional.push_back(arg);
    }
    if (bad || positional.size() > 1 || (positional.empty() && !dumpStyle)) {
        std::fputs("usage: Paint.exe PAGE.toml [--dump-ranges]  |  Paint.exe [PAGE.toml] --dump-style\n", stderr);
        return 2;
    }
    if (dumpStyle) {
        try {
            toml::table doc;
            if (!positional.empty()) doc = toml::parse_file(positional.front());
            std::cout << Paint::readStyle(doc["style"].as_table()).merged << "\n";
        } catch (const std::exception& error) {
            std::fprintf(stderr, "%s\n", error.what());
            return 1;
        }
        return 0;
    }
    const std::string pagePath = positional.front();
    Status::Reporter status(0);

    Paint::Page page;
    try {
        page = Paint::readPage(pagePath);
    } catch (const std::exception& error) {
        status.log("error", error.what());
        return 1;
    }

    std::vector<Paint::Series> curves;
    Paint::Series data;
    bool haveData = false;
    try {
        for (const auto& source : page.curves) curves.push_back(Paint::load(source, false));
        if (page.hasData) data = Paint::load(page.data, true), haveData = true;
    } catch (const std::exception& error) {
        status.log("error", error.what());
        return 4;
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

    if (dump) {
        std::string voided;
        for (size_t i = 0; i < mask.size(); ++i)
            if (mask[i]) voided += (voided.empty() ? "" : ", ") + std::to_string(i + 1);
        std::printf("{\"x\": [%.10g, %.10g], \"y\": [%.10g, %.10g], \"largest\": %.10g, \"voided\": [%s], "
                    "\"data_bins\": %zu, \"data_x\": [%.10g, %.10g]}\n", x.lo, x.hi, y.lo, y.hi, y.largest, voided.c_str(),
                    haveData ? data.size() : 0, haveData ? data.lo.front() : 0.0, haveData ? data.hi.back() : 0.0);
        return 0;
    }
    try {
        Paint::draw(page, curves, haveData ? &data : nullptr, x, y);
    } catch (const std::exception& error) {
        status.log("error", error.what());
        return 5;
    }
    status.summary("\"page\": " + Status::quote(page.name) + ", \"formats\": " + std::to_string(page.formats.size()));
    return 0;
}
