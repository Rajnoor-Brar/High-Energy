#pragma once

#include <algorithm>
#include <cctype>
#include <memory>
#include <stdexcept>
#include <string>

#include "TCanvas.h"
#include "TGraph.h"
#include "TH1.h"
#include "TH2.h"
#include "TLegend.h"
#include "TPad.h"
#include "TPaveStats.h"
#include "TPaveText.h"
#include "TROOT.h"

#include "Paint/Apply.hh"
#include "Paint/Save.hh"
#include "Paint/Style.hh"
#include "Paint/Types.hh"

namespace Paint {

    namespace detail {

        inline std::unique_ptr<TCanvas> makeCanvas(const RenderResult& result) {
            const int width = result.style.canvas.width * std::max(1, result.cols);
            const int height = result.style.canvas.height * std::max(1, result.rows);
            auto canvas = std::make_unique<TCanvas>(
                ("c_" + result.name).c_str(),
                result.title.empty() ? result.name.c_str() : result.title.c_str(),
                width,
                height);

            canvas->SetLeftMargin(result.style.canvas.marginL);
            canvas->SetRightMargin(result.style.canvas.marginR);
            canvas->SetBottomMargin(result.style.canvas.marginB);
            canvas->SetTopMargin(result.style.canvas.marginT);
            canvas->SetTicks(result.style.canvas.ticksX ? 1 : 0, result.style.canvas.ticksY ? 1 : 0);
            canvas->SetFillColor(0);
            canvas->SetBorderMode(0);
            canvas->SetFrameBorderMode(0);
            return canvas;
        }

        inline void configurePad(TPad* pad, const Style& style) {
            if (pad == nullptr) return;
            pad->SetLeftMargin(style.canvas.marginL);
            pad->SetRightMargin(style.canvas.marginR);
            pad->SetBottomMargin(style.canvas.marginB);
            pad->SetTopMargin(style.canvas.marginT);
            pad->SetTicks(style.canvas.ticksX ? 1 : 0, style.canvas.ticksY ? 1 : 0);
            pad->SetLogx(style.logX ? 1 : 0);
            pad->SetLogy(style.logY ? 1 : 0);
            pad->SetLogz(style.logZ ? 1 : 0);
            pad->SetGrid(style.gridX ? 1 : 0, style.gridY ? 1 : 0);
            pad->SetFillColor(0);
            pad->SetBorderMode(0);
            pad->SetFrameBorderMode(0);
        }

        inline std::string defaultDrawOption(const ResolvedSource& source) {
            std::string option = source.drawOption.empty() ? source.style.drawOption : source.drawOption;
            if (source.kind == ObjectKind::Hist2D && (option.empty() || option == "HIST")) return "COLZ";
            if (source.kind == ObjectKind::Graph && (option.empty() || option == "HIST")) return "APL";
            return option.empty() ? "HIST" : option;
        }

        inline bool containsSame(const std::string& option) {
            std::string upper = option;
            std::transform(upper.begin(), upper.end(), upper.begin(), [](unsigned char ch) {
                return static_cast<char>(std::toupper(ch));
            });
            return upper.find("SAME") != std::string::npos;
        }

        inline void applyToSource(ResolvedSource& source) {
            switch (source.kind) {
                case ObjectKind::Hist2D:
                    apply(dynamic_cast<TH2*>(source.object), source.style);
                    break;
                case ObjectKind::Hist1D:
                    apply(dynamic_cast<TH1*>(source.object), source.style);
                    break;
                case ObjectKind::Graph:
                    apply(dynamic_cast<TGraph*>(source.object), source.style);
                    break;
            }
        }

        inline void drawSource(ResolvedSource& source, const std::string& option) {
            switch (source.kind) {
                case ObjectKind::Hist2D:
                case ObjectKind::Hist1D:
                    if (TH1* hist = dynamic_cast<TH1*>(source.object)) hist->Draw(option.c_str());
                    break;
                case ObjectKind::Graph:
                    if (TGraph* graph = dynamic_cast<TGraph*>(source.object)) graph->Draw(option.c_str());
                    break;
            }
        }

        inline void setSourceTitle(ResolvedSource& source) {
            if (source.title.empty()) return;
            if (TH1* hist = dynamic_cast<TH1*>(source.object)) {
                hist->SetTitle(source.title.c_str());
            } else if (TGraph* graph = dynamic_cast<TGraph*>(source.object)) {
                graph->SetTitle(source.title.c_str());
            }
        }

        inline void applyStatsBox(ResolvedSource& source, TPad* pad) {
            if (pad == nullptr || !source.style.stats.show) return;
            TH1* hist = dynamic_cast<TH1*>(source.object);
            if (hist == nullptr) return;

            pad->Update();
            TPaveStats* stats = dynamic_cast<TPaveStats*>(hist->FindObject("stats"));
            if (stats == nullptr) return;

            stats->SetX2NDC(source.style.stats.x);
            stats->SetY2NDC(source.style.stats.y);
            stats->SetX1NDC(source.style.stats.x - source.style.stats.width);
            stats->SetY1NDC(source.style.stats.y - source.style.stats.height);
            stats->SetTextFont(source.style.stats.textFont);
            stats->SetTextSize(source.style.stats.textSize);
            stats->SetBorderSize(source.style.stats.borderSize);
            stats->SetFillColor(0);
            stats->SetFillStyle(1001);
            pad->Modified();
            pad->Update();
        }

        inline void applyTitleBox(TPad* pad, const Style& style) {
            if (pad == nullptr || !style.titleBox.show) return;
            pad->Update();
            TPaveText* title = dynamic_cast<TPaveText*>(pad->GetPrimitive("title"));
            if (title == nullptr) return;
            title->SetTextFont(style.titleBox.textFont);
            title->SetTextSize(style.titleBox.textSize);
            title->SetBorderSize(style.titleBox.borderSize);
            title->SetFillColor(0);
            title->SetFillStyle(style.titleBox.fillStyle);
            pad->Modified();
            pad->Update();
        }

        inline void drawOneOnPad(ResolvedSource& source, TPad* pad) {
            configurePad(pad, source.style);
            if (pad != nullptr) pad->cd();
            applyGlobalStyle(source.style);
            applyToSource(source);
            setSourceTitle(source);
            drawSource(source, defaultDrawOption(source));
            applyStatsBox(source, pad);
            applyTitleBox(pad, source.style);
        }

        inline void drawSingle(RenderResult& result, TCanvas& canvas) {
            drawOneOnPad(result.sources.front(), &canvas);
        }

        inline void drawGrid(RenderResult& result, TCanvas& canvas) {
            canvas.Divide(result.cols, result.rows);
            for (std::size_t i = 0; i < result.sources.size(); ++i) {
                TPad* pad = dynamic_cast<TPad*>(canvas.cd(static_cast<Int_t>(i + 1)));
                drawOneOnPad(result.sources[i], pad);
            }
            canvas.cd();
        }

        inline void drawOverlay(RenderResult& result, TCanvas& canvas) {
            configurePad(&canvas, result.style);
            canvas.cd();
            applyGlobalStyle(result.style);

            const bool hasLabels = std::any_of(result.sources.begin(), result.sources.end(), [](const ResolvedSource& source) {
                return !source.label.empty();
            });

            std::unique_ptr<TLegend> legend;
            if (result.style.legend.show || hasLabels) {
                legend = std::make_unique<TLegend>(
                    result.style.legend.x1, result.style.legend.y1,
                    result.style.legend.x2, result.style.legend.y2);
                legend->SetTextFont(result.style.legend.textFont);
                legend->SetTextSize(result.style.legend.textSize);
                legend->SetBorderSize(result.style.legend.borderSize);
                legend->SetFillStyle(result.style.legend.fillStyle);
            }

            for (std::size_t i = 0; i < result.sources.size(); ++i) {
                ResolvedSource& source = result.sources[i];
                applyToSource(source);
                setSourceTitle(source);

                std::string option = defaultDrawOption(source);
                if (i > 0 && !containsSame(option)) option += " SAME";
                drawSource(source, option);
                applyStatsBox(source, &canvas);

                if (legend && !source.label.empty()) {
                    legend->AddEntry(source.object, source.label.c_str(), "lpf");
                }
            }

            if (legend) legend->Draw();
            applyTitleBox(&canvas, result.style);
            canvas.Modified();
            canvas.Update();
        }

    } // namespace detail

    inline void renderResult(RenderResult& result) {
        std::unique_ptr<TCanvas> canvas = detail::makeCanvas(result);

        switch (result.mode) {
            case Mode::Single:
                detail::drawSingle(result, *canvas);
                break;
            case Mode::Overlay:
                detail::drawOverlay(result, *canvas);
                break;
            case Mode::Grid:
                detail::drawGrid(result, *canvas);
                break;
        }

        canvas->Modified();
        canvas->Update();
        saveCanvas(*canvas, result);
    }

    inline void renderPlan(RenderPlan& plan) {
        gROOT->SetBatch(kTRUE);
        for (RenderResult& result : plan.results) {
            renderResult(result);
        }
    }

} // namespace Paint
