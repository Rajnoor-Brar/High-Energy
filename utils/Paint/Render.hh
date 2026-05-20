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
            const int scale = std::max(1, result.imageScale);
            const int width = result.style.canvas.width * std::max(1, result.cols) * scale;
            const int height = result.style.canvas.height * std::max(1, result.rows) * scale;
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
            for (const auto& [kind, entry] : kindRegistry()) {
                if (kind == source.kind) {
                    if (option.empty() || option == "HIST") return entry.defaultDraw;
                    return option;
                }
            }
            return option.empty() ? "HIST" : option;
        }

        // Derive the TLegend marker-type string from the resolved draw option.
        // 'l' = line, 'p' = marker, 'f' = filled box.
        inline std::string legendOption(const ResolvedSource& source, const std::string& drawOpt) {
            std::string upper = drawOpt;
            std::transform(upper.begin(), upper.end(), upper.begin(), [](unsigned char ch) {
                return static_cast<char>(std::toupper(ch));
            });

            if (upper.find("COLZ") != std::string::npos) return "f";

            const bool hasLine   = upper.find('L') != std::string::npos
                                || upper.find("HIST") != std::string::npos;
            const bool hasMarker = upper.find('P') != std::string::npos;
            const bool hasFill   = source.style.fill.style != 0
                                && upper.find("HIST") != std::string::npos;

            std::string opt;
            if (hasLine)   opt += 'l';
            if (hasMarker) opt += 'p';
            if (hasFill)   opt += 'f';
            return opt.empty() ? "lp" : opt;
        }

        inline bool containsSame(const std::string& option) {
            std::string upper = option;
            std::transform(upper.begin(), upper.end(), upper.begin(), [](unsigned char ch) {
                return static_cast<char>(std::toupper(ch));
            });
            return upper.find("SAME") != std::string::npos;
        }

        inline void applyToSource(ResolvedSource& source) {
            for (const auto& [kind, entry] : kindRegistry()) {
                if (kind == source.kind) {
                    entry.applyStyle(source.object, source.style);
                    return;
                }
            }
        }

        inline void drawSource(ResolvedSource& source, const std::string& option) {
            for (const auto& [kind, entry] : kindRegistry()) {
                if (kind == source.kind) {
                    entry.draw(source.object, option);
                    return;
                }
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
            stats->SetFillColor(source.style.stats.fillColor);
            stats->SetFillStyle(source.style.stats.fillStyle);
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

                // Stack each source's stats box vertically so they don't overwrite each other.
                const double stride = source.style.stats.height + 0.02;
                const double y2     = source.style.stats.y - static_cast<double>(i) * stride;
                if (TH1* hist = dynamic_cast<TH1*>(source.object); hist != nullptr
                        && source.style.stats.show) {
                    canvas.Update();
                    if (TPaveStats* stats = dynamic_cast<TPaveStats*>(hist->FindObject("stats"))) {
                        stats->SetX2NDC(source.style.stats.x);
                        stats->SetY2NDC(y2);
                        stats->SetX1NDC(source.style.stats.x - source.style.stats.width);
                        stats->SetY1NDC(y2 - source.style.stats.height);
                        stats->SetTextFont(source.style.stats.textFont);
                        stats->SetTextSize(source.style.stats.textSize);
                        stats->SetBorderSize(source.style.stats.borderSize);
                        stats->SetLineColor(source.style.line.color);
                        stats->SetFillColor(source.style.stats.fillColor);
                        stats->SetFillStyle(source.style.stats.fillStyle);
                        canvas.Modified();
                        canvas.Update();
                    }
                }

                if (legend && !source.label.empty()) {
                    const std::string legOpt = legendOption(source, defaultDrawOption(source));
                    legend->AddEntry(source.object, source.label.c_str(), legOpt.c_str());
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
        const Bool_t wasBatch = gROOT->IsBatch();
        gROOT->SetBatch(kTRUE);
        struct BatchRestore { Bool_t prev; ~BatchRestore() { gROOT->SetBatch(prev); } } guard{wasBatch};
        for (RenderResult& result : plan.results) {
            renderResult(result);
        }
    }

} // namespace Paint
