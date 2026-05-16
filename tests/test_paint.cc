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
#include "TTree.h"

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

    std::cout << "ALL TESTS PASSED\n";
    return 0;
}
