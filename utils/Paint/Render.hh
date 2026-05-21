#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
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

        inline double positiveScale(double value) {
            return value > 0.0 ? value : 1.0;
        }

        template <typename T>
        inline T scaleIntegralSize(T value, double scale) {
            if (value == 0) return value;
            const long scaled = std::lround(static_cast<double>(value) * scale);
            if (value > 0) return static_cast<T>(std::max<long>(1, scaled));
            return static_cast<T>(scaled);
        }

        inline Style scaledStyle(Style style, const RenderResult& result) {
            const double imageScale = static_cast<double>(std::max(1, result.imageScale));
            const double textScale = imageScale * positiveScale(result.textScale);
            const double brushScale = imageScale * positiveScale(result.brushScale);

            style.axis.titleSize = static_cast<Float_t>(style.axis.titleSize * textScale);
            style.axis.labelSize = static_cast<Float_t>(style.axis.labelSize * textScale);
            style.stats.textSize = static_cast<Float_t>(style.stats.textSize * textScale);
            style.legend.textSize = static_cast<Float_t>(style.legend.textSize * textScale);
            style.titleBox.textSize = static_cast<Float_t>(style.titleBox.textSize * textScale);

            style.line.width = scaleIntegralSize(style.line.width, brushScale);
            style.marker.size = static_cast<Float_t>(style.marker.size * brushScale);
            style.stats.borderSize = scaleIntegralSize(style.stats.borderSize, brushScale);
            style.legend.borderSize = scaleIntegralSize(style.legend.borderSize, brushScale);
            style.titleBox.borderSize = scaleIntegralSize(style.titleBox.borderSize, brushScale);

            return style;
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

        inline void applyToSource(ResolvedSource& source, const Style& style) {
            for (const auto& [kind, entry] : kindRegistry()) {
                if (kind == source.kind) {
                    entry.applyStyle(source.object, style);
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

        inline void applyStatsBox(ResolvedSource& source, TPad* pad, const Style& style) {
            if (pad == nullptr || !style.stats.show) return;
            TH1* hist = dynamic_cast<TH1*>(source.object);
            if (hist == nullptr) return;

            pad->Update();
            TPaveStats* stats = dynamic_cast<TPaveStats*>(hist->FindObject("stats"));
            if (stats == nullptr) return;

            stats->SetX2NDC(style.stats.x);
            stats->SetY2NDC(style.stats.y);
            stats->SetX1NDC(style.stats.x - style.stats.width);
            stats->SetY1NDC(style.stats.y - style.stats.height);
            stats->SetTextFont(style.stats.textFont);
            stats->SetTextSize(style.stats.textSize);
            stats->SetBorderSize(style.stats.borderSize);
            stats->SetFillColor(style.stats.fillColor);
            stats->SetFillStyle(style.stats.fillStyle);
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

        inline void drawOneOnPad(ResolvedSource& source, TPad* pad, const RenderResult& result) {
            const Style style = scaledStyle(source.style, result);
            configurePad(pad, style);
            if (pad != nullptr) pad->cd();
            applyGlobalStyle(style);
            setSourceTitle(source);
            drawSource(source, defaultDrawOption(source));
            // Apply per-source style AFTER Draw(): gROOT->ForceStyle() (armed by
            // applyGlobalStyle) fires inside TObject::AppendPad during Draw() and
            // calls UseCurrentStyle(), which resets line/marker colors to gStyle
            // defaults.  Setting them again here survives that reset.
            applyToSource(source, style);
            applyStatsBox(source, pad, style);
            applyTitleBox(pad, style);
        }

        inline void drawSingle(RenderResult& result, TCanvas& canvas) {
            drawOneOnPad(result.sources.front(), &canvas, result);
        }

        inline void drawGrid(RenderResult& result, TCanvas& canvas) {
            canvas.Divide(result.cols, result.rows);
            for (std::size_t i = 0; i < result.sources.size(); ++i) {
                TPad* pad = dynamic_cast<TPad*>(canvas.cd(static_cast<Int_t>(i + 1)));
                drawOneOnPad(result.sources[i], pad, result);
            }
            canvas.cd();
        }

        inline void drawOverlay(RenderResult& result, TCanvas& canvas) {
            const Style resultStyle = scaledStyle(result.style, result);
            configurePad(&canvas, resultStyle);
            canvas.cd();
            applyGlobalStyle(resultStyle);

            const bool hasLabels = std::any_of(result.sources.begin(), result.sources.end(), [](const ResolvedSource& source) {
                return !source.label.empty();
            });

            std::unique_ptr<TLegend> legend;
            if (resultStyle.legend.show || hasLabels) {
                legend = std::make_unique<TLegend>(
                    resultStyle.legend.x1, resultStyle.legend.y1,
                    resultStyle.legend.x2, resultStyle.legend.y2);
                legend->SetTextFont(resultStyle.legend.textFont);
                legend->SetTextSize(resultStyle.legend.textSize);
                legend->SetBorderSize(resultStyle.legend.borderSize);
                legend->SetFillStyle(resultStyle.legend.fillStyle);
            }

            for (std::size_t i = 0; i < result.sources.size(); ++i) {
                ResolvedSource& source = result.sources[i];
                const Style sourceStyle = scaledStyle(source.style, result);
                setSourceTitle(source);

                std::string option = defaultDrawOption(source);
                if (i > 0 && !containsSame(option)) option += " SAME";
                drawSource(source, option);
                // Apply per-source style (palette colors, line width, etc.) AFTER
                // Draw() so ROOT's ForceStyle/UseCurrentStyle cannot overwrite them.
                applyToSource(source, sourceStyle);

                // Stack each source's stats box vertically so they don't overwrite each other.
                const double stride = sourceStyle.stats.height + 0.02;
                const double y2     = sourceStyle.stats.y - static_cast<double>(i) * stride;
                if (TH1* hist = dynamic_cast<TH1*>(source.object); hist != nullptr
                        && sourceStyle.stats.show) {
                    canvas.Update();
                    if (TPaveStats* stats = dynamic_cast<TPaveStats*>(hist->FindObject("stats"))) {
                        stats->SetX2NDC(sourceStyle.stats.x);
                        stats->SetY2NDC(y2);
                        stats->SetX1NDC(sourceStyle.stats.x - sourceStyle.stats.width);
                        stats->SetY1NDC(y2 - sourceStyle.stats.height);
                        stats->SetTextFont(sourceStyle.stats.textFont);
                        stats->SetTextSize(sourceStyle.stats.textSize);
                        stats->SetBorderSize(sourceStyle.stats.borderSize);
                        stats->SetLineColor(sourceStyle.line.color);
                        stats->SetFillColor(sourceStyle.stats.fillColor);
                        stats->SetFillStyle(sourceStyle.stats.fillStyle);
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
