#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "TFile.h"
#include "TGraph.h"
#include "TH1D.h"
#include "TH2D.h"
#include "TProfile.h"
#include "TTree.h"

#include <toml++/toml.hpp>

#include "test_assert.hh"
#include "Paint.hh"

namespace {
    const std::filesystem::path kTmpDir = "tests/tmp_paint";
    const std::filesystem::path kInputRoot = kTmpDir / "input.root";
    const std::filesystem::path kResultsDir = kTmpDir / "results";

    void writeText(const std::filesystem::path& path, const std::string& text) {
        std::filesystem::create_directories(path.parent_path());
        std::ofstream out(path);
        if (!out) throw std::runtime_error("failed to write " + path.string());
        out << text;
    }

    void createFixtureRoot() {
        std::filesystem::create_directories(kTmpDir);

        TFile file(kInputRoot.string().c_str(), "RECREATE");

        TDirectory* validated = file.mkdir("Validated");
        validated->cd();
        TH1D mass("Validated_Mass_Invariant_Hist", "Mass", 20, 1.0, 1.3);
        TH1D repeatedA("Repeated_Hist", "Repeated A", 10, 0.0, 1.0);
        for (int i = 0; i < 20; ++i) {
            mass.Fill(1.08 + 0.004 * i);
            repeatedA.Fill(0.02 * i);
        }
        mass.Write();
        repeatedA.Write();

        file.cd();
        TDirectory* other = file.mkdir("Other");
        other->cd();
        TH1D repeatedB("Repeated_Hist", "Repeated B", 10, 0.0, 1.0);
        for (int i = 0; i < 10; ++i) repeatedB.Fill(0.05 * i);
        repeatedB.Write();

        file.cd();
        TDirectory* heat = file.mkdir("Heat");
        heat->cd();
        TH2D heatmap("Heatmap", "Heatmap", 4, 0.0, 4.0, 4, 0.0, 4.0);
        for (int x = 1; x <= 4; ++x) {
            for (int y = 1; y <= 4; ++y) {
                heatmap.SetBinContent(x, y, x * y);
            }
        }
        heatmap.Write();

        file.cd();
        TDirectory* graphs = file.mkdir("Graphs");
        graphs->cd();
        double xs[3] = {0.0, 1.0, 2.0};
        double ys[3] = {1.0, 2.0, 1.5};
        TGraph graph(3, xs, ys);
        graph.SetName("G1");
        graph.SetTitle("Graph One");
        graph.Write();

        file.cd();
        TDirectory* profiles = file.mkdir("Profiles");
        profiles->cd();
        TProfile prof("MeanPt", "Mean pT vs eta", 10, -2.5, 2.5, 0.0, 20.0);
        for (int i = 0; i < 10; ++i) prof.Fill(-2.0 + 0.4 * i, 1.0 + i * 0.5);
        prof.Write();

        file.cd();
        TTree tree("BadTree", "Unsupported tree");
        tree.Write();

        file.Close();
    }

    std::string commonHeader(const std::string& resultList) {
        return std::string{
            "[paint]\n"
            "root_file = \"" + kInputRoot.string() + "\"\n"
            "result_dir = \"" + kResultsDir.string() + "\"\n"
            "formats = [\"png\"]\n"
            "image_scale = 1\n"
            "results = " + resultList + "\n\n"
        };
    }

    void writeMainConfig(const std::filesystem::path& path) {
        writeText(path,
            commonHeader("[\"strict_hist\", \"search_grid\", \"graph_overlay\", \"heat\"]") +
            "[paint.massPreset]\n"
            "line_color = \"kRed-4\"\n"
            "fill_color = \"kRed-7\"\n\n"
            "[paint.axisPreset.axis]\n"
            "title_x = \"Mass Axis\"\n\n"
            "[paint.greenLine]\n"
            "line_color = \"kGreen+2\"\n\n"
            "[paint.strict_hist]\n"
            "use = \"massPreset\"\n"
            "axis_use = \"axisPreset\"\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n\n"
            "[paint.strict_hist.axis]\n"
            "title_y = \"Counts Override\"\n\n"
            "[paint.search_grid]\n"
            "source_search = \"Repeated_Hist\"\n\n"
            "[paint.graph_overlay]\n"
            "mode = \"overlay\"\n"
            "draw_option = \"APL\"\n"
            "sources = [{ path = \"Graphs/G1\", label = \"g1\", use = \"greenLine\", line_width = 3 }]\n\n"
            "[paint.graph_overlay.legend]\n"
            "show = true\n\n"
            "[paint.heat]\n"
            "sources = [{ path = \"Heat/Heatmap\" }]\n\n"
            "[paint.heat.axis]\n"
            "title_z = \"Weight\"\n");
    }

    template <typename Fn>
    void expectThrows(Fn&& fn, const std::string& needle) {
        try {
            fn();
        } catch (const std::runtime_error& ex) {
            const std::string msg = ex.what();
            TEST_TRUE(msg.find(needle) != std::string::npos);
            return;
        }
        TEST_TRUE(false);
    }
}

int main() {
    std::cout << "── test_paint ───────────────────────────────────────────────\n";

    std::filesystem::remove_all(kTmpDir);
    createFixtureRoot();

    const std::filesystem::path mainConfig = kTmpDir / "paint.toml";
    writeMainConfig(mainConfig);

    Paint::PaintBook book = Paint::loadBook(mainConfig.string());
    TEST_EQ(book.defaultStylePath, std::string{"configs/defaults/Paint.toml"});

    Paint::RenderPlan plan = Paint::resolveBook(book);
    TEST_EQ(plan.results.size(), std::size_t{4});

    const Paint::RenderResult& strict = plan.results[0];
    TEST_EQ(strict.name, std::string{"strict_hist"});
    TEST_EQ(strict.style.line.color, Paint::parseColor("kRed-4"));
    TEST_EQ(strict.style.axis.titleX, std::string{"Mass Axis"});
    TEST_EQ(strict.style.axis.titleY, std::string{"Counts Override"});
    TEST_EQ(strict.sources.size(), std::size_t{1});
    TEST_EQ(static_cast<int>(strict.sources[0].kind), static_cast<int>(Paint::ObjectKind::Hist1D));
    TEST_PASS("strict path and preset merge");

    const Paint::RenderResult& search = plan.results[1];
    TEST_EQ(static_cast<int>(search.mode), static_cast<int>(Paint::Mode::Grid));
    TEST_EQ(search.sources.size(), std::size_t{2});
    TEST_EQ(search.sources[0].path, std::string{"Other/Repeated_Hist"});
    TEST_EQ(search.sources[1].path, std::string{"Validated/Repeated_Hist"});
    TEST_TRUE(search.rows * search.cols >= 2);
    TEST_PASS("recursive exact source_search");

    const Paint::RenderResult& graph = plan.results[2];
    TEST_EQ(static_cast<int>(graph.mode), static_cast<int>(Paint::Mode::Overlay));
    TEST_EQ(static_cast<int>(graph.sources[0].kind), static_cast<int>(Paint::ObjectKind::Graph));
    TEST_EQ(graph.sources[0].style.line.color, Paint::parseColor("kGreen+2"));
    TEST_EQ(graph.sources[0].style.line.width, static_cast<Width_t>(3));
    TEST_PASS("source-level preset and inline override");

    const Paint::RenderResult& heat = plan.results[3];
    TEST_EQ(static_cast<int>(heat.sources[0].kind), static_cast<int>(Paint::ObjectKind::Hist2D));
    TEST_EQ(heat.style.axis.titleZ, std::string{"Weight"});
    TEST_PASS("TH2 resolution");

    std::ostringstream dryRun;
    Paint::printPlan(plan, dryRun);
    TEST_TRUE(dryRun.str().find("strict_hist") != std::string::npos);
    TEST_TRUE(dryRun.str().find("Other/Repeated_Hist") != std::string::npos);
    TEST_PASS("dry-run plan output");

    Paint::renderPlan(plan);
    TEST_TRUE(std::filesystem::exists(kResultsDir / "strict_hist.png"));
    TEST_TRUE(std::filesystem::exists(kResultsDir / "search_grid.png"));
    TEST_TRUE(std::filesystem::exists(kResultsDir / "graph_overlay.png"));
    TEST_TRUE(std::filesystem::exists(kResultsDir / "heat.png"));
    TEST_PASS("render smoke outputs");

    {
        // Phase 24: explicit mode = "overlay" + source_search must not be silently promoted to Grid.
        const std::filesystem::path cfg = kTmpDir / "explicit_mode.toml";
        writeText(cfg,
            commonHeader("[\"ov\"]") +
            "[paint.ov]\n"
            "mode = \"overlay\"\n"
            "source_search = \"Repeated_Hist\"\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_EQ(static_cast<int>(p.results[0].mode), static_cast<int>(Paint::Mode::Overlay));
        TEST_PASS("explicit mode = overlay not overridden by source_search auto-promotion");
    }

    const std::filesystem::path mixedConfig = kTmpDir / "mixed.toml";
    writeText(mixedConfig,
        commonHeader("[\"bad\"]") +
        "[paint.bad]\n"
        "source_search = \"Repeated_Hist\"\n"
        "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n");
    expectThrows([&]() {
        Paint::RenderPlan bad = Paint::resolveBook(Paint::loadBook(mixedConfig.string()));
    }, "cannot use both sources and source_search");
    TEST_PASS("mixed source controls fail");

    const std::filesystem::path unsupportedConfig = kTmpDir / "unsupported.toml";
    writeText(unsupportedConfig,
        commonHeader("[\"bad\"]") +
        "[paint.bad]\n"
        "sources = [{ path = \"BadTree\" }]\n");
    expectThrows([&]() {
        Paint::RenderPlan bad = Paint::resolveBook(Paint::loadBook(unsupportedConfig.string()));
    }, "unsupported ROOT object type");
    TEST_PASS("unsupported object fails");

    const std::filesystem::path missingConfig = kTmpDir / "missing.toml";
    writeText(missingConfig,
        commonHeader("[\"bad\"]") +
        "[paint.bad]\n"
        "sources = [{ path = \"Validated/DoesNotExist\" }]\n");
    expectThrows([&]() {
        Paint::RenderPlan bad = Paint::resolveBook(Paint::loadBook(missingConfig.string()));
    }, "not found");
    TEST_PASS("missing path fails");

    {
        // Phase 23: maximum = 0.0 must set hasMaximum = true, not evaluate abs(0.0) > 0.
        auto cfg = toml::parse("maximum = 0.0\n");
        Paint::Style s;
        Paint::mergeStyle(cfg, s);
        TEST_TRUE(s.hasMaximum);
        TEST_EQ(s.maximum, 0.0);
        TEST_PASS("maximum = 0.0 sets hasMaximum = true");
    }

    {
        // Phase 29: unknown colour token throws instead of silently returning kBlack.
        expectThrows([]() { Paint::parseColor("kRedd"); }, "unknown color token");
        TEST_PASS("unknown colour token throws");
    }

    {
        // Non-k non-numeric strings throw rather than silently falling back to kBlack.
        expectThrows([]() { Paint::parseColor("purple"); }, "unknown color spec");
        TEST_PASS("non-k non-numeric color string throws");
    }

    {
        // Phase 30: type mismatch (string value for int key) throws.
        auto cfg = toml::parse("line_width = \"thick\"\n");
        Paint::Style s;
        expectThrows([&]() { Paint::mergeStyle(cfg, s); }, "type mismatch");
        TEST_PASS("type mismatch for int key throws");
    }

    {
        // Phase 34: TProfile is detected as ObjectKind::TProfile, not Hist1D.
        const std::filesystem::path cfg = kTmpDir / "profile.toml";
        writeText(cfg,
            commonHeader("[\"prof\"]") +
            "[paint.prof]\n"
            "sources = [{ path = \"Profiles/MeanPt\" }]\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_EQ(static_cast<int>(p.results[0].sources[0].kind),
                static_cast<int>(Paint::ObjectKind::TProfile));
        TEST_PASS("TProfile detected as ObjectKind::TProfile");
    }

    {
        // Phase 35: palette assigns different line colors to source_search results.
        const std::filesystem::path cfg = kTmpDir / "palette.toml";
        writeText(cfg,
            commonHeader("[\"pal\"]") +
            "[paint.pal]\n"
            "mode = \"overlay\"\n"
            "source_search = \"Repeated_Hist\"\n"
            "palette = [\"kRed\", \"kBlue\"]\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        const auto& srcs = p.results[0].sources;
        TEST_TRUE(srcs.size() >= 2);
        TEST_EQ(srcs[0].style.line.color, Paint::parseColor("kRed"));
        TEST_EQ(srcs[1].style.line.color, Paint::parseColor("kBlue"));
        TEST_PASS("palette assigns per-source line colors");
    }

    {
        // Phase 36: glob wildcard in source_search.
        const std::filesystem::path cfg = kTmpDir / "glob.toml";
        writeText(cfg,
            commonHeader("[\"g\"]") +
            "[paint.g]\n"
            "mode = \"grid\"\n"
            "source_search = \"*_Hist\"\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        // Fixture has: Validated/Validated_Mass_Invariant_Hist, Validated/Repeated_Hist,
        // Other/Repeated_Hist — all end in _Hist
        TEST_TRUE(p.results[0].sources.size() >= 3);
        TEST_PASS("glob wildcard in source_search matches multiple objects");
    }

    {
        // Phase 37: source_type token matching is case-insensitive.
        const std::filesystem::path cfg = kTmpDir / "source_type.toml";
        writeText(cfg,
            commonHeader("[\"st\"]") +
            "[paint.st]\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\", source_type = \"th1\" }]\n");
        // Must not throw — lowercase "th1" should match TH1.
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_EQ(static_cast<int>(p.results[0].sources[0].kind),
                static_cast<int>(Paint::ObjectKind::Hist1D));
        TEST_PASS("source_type token matching is case-insensitive");
    }

    {
        // Phase 38: default_style = "" opts out of loading the defaults file.
        const std::filesystem::path cfg = kTmpDir / "no_defaults.toml";
        writeText(cfg,
            "[paint]\n"
            "root_file = \"" + kInputRoot.string() + "\"\n"
            "result_dir = \"" + kResultsDir.string() + "\"\n"
            "formats = [\"png\"]\n"
            "default_style = \"\"\n"
            "results = [\"nd\"]\n\n"
            "[paint.nd]\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n");
        Paint::PaintBook b = Paint::loadBook(cfg.string());
        TEST_EQ(b.defaultStylePath, std::string{""});
        // Must resolve without errors even without a defaults file.
        Paint::RenderPlan p = Paint::resolveBook(b);
        TEST_EQ(p.results.size(), std::size_t{1});
        TEST_PASS("default_style = \"\" opts out of defaults file");
    }

    {
        // Phase 39: output_name set in a visual preset is inherited by the result.
        const std::filesystem::path cfg = kTmpDir / "output_name_preset.toml";
        writeText(cfg,
            commonHeader("[\"r1\", \"r2\"]") +
            "[paint.myPreset]\n"
            "output_name = \"from_preset\"\n\n"
            "[paint.r1]\n"
            "use = \"myPreset\"\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n\n"
            "[paint.r2]\n"
            "use = \"myPreset\"\n"
            "output_name = \"overridden\"\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_EQ(p.results[0].outputName, std::string{"from_preset"});
        TEST_EQ(p.results[1].outputName, std::string{"overridden"});
        TEST_PASS("output_name in visual preset is inherited; result-level wins");
    }

    {
        // Phase 40: stats fill_color and fill_style are configurable.
        auto cfg = toml::parse("[stats]\nfill_color = \"kYellow\"\nfill_style = 3001\n");
        Paint::Style s;
        if (const toml::table* stats = cfg["stats"].as_table()) Paint::mergeStats(*stats, s.stats);
        TEST_EQ(s.stats.fillColor, Paint::parseColor("kYellow"));
        TEST_EQ(s.stats.fillStyle, static_cast<Style_t>(3001));
        TEST_PASS("stats fill_color and fill_style are configurable");
    }

    {
        // image_scale now multiplies canvas size and render style sizes; text_scale
        // and brush_scale are additional multipliers for their domains.
        const std::filesystem::path cfg = kTmpDir / "scale_options.toml";
        writeText(cfg,
            "[paint]\n"
            "root_file = \"" + kInputRoot.string() + "\"\n"
            "result_dir = \"" + kResultsDir.string() + "\"\n"
            "formats = [\"png\"]\n"
            "results = [\"sc\"]\n"
            "image_scale = 3\n"
            "text_scale = 0.5\n"
            "brush_scale = 2.0\n\n"
            "[paint.sc]\n"
            "line_width = 2\n"
            "marker_size = 1.5\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n\n"
            "[paint.sc.axis]\n"
            "title_size = 10.0\n"
            "label_size = 8.0\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_EQ(p.results[0].imageScale, 3);
        TEST_NEAR(p.results[0].textScale, 0.5, 1e-12);
        TEST_NEAR(p.results[0].brushScale, 2.0, 1e-12);

        const Paint::Style scaled = Paint::detail::scaledStyle(p.results[0].style, p.results[0]);
        TEST_NEAR(scaled.axis.titleSize, 15.0, 1e-6);
        TEST_NEAR(scaled.axis.labelSize, 12.0, 1e-6);
        TEST_EQ(scaled.line.width, static_cast<Width_t>(12));
        TEST_NEAR(scaled.marker.size, 9.0, 1e-6);
        TEST_PASS("image/text/brush scale options multiply render style sizes");
    }

    {
        // Phase 51 gap: preset cycle is detected and throws.
        const std::filesystem::path cfg = kTmpDir / "cycle.toml";
        writeText(cfg,
            commonHeader("[\"r\"]") +
            "[paint.A]\n"
            "use = \"B\"\n"
            "line_color = \"kRed\"\n\n"
            "[paint.B]\n"
            "use = \"A\"\n"
            "line_color = \"kBlue\"\n\n"
            "[paint.r]\n"
            "use = \"A\"\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n");
        expectThrows([&]() {
            Paint::resolveBook(Paint::loadBook(cfg.string()));
        }, "cycle involving");
        TEST_PASS("preset cycle detection throws");
    }

    {
        // Phase 51 gap: source_type mismatch throws.
        const std::filesystem::path cfg = kTmpDir / "type_mismatch.toml";
        writeText(cfg,
            commonHeader("[\"tm\"]") +
            "[paint.tm]\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\","
            " source_type = \"TH2\" }]\n");
        expectThrows([&]() {
            Paint::resolveBook(Paint::loadBook(cfg.string()));
        }, "expected TH2");
        TEST_PASS("source_type mismatch throws expected kind error");
    }

    {
        // Phase 51 gap: '?' wildcard matches single character in source_search.
        const std::filesystem::path cfg = kTmpDir / "qmark.toml";
        writeText(cfg,
            commonHeader("[\"q\"]") +
            "[paint.q]\n"
            "mode = \"grid\"\n"
            "source_search = \"?epeated_Hist\"\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_TRUE(p.results[0].sources.size() >= 2);
        TEST_PASS("? wildcard matches single character in source_search");
    }

    {
        // Phase 51 gap: empty palette = [] is a no-op (does not crash).
        const std::filesystem::path cfg = kTmpDir / "empty_palette.toml";
        writeText(cfg,
            commonHeader("[\"ep\"]") +
            "[paint.ep]\n"
            "mode = \"overlay\"\n"
            "source_search = \"Repeated_Hist\"\n"
            "palette = []\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_TRUE(p.results[0].sources.size() >= 2);
        TEST_PASS("empty palette = [] is a no-op");
    }

    {
        // Phase 51 gap: axis_use subsection preset applies axis title.
        const std::filesystem::path cfg = kTmpDir / "axis_use.toml";
        writeText(cfg,
            commonHeader("[\"au\"]") +
            "[paint.myAxis.axis]\n"
            "title_x = \"My X Axis\"\n\n"
            "[paint.au]\n"
            "axis_use = \"myAxis\"\n"
            "sources = [{ path = \"Validated/Validated_Mass_Invariant_Hist\" }]\n");
        Paint::RenderPlan p = Paint::resolveBook(Paint::loadBook(cfg.string()));
        TEST_EQ(p.results[0].style.axis.titleX, std::string{"My X Axis"});
        TEST_PASS("axis_use subsection preset applies axis title to result");
    }

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
