#pragma once

#include <string>

#include <toml++/toml.hpp>

#include "TAxis.h"
#include "TCanvas.h"
#include "TGraph.h"
#include "TH1.h"
#include "TPaveStats.h"
#include "TROOT.h"
#include "TStyle.h"

#include "Paint/Style.hh"

namespace Paint {

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

        inline void mergeSection(const toml::node& sectionNode, Style& s) {
            if (!sectionNode.is_table()) return;
            const toml::node_view<const toml::node> sec(sectionNode);

            s.line.color   = readColor(sec["line_color"],  s.line.color);
            s.line.width   = static_cast<Width_t>(valueOr<int64_t>(sec["line_width"], s.line.width));
            s.line.style   = static_cast<Style_t>(valueOr<int64_t>(sec["line_style"], s.line.style));
            s.fill.color   = readColor(sec["fill_color"],  s.fill.color);
            s.fill.style   = static_cast<Style_t>(valueOr<int64_t>(sec["fill_style"], s.fill.style));
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
                s.canvas.width   = static_cast<Int_t>(valueOr<int64_t>(canvasNode["width"],    s.canvas.width));
                s.canvas.height  = static_cast<Int_t>(valueOr<int64_t>(canvasNode["height"],   s.canvas.height));
                s.canvas.marginL = static_cast<Float_t>(valueOr<double>(canvasNode["margin_l"], s.canvas.marginL));
                s.canvas.marginR = static_cast<Float_t>(valueOr<double>(canvasNode["margin_r"], s.canvas.marginR));
                s.canvas.marginB = static_cast<Float_t>(valueOr<double>(canvasNode["margin_b"], s.canvas.marginB));
                s.canvas.marginT = static_cast<Float_t>(valueOr<double>(canvasNode["margin_t"], s.canvas.marginT));
                s.canvas.ticksX  = valueOr<bool>(canvasNode["ticks_x"], s.canvas.ticksX);
                s.canvas.ticksY  = valueOr<bool>(canvasNode["ticks_y"], s.canvas.ticksY);
            }

            if (const auto statsNode = sec["stats"]; statsNode.is_table()) {
                s.stats.show       = valueOr<bool>(statsNode["show"],        s.stats.show);
                s.stats.optStat    = stringOr(statsNode["opt_stat"],         s.stats.optStat);
                s.stats.x          = valueOr<double>(statsNode["x"],         s.stats.x);
                s.stats.y          = valueOr<double>(statsNode["y"],         s.stats.y);
                s.stats.width      = valueOr<double>(statsNode["width"],     s.stats.width);
                s.stats.height     = valueOr<double>(statsNode["height"],    s.stats.height);
                s.stats.textFont   = static_cast<Font_t>(valueOr<int64_t>(statsNode["text_font"],   s.stats.textFont));
                s.stats.textSize   = static_cast<Float_t>(valueOr<double>(statsNode["text_size"],   s.stats.textSize));
                s.stats.borderSize = static_cast<Int_t>(valueOr<int64_t>(statsNode["border_size"],  s.stats.borderSize));
            }

            if (const auto legendNode = sec["legend"]; legendNode.is_table()) {
                s.legend.show     = valueOr<bool>(legendNode["show"],       s.legend.show);
                s.legend.x1       = valueOr<double>(legendNode["x1"],       s.legend.x1);
                s.legend.y1       = valueOr<double>(legendNode["y1"],       s.legend.y1);
                s.legend.x2       = valueOr<double>(legendNode["x2"],       s.legend.x2);
                s.legend.y2       = valueOr<double>(legendNode["y2"],       s.legend.y2);
                s.legend.textFont = static_cast<Font_t>(valueOr<int64_t>(legendNode["text_font"],  s.legend.textFont));
                s.legend.textSize = static_cast<Float_t>(valueOr<double>(legendNode["text_size"],  s.legend.textSize));
            }
        }
    }

    inline Style loadStyle(const std::string& tomlPath, const std::string& section = "default") {
        toml::table config = toml::parse_file(tomlPath);
        Style s{};

        if (config.contains("default"))
            if (const toml::node* n = config.get("default")) detail::mergeSection(*n, s);

        if (section != "default" && config.contains(section))
            if (const toml::node* n = config.get(section)) detail::mergeSection(*n, s);

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
}
