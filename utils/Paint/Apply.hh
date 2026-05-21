#pragma once

#include <string>

#include "TAxis.h"
#include "TGraph.h"
#include "TH1.h"
#include "TH2.h"
#include "TProfile.h"
#include "TROOT.h"
#include "TStyle.h"

#include "Paint/Types.hh"

namespace Paint {

    inline void applyGlobalStyle(const Style& style) {
        gStyle->SetOptStat(style.stats.show ? style.stats.optStat.c_str() : "");
        gStyle->SetOptTitle(1);
        gStyle->SetPadTickX(style.canvas.ticksX ? 1 : 0);
        gStyle->SetPadTickY(style.canvas.ticksY ? 1 : 0);
        gStyle->SetTitleFont(style.axis.titleFont, "XYZ");
        gStyle->SetLabelFont(style.axis.labelFont, "XYZ");
        gStyle->SetTitleSize(style.axis.titleSize, "XYZ");
        gStyle->SetLabelSize(style.axis.labelSize, "XYZ");
        gStyle->SetTitleBorderSize(0);
        gStyle->SetTitleAlign(23);
        gROOT->ForceStyle();
    }

    inline void applyAxis2D(TAxis* x, TAxis* y, const Style& style) {
        if (x == nullptr || y == nullptr) return;

        x->SetTitleFont(style.axis.titleFont);
        y->SetTitleFont(style.axis.titleFont);
        x->SetLabelFont(style.axis.labelFont);
        y->SetLabelFont(style.axis.labelFont);
        x->SetTitleSize(style.axis.titleSize);
        y->SetTitleSize(style.axis.titleSize);
        x->SetLabelSize(style.axis.labelSize);
        y->SetLabelSize(style.axis.labelSize);
        x->SetTitleOffset(style.axis.offsetX);
        y->SetTitleOffset(style.axis.offsetY);
        if (style.axis.centerTitles) {
            x->CenterTitle();
            y->CenterTitle();
        }
        y->SetMaxDigits(style.axis.maxDigitsY);
        if (!style.axis.titleX.empty()) x->SetTitle(style.axis.titleX.c_str());
        if (!style.axis.titleY.empty()) y->SetTitle(style.axis.titleY.c_str());
    }

    inline void apply(TH1* hist, const Style& style) {
        if (hist == nullptr) return;

        hist->SetLineColor(style.line.color);
        hist->SetLineWidth(style.line.width);
        hist->SetLineStyle(style.line.style);
        if (style.fill.style != 0) {
            hist->SetFillColor(style.fill.color);
            hist->SetFillStyle(style.fill.style);
        }
        hist->SetMarkerColor(style.marker.color);
        hist->SetMarkerStyle(style.marker.style);
        hist->SetMarkerSize(style.marker.size);
        hist->SetStats(style.stats.show ? 1 : 0);
        if (style.hasMinimum) hist->SetMinimum(style.minimum);
        if (style.hasMaximum) hist->SetMaximum(style.maximum);

        applyAxis2D(hist->GetXaxis(), hist->GetYaxis(), style);
    }

    inline void apply(TH2* hist, const Style& style) {
        if (hist == nullptr) return;
        apply(static_cast<TH1*>(hist), style);

        TAxis* z = hist->GetZaxis();
        if (z == nullptr) return;
        z->SetTitleFont(style.axis.titleFont);
        z->SetLabelFont(style.axis.labelFont);
        z->SetTitleSize(style.axis.titleSize);
        z->SetLabelSize(style.axis.labelSize);
        z->SetTitleOffset(style.axis.offsetZ);
        if (style.axis.centerTitles) z->CenterTitle();
        if (!style.axis.titleZ.empty()) z->SetTitle(style.axis.titleZ.c_str());
    }

    inline void apply(TGraph* graph, const Style& style) {
        if (graph == nullptr) return;

        graph->SetLineColor(style.line.color);
        graph->SetLineWidth(style.line.width);
        graph->SetLineStyle(style.line.style);
        graph->SetFillColor(style.fill.color);
        graph->SetFillStyle(style.fill.style);
        graph->SetMarkerColor(style.marker.color);
        graph->SetMarkerStyle(style.marker.style);
        graph->SetMarkerSize(style.marker.size);

        applyAxis2D(graph->GetXaxis(), graph->GetYaxis(), style);
    }

    inline const KindRegistry& kindRegistry() {
        static const KindRegistry kRegistry = {
            {ObjectKind::Hist2D, {
                [](const TObject* o) { return dynamic_cast<const TH2*>(o) != nullptr; },
                "TH2",
                [](TObject* o, const Style& s) { apply(dynamic_cast<TH2*>(o), s); },
                [](TObject* o, const std::string& opt) {
                    if (TH1* h = dynamic_cast<TH1*>(o)) h->Draw(opt.c_str());
                },
                "COLZ"
            }},
            {ObjectKind::TProfile, {
                [](const TObject* o) { return dynamic_cast<const TProfile*>(o) != nullptr; },
                "TProfile",
                [](TObject* o, const Style& s) { apply(dynamic_cast<TH1*>(o), s); },
                [](TObject* o, const std::string& opt) {
                    if (TH1* h = dynamic_cast<TH1*>(o)) h->Draw(opt.c_str());
                },
                "E1"
            }},
            {ObjectKind::Hist1D, {
                [](const TObject* o) {
                    return dynamic_cast<const TH1*>(o) != nullptr
                        && dynamic_cast<const TH2*>(o) == nullptr
                        && dynamic_cast<const TProfile*>(o) == nullptr;
                },
                "TH1",
                [](TObject* o, const Style& s) { apply(dynamic_cast<TH1*>(o), s); },
                [](TObject* o, const std::string& opt) {
                    if (TH1* h = dynamic_cast<TH1*>(o)) h->Draw(opt.c_str());
                },
                "HIST"
            }},
            {ObjectKind::Graph, {
                [](const TObject* o) { return dynamic_cast<const TGraph*>(o) != nullptr; },
                "TGraph",
                [](TObject* o, const Style& s) { apply(dynamic_cast<TGraph*>(o), s); },
                [](TObject* o, const std::string& opt) {
                    if (TGraph* g = dynamic_cast<TGraph*>(o)) g->Draw(opt.c_str());
                },
                "APL"
            }},
        };
        return kRegistry;
    }

} // namespace Paint
