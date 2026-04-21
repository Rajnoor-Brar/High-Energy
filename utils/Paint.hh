#pragma once

#include <algorithm>
#include <cstddef>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include <toml++/toml.hpp>

#include "TAxis.h"
#include "TCanvas.h"
#include "TColor.h"
#include "TGraph.h"
#include "TH1.h"
#include "TPad.h"
#include "TPaveStats.h"
#include "TPaveText.h"
#include "TROOT.h"
#include "TStyle.h"
#include "TSystem.h"

namespace Paint {

    struct LineSpec   { Color_t color{kBlack}; Width_t width{1};  Style_t style{1}; };
    struct FillSpec   { Color_t color{0};      Style_t style{0}; };
    struct MarkerSpec { Color_t color{kBlack}; Style_t style{20}; Float_t size{1.0}; };

    struct AxisSpec {
        Font_t  titleFont{43};
        Font_t  labelFont{43};
        Float_t titleSize{27.0};
        Float_t labelSize{20.0};
        Float_t offsetX{1.1};
        Float_t offsetY{1.35};
        bool    centerTitles{true};
        Int_t   maxDigitsY{3};
        std::string titleX{};
        std::string titleY{};
    };

    struct CanvasSpec {
        Int_t   width{900};
        Int_t   height{600};
        Float_t marginL{0.12};
        Float_t marginR{0.05};
        Float_t marginB{0.12};
        Float_t marginT{0.08};
        bool    ticksX{true};
        bool    ticksY{true};
    };

    struct StatsSpec {
        bool        show{true};
        std::string optStat{"emr"};
        Double_t    x{0.79};
        Double_t    y{0.89};
        Double_t    width{0.18};
        Double_t    height{0.10};
        Font_t      textFont{43};
        Float_t     textSize{12.0};
        Int_t       borderSize{2};
    };

    struct LegendSpec {
        bool     show{false};
        Double_t x1{0.65}, y1{0.75}, x2{0.88}, y2{0.88};
        Font_t   textFont{43};
        Float_t  textSize{14.0};
    };

    struct Style {
        LineSpec    line{};
        FillSpec    fill{};
        MarkerSpec  marker{};
        AxisSpec    axis{};
        CanvasSpec  canvas{};
        StatsSpec   stats{};
        LegendSpec  legend{};
        std::string drawOption{"HIST"};
        Double_t    minimum{0.0};
    };

    // Parse "kBlue-6", "kRed+2", "kBlack", or a plain integer.
    inline Color_t parseColor(const std::string& spec) {
        static const std::unordered_map<std::string, Color_t> kNamedColors = {
            {"kWhite",   kWhite},   {"kBlack",   kBlack},   {"kGray",    kGray},
            {"kRed",     kRed},     {"kGreen",   kGreen},   {"kBlue",    kBlue},
            {"kYellow",  kYellow},  {"kMagenta", kMagenta}, {"kCyan",    kCyan},
            {"kOrange",  kOrange},  {"kSpring",  kSpring},  {"kTeal",    kTeal},
            {"kAzure",   kAzure},   {"kViolet",  kViolet},  {"kPink",    kPink},
        };

        std::string s = spec;
        s.erase(std::remove_if(s.begin(), s.end(), ::isspace), s.end());
        if (s.empty()) return kBlack;

        if (s[0] != 'k') {
            try { return static_cast<Color_t>(std::stoi(s)); }
            catch (...) { return kBlack; }
        }

        std::size_t opPos = s.find_first_of("+-", 1);
        const std::string base   = (opPos == std::string::npos) ? s : s.substr(0, opPos);
        const int         offset = (opPos == std::string::npos) ? 0 : std::stoi(s.substr(opPos));

        const auto it = kNamedColors.find(base);
        if (it == kNamedColors.end()) return kBlack;
        return static_cast<Color_t>(it->second + offset);
    }

    namespace detail {
        inline Color_t readColor(const toml::node_view<const toml::node>& node, Color_t fallback) {
            if (!node) return fallback;
            if (node.is_string()) return parseColor(node.value<std::string>().value_or(""));
            if (node.is_integer()) return static_cast<Color_t>(node.value<int64_t>().value_or(fallback));
            return fallback;
        }

        template <typename T>
        inline T valueOr(const toml::node_view<const toml::node>& node, T fallback) {
            return node ? node.value<T>().value_or(fallback) : fallback;
        }

        inline std::string stringOr(const toml::node_view<const toml::node>& node, const std::string& fallback) {
            return node ? node.value<std::string>().value_or(fallback) : fallback;
        }

        // Load a single section's fields on top of a pre-populated Style (so defaults cascade).
        inline void mergeSection(const toml::node& sectionNode, Style& s) {
            if (!sectionNode.is_table()) return;
            const toml::node_view<const toml::node> sec(sectionNode);

            s.line.color  = readColor(sec["line_color"],  s.line.color);
            s.line.width  = static_cast<Width_t>(valueOr<int64_t>(sec["line_width"],  s.line.width));
            s.line.style  = static_cast<Style_t>(valueOr<int64_t>(sec["line_style"],  s.line.style));
            s.fill.color  = readColor(sec["fill_color"],  s.fill.color);
            s.fill.style  = static_cast<Style_t>(valueOr<int64_t>(sec["fill_style"],  s.fill.style));
            s.marker.color = readColor(sec["marker_color"], s.marker.color);
            s.marker.style = static_cast<Style_t>(valueOr<int64_t>(sec["marker_style"], s.marker.style));
            s.marker.size  = static_cast<Float_t>(valueOr<double>(sec["marker_size"],  s.marker.size));

            s.drawOption = stringOr(sec["draw_option"], s.drawOption);
            s.minimum    = valueOr<double>(sec["minimum"], s.minimum);

            if (const auto axisNode = sec["axis"]; axisNode.is_table()) {
                s.axis.titleFont    = static_cast<Font_t>(valueOr<int64_t>(axisNode["title_font"], s.axis.titleFont));
                s.axis.labelFont    = static_cast<Font_t>(valueOr<int64_t>(axisNode["label_font"], s.axis.labelFont));
                s.axis.titleSize    = static_cast<Float_t>(valueOr<double>(axisNode["title_size"], s.axis.titleSize));
                s.axis.labelSize    = static_cast<Float_t>(valueOr<double>(axisNode["label_size"], s.axis.labelSize));
                s.axis.offsetX      = static_cast<Float_t>(valueOr<double>(axisNode["offset_x"],   s.axis.offsetX));
                s.axis.offsetY      = static_cast<Float_t>(valueOr<double>(axisNode["offset_y"],   s.axis.offsetY));
                s.axis.centerTitles = valueOr<bool>(axisNode["center_titles"], s.axis.centerTitles);
                s.axis.maxDigitsY   = static_cast<Int_t>(valueOr<int64_t>(axisNode["max_digits_y"], s.axis.maxDigitsY));
                s.axis.titleX       = stringOr(axisNode["title_x"], s.axis.titleX);
                s.axis.titleY       = stringOr(axisNode["title_y"], s.axis.titleY);
            }

            if (const auto canvasNode = sec["canvas"]; canvasNode.is_table()) {
                s.canvas.width    = static_cast<Int_t>(valueOr<int64_t>(canvasNode["width"],  s.canvas.width));
                s.canvas.height   = static_cast<Int_t>(valueOr<int64_t>(canvasNode["height"], s.canvas.height));
                s.canvas.marginL  = static_cast<Float_t>(valueOr<double>(canvasNode["margin_l"], s.canvas.marginL));
                s.canvas.marginR  = static_cast<Float_t>(valueOr<double>(canvasNode["margin_r"], s.canvas.marginR));
                s.canvas.marginB  = static_cast<Float_t>(valueOr<double>(canvasNode["margin_b"], s.canvas.marginB));
                s.canvas.marginT  = static_cast<Float_t>(valueOr<double>(canvasNode["margin_t"], s.canvas.marginT));
                s.canvas.ticksX   = valueOr<bool>(canvasNode["ticks_x"], s.canvas.ticksX);
                s.canvas.ticksY   = valueOr<bool>(canvasNode["ticks_y"], s.canvas.ticksY);
            }

            if (const auto statsNode = sec["stats"]; statsNode.is_table()) {
                s.stats.show       = valueOr<bool>(statsNode["show"], s.stats.show);
                s.stats.optStat    = stringOr(statsNode["opt_stat"], s.stats.optStat);
                s.stats.x          = valueOr<double>(statsNode["x"], s.stats.x);
                s.stats.y          = valueOr<double>(statsNode["y"], s.stats.y);
                s.stats.width      = valueOr<double>(statsNode["width"],  s.stats.width);
                s.stats.height     = valueOr<double>(statsNode["height"], s.stats.height);
                s.stats.textFont   = static_cast<Font_t>(valueOr<int64_t>(statsNode["text_font"], s.stats.textFont));
                s.stats.textSize   = static_cast<Float_t>(valueOr<double>(statsNode["text_size"], s.stats.textSize));
                s.stats.borderSize = static_cast<Int_t>(valueOr<int64_t>(statsNode["border_size"], s.stats.borderSize));
            }

            if (const auto legendNode = sec["legend"]; legendNode.is_table()) {
                s.legend.show     = valueOr<bool>(legendNode["show"], s.legend.show);
                s.legend.x1       = valueOr<double>(legendNode["x1"], s.legend.x1);
                s.legend.y1       = valueOr<double>(legendNode["y1"], s.legend.y1);
                s.legend.x2       = valueOr<double>(legendNode["x2"], s.legend.x2);
                s.legend.y2       = valueOr<double>(legendNode["y2"], s.legend.y2);
                s.legend.textFont = static_cast<Font_t>(valueOr<int64_t>(legendNode["text_font"], s.legend.textFont));
                s.legend.textSize = static_cast<Float_t>(valueOr<double>(legendNode["text_size"], s.legend.textSize));
            }
        }
    }

    inline Style loadStyle(const std::string& tomlPath, const std::string& section = "default") {
        toml::table config = toml::parse_file(tomlPath);
        Style s{};

        if (config.contains("default")) {
            if (const toml::node* defaultNode = config.get("default"))
                detail::mergeSection(*defaultNode, s);
        }

        if (section != "default" && config.contains(section)) {
            if (const toml::node* sectionNode = config.get(section))
                detail::mergeSection(*sectionNode, s);
        }

        return s;
    }

    inline void applyGlobalStyle(const Style& s) {
        gStyle->SetOptStat(s.stats.optStat.c_str());
        gStyle->SetOptTitle(1);
        gStyle->SetPadTickX(s.canvas.ticksX ? 1 : 0);
        gStyle->SetPadTickY(s.canvas.ticksY ? 1 : 0);
        gStyle->SetTitleFont(s.axis.titleFont, "XYZ");
        gStyle->SetLabelFont(s.axis.labelFont, "XYZ");
        gStyle->SetTitleSize(s.axis.titleSize, "XYZ");
        gStyle->SetLabelSize(s.axis.labelSize, "XYZ");
        gStyle->SetTitleBorderSize(0);
        gStyle->SetTitleAlign(23);
    }

    inline void applyStyle(TH1* h, const Style& s) {
        if (h == nullptr) return;
        h->SetLineColor(s.line.color);
        h->SetLineWidth(s.line.width);
        h->SetLineStyle(s.line.style);
        if (s.fill.style != 0) {
            h->SetFillColor(s.fill.color);
            h->SetFillStyle(s.fill.style);
        }
        h->SetMarkerColor(s.marker.color);
        h->SetMarkerStyle(s.marker.style);
        h->SetMarkerSize(s.marker.size);

        auto axX = h->GetXaxis();
        auto axY = h->GetYaxis();
        axX->SetTitleFont(s.axis.titleFont);
        axY->SetTitleFont(s.axis.titleFont);
        axX->SetLabelFont(s.axis.labelFont);
        axY->SetLabelFont(s.axis.labelFont);
        axX->SetTitleSize(s.axis.titleSize);
        axY->SetTitleSize(s.axis.titleSize);
        axX->SetLabelSize(s.axis.labelSize);
        axY->SetLabelSize(s.axis.labelSize);
        axX->SetTitleOffset(s.axis.offsetX);
        axY->SetTitleOffset(s.axis.offsetY);
        if (s.axis.centerTitles) { axX->CenterTitle(); axY->CenterTitle(); }
        axY->SetMaxDigits(s.axis.maxDigitsY);
        if (!s.axis.titleX.empty()) axX->SetTitle(s.axis.titleX.c_str());
        if (!s.axis.titleY.empty()) axY->SetTitle(s.axis.titleY.c_str());

        h->SetStats(s.stats.show ? 1 : 0);
        h->SetMinimum(s.minimum);
    }

    inline void applyStyle(TGraph* g, const Style& s) {
        if (g == nullptr) return;
        g->SetLineColor(s.line.color);
        g->SetLineWidth(s.line.width);
        g->SetLineStyle(s.line.style);
        g->SetFillColor(s.fill.color);
        g->SetFillStyle(s.fill.style);
        g->SetMarkerColor(s.marker.color);
        g->SetMarkerStyle(s.marker.style);
        g->SetMarkerSize(s.marker.size);
    }

    inline TCanvas* makeCanvas(const Style& s,
                               const std::string& name  = "c",
                               const std::string& title = "c")
    {
        TCanvas* c = new TCanvas(name.c_str(), title.c_str(), s.canvas.width, s.canvas.height);
        c->SetLeftMargin(s.canvas.marginL);
        c->SetRightMargin(s.canvas.marginR);
        c->SetBottomMargin(s.canvas.marginB);
        c->SetTopMargin(s.canvas.marginT);
        c->SetTicks(s.canvas.ticksX ? 1 : 0, s.canvas.ticksY ? 1 : 0);
        c->SetFillColor(0);
        c->SetBorderMode(0);
        c->SetFrameBorderMode(0);
        return c;
    }

    inline void applyStats(TH1* h, TCanvas* c, const Style& s) {
        if (h == nullptr || c == nullptr || !s.stats.show) return;
        TPaveStats* st = dynamic_cast<TPaveStats*>(h->FindObject("stats"));
        if (st == nullptr) return;

        st->SetX2NDC(s.stats.x);
        st->SetY2NDC(s.stats.y);
        st->SetX1NDC(s.stats.x - s.stats.width);
        st->SetY1NDC(s.stats.y - s.stats.height);
        st->SetTextFont(s.stats.textFont);
        st->SetTextSize(s.stats.textSize);
        st->SetBorderSize(s.stats.borderSize);
        st->SetFillColor(0);
        st->SetFillStyle(1001);
        c->Modified();
        c->Update();
    }

    namespace detail {
        inline void ensureDirFor(const std::string& path) {
            const auto slash = path.find_last_of('/');
            if (slash == std::string::npos) return;
            gSystem->mkdir(path.substr(0, slash).c_str(), kTRUE);
        }
    }

    inline void saveToFile(TH1* h, const Style& s, const std::string& outPath) {
        if (h == nullptr) return;
        detail::ensureDirFor(outPath);
        applyGlobalStyle(s);
        TCanvas* c = makeCanvas(s, "c_paint", h->GetTitle());
        applyStyle(h, s);
        h->Draw(s.drawOption.c_str());
        c->Update();
        applyStats(h, c, s);
        c->Print(outPath.c_str());
        delete c;
    }

    inline void savePdf(TH1* h, const Style& s, const std::string& outPath) {
        const std::string p = outPath.size() >= 4 && outPath.substr(outPath.size() - 4) == ".pdf"
            ? outPath : outPath + ".pdf";
        saveToFile(h, s, p);
    }

    inline void savePng(TH1* h, const Style& s, const std::string& outPath) {
        const std::string p = outPath.size() >= 4 && outPath.substr(outPath.size() - 4) == ".png"
            ? outPath : outPath + ".png";
        saveToFile(h, s, p);
    }

    inline void saveSvg(TH1* h, const Style& s, const std::string& outPath) {
        const std::string p = outPath.size() >= 4 && outPath.substr(outPath.size() - 4) == ".svg"
            ? outPath : outPath + ".svg";
        saveToFile(h, s, p);
    }

    struct PadLayout { Int_t rows{1}; Int_t cols{1}; };

    inline void saveComposite(const std::vector<TH1*>&         hists,
                              const std::vector<const Style*>& styles,
                              const std::vector<std::string>&  titles,
                              PadLayout                        layout,
                              const std::string&               outPath)
    {
        if (hists.empty()) return;
        if (styles.size() != hists.size())
            throw std::runtime_error("Paint::saveComposite: styles size must match hists");

        detail::ensureDirFor(outPath);
        const Style& base = *styles.front();
        applyGlobalStyle(base);

        TCanvas* c = new TCanvas("c_composite", "composite",
                                  base.canvas.width * layout.cols,
                                  base.canvas.height * layout.rows);
        c->Divide(layout.cols, layout.rows);

        const std::size_t nPads = static_cast<std::size_t>(layout.rows * layout.cols);
        const std::size_t n     = std::min(hists.size(), nPads);
        for (std::size_t i = 0; i < n; ++i) {
            TPad* pad = static_cast<TPad*>(c->cd(static_cast<Int_t>(i + 1)));
            if (pad == nullptr) continue;
            pad->SetLeftMargin(styles[i]->canvas.marginL);
            pad->SetRightMargin(styles[i]->canvas.marginR);
            pad->SetBottomMargin(styles[i]->canvas.marginB);
            pad->SetTopMargin(styles[i]->canvas.marginT);
            pad->SetTicks(styles[i]->canvas.ticksX ? 1 : 0, styles[i]->canvas.ticksY ? 1 : 0);

            applyStyle(hists[i], *styles[i]);
            if (i < titles.size() && !titles[i].empty()) hists[i]->SetTitle(titles[i].c_str());
            hists[i]->Draw(styles[i]->drawOption.c_str());
            pad->Update();
            applyStats(hists[i], c, *styles[i]);
        }

        c->Print(outPath.c_str());
        delete c;
    }
}
