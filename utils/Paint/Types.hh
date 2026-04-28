#pragma once

#include <string>

#include "TColor.h"

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

    struct PadLayout { Int_t rows{1}; Int_t cols{1}; };
}
