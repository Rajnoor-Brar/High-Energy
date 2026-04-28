#pragma once

#include <cstddef>
#include <stdexcept>
#include <string>
#include <vector>

#include "TCanvas.h"
#include "TH1.h"
#include "TPad.h"
#include "TSystem.h"

#include "Paint/Types.hh"
#include "Paint/Apply.hh"

namespace Paint {

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
                                  base.canvas.width  * layout.cols,
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
