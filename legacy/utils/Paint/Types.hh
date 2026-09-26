#pragma once

#include <functional>
#include <memory>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "TColor.h"
#include "TFile.h"
#include "TObject.h"

namespace Paint {

    enum class Mode { Single, Overlay, Grid };
    enum class ObjectKind { Hist1D, Hist2D, TProfile, Graph };

    struct LineSpec {
        Color_t color{kBlack};
        Width_t width{1};
        Style_t style{1};
    };

    struct FillSpec {
        Color_t color{0};
        Style_t style{0};
    };

    struct MarkerSpec {
        Color_t color{kBlack};
        Style_t style{20};
        Float_t size{1.0};
    };

    struct AxisSpec {
        Font_t titleFont{43};
        Font_t labelFont{43};
        Float_t titleSize{27.0};
        Float_t labelSize{20.0};
        Float_t offsetX{1.1};
        Float_t offsetY{1.35};
        Float_t offsetZ{1.1};
        bool centerTitles{true};
        Int_t maxDigitsY{3};
        std::string titleX{};
        std::string titleY{};
        std::string titleZ{};
    };

    struct CanvasSpec {
        Int_t width{900};
        Int_t height{600};
        Float_t marginL{0.12};
        Float_t marginR{0.05};
        Float_t marginB{0.12};
        Float_t marginT{0.08};
        bool ticksX{true};
        bool ticksY{true};
    };

    struct StatsSpec {
        bool show{true};
        std::string optStat{"emr"};
        Double_t x{0.92};
        Double_t y{0.89};
        Double_t width{0.18};
        Double_t height{0.10};
        Font_t textFont{43};
        Float_t textSize{12.0};
        Int_t borderSize{2};
        Color_t fillColor{0};
        Style_t fillStyle{1001};
    };

    struct LegendSpec {
        bool show{false};
        Double_t x1{0.65};
        Double_t y1{0.75};
        Double_t x2{0.88};
        Double_t y2{0.88};
        Font_t textFont{43};
        Float_t textSize{14.0};
        Int_t borderSize{0};
        Style_t fillStyle{0};
    };

    struct TitleBoxSpec {
        bool show{true};
        Font_t textFont{43};
        Float_t textSize{24.0};
        Int_t borderSize{0};
        Style_t fillStyle{0};
    };

    struct Style {
        LineSpec line{};
        FillSpec fill{};
        MarkerSpec marker{};
        AxisSpec axis{};
        CanvasSpec canvas{};
        StatsSpec stats{};
        LegendSpec legend{};
        TitleBoxSpec titleBox{};
        std::string drawOption{"HIST"};
        Double_t minimum{0.0};
        Double_t maximum{0.0};
        bool hasMinimum{false};
        bool hasMaximum{false};
        bool logX{false};
        bool logY{false};
        bool logZ{false};
        bool gridX{false};
        bool gridY{false};
    };

    struct KindEntry {
        std::function<bool(const TObject*)>              detect;
        std::string                                      rootClassName;
        std::function<void(TObject*, const Style&)>      applyStyle;
        std::function<void(TObject*, const std::string&)> draw;
        std::string                                      defaultDraw;
    };
    using KindRegistry = std::vector<std::pair<ObjectKind, KindEntry>>;

    struct PaintBook {
        std::string configPath{};
        std::string defaultStylePath{};
        toml::table config{};
    };

    struct ResolvedSource {
        std::string path{};
        std::string label{};
        std::string title{};
        std::string drawOption{};
        std::string rootClass{};
        ObjectKind kind{ObjectKind::Hist1D};
        Style style{};
        TObject* object{nullptr};
        std::unique_ptr<TObject> owned{};

        ResolvedSource() = default;
        ResolvedSource(ResolvedSource&&) noexcept = default;
        ResolvedSource& operator=(ResolvedSource&&) noexcept = default;
        ResolvedSource(const ResolvedSource&) = delete;
        ResolvedSource& operator=(const ResolvedSource&) = delete;
    };

    struct RenderResult {
        std::string name{};
        std::string outputName{};
        std::string title{};
        std::string resultDir{"results"};
        std::vector<std::string> formats{"png"};
        bool overwrite{true};
        int imageScale{1};
        double textScale{1.0};
        double brushScale{1.0};
        Mode mode{Mode::Single};
        bool modeExplicit{false};
        int rows{0};
        int cols{0};
        Style style{};
        std::vector<ResolvedSource> sources{};

        RenderResult() = default;
        RenderResult(RenderResult&&) noexcept = default;
        RenderResult& operator=(RenderResult&&) noexcept = default;
        RenderResult(const RenderResult&) = delete;
        RenderResult& operator=(const RenderResult&) = delete;
    };

    struct RenderPlan {
        std::string rootFile{};
        std::unique_ptr<TFile> file{};
        std::vector<RenderResult> results{};

        RenderPlan() = default;
        RenderPlan(RenderPlan&&) noexcept = default;
        RenderPlan& operator=(RenderPlan&&) noexcept = default;
        RenderPlan(const RenderPlan&) = delete;
        RenderPlan& operator=(const RenderPlan&) = delete;
    };

} // namespace Paint
