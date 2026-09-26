#pragma once
// utils/Apps/Paint/Draw.hh — loading series from ROOT files, and drawing a page with ROOT.
//
// Curves are step histograms, drawn per run of non-void bins, so a voided bin is a gap rather than a
// drop to zero. Data are points with x bars. The optional ratio pad divides each curve by the
// reference: the data when there are any, otherwise the first curve. Curves are rebinned onto the
// reference bins, which the alignment guarantees are MC edges.

#include "Page.hh"
#include "Transform.hh"

#include "TCanvas.h"
#include "TColor.h"
#include "TFile.h"
#include "TGraphAsymmErrors.h"
#include "TH1.h"
#include "TH1D.h"
#include "TLatex.h"
#include "TLegend.h"
#include "TLine.h"
#include "TPad.h"
#include "TROOT.h"
#include "TStyle.h"
#include "TSystem.h"

#include <limits>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace Paint {

    // ── loading ──────────────────────────────────────────────────────────────────────────────

    inline Series load(const Source& source, bool data) {
        std::unique_ptr<TFile> file(TFile::Open(source.file.c_str(), "READ"));
        if (!file || file->IsZombie()) throw std::runtime_error("cannot open " + source.file);
        TObject* object = file->Get(source.object.c_str());
        if (!object) throw std::runtime_error(source.file + " has no " + source.object);
        Series s;
        s.label = source.label;
        s.data = data;
        if (auto* h = dynamic_cast<TH1*>(object)) {
            for (int i = 1; i <= h->GetNbinsX(); ++i) {
                s.lo.push_back(h->GetXaxis()->GetBinLowEdge(i));
                s.hi.push_back(h->GetXaxis()->GetBinUpEdge(i));
                s.y.push_back(h->GetBinContent(i));
                s.err.push_back(h->GetBinError(i));
            }
        } else if (auto* g = dynamic_cast<TGraphAsymmErrors*>(object)) {
            for (int i = 0; i < g->GetN(); ++i) {
                s.lo.push_back(g->GetX()[i] - g->GetErrorXlow(i));
                s.hi.push_back(g->GetX()[i] + g->GetErrorXhigh(i));
                s.y.push_back(g->GetY()[i]);
                s.err.push_back(0.5 * (g->GetErrorYlow(i) + g->GetErrorYhigh(i)));
            }
        } else {
            throw std::runtime_error(source.object + " in " + source.file + " is neither a TH1 nor a TGraphAsymmErrors");
        }
        if (!source.raw.empty()) {                     // per-bin raw entries, for min_entries voiding
            auto* entries = dynamic_cast<TH1*>(file->Get((source.raw + "__entries").c_str()));
            if (!entries) throw std::runtime_error(source.file + " has no " + source.raw + "__entries (convert with --keep-raw)");
            for (int i = 1; i <= entries->GetNbinsX(); ++i) s.raw.push_back(entries->GetBinContent(i));
        }
        return s;
    }

    // ── style ────────────────────────────────────────────────────────────────────────────────

    // "kBlue+1", "kRed-4", "#aa3377", or a number.
    inline int colour(const std::string& name) {
        if (!name.empty() && name[0] == '#') return TColor::GetColor(name.c_str());
        static const std::map<std::string, int> base{
            {"kWhite", 0}, {"kBlack", 1}, {"kGray", 920}, {"kRed", 632}, {"kGreen", 416}, {"kBlue", 600},
            {"kYellow", 400}, {"kMagenta", 616}, {"kCyan", 432}, {"kOrange", 800}, {"kSpring", 820},
            {"kTeal", 840}, {"kAzure", 860}, {"kViolet", 880}, {"kPink", 900}};
        const size_t sign = name.find_first_of("+-");
        const std::string head = name.substr(0, sign);
        const auto it = base.find(head);
        if (it == base.end()) {
            try {
                return std::stoi(name);
            } catch (...) {
                throw std::runtime_error("unknown colour '" + name + "'");
            }
        }
        return it->second + (sign == std::string::npos ? 0 : std::stoi(name.substr(sign)));
    }

    // ── drawing ──────────────────────────────────────────────────────────────────────────────

    struct Keep {                                      // what is drawn must outlive the saves; declared
                                                       // before the canvas, so it is freed after it
        std::vector<std::unique_ptr<TObject>> objects;
        template <class T>
        T* hold(T* object) {
            objects.emplace_back(object);
            return object;
        }
    };

    // One TH1D per run of finite bins: a voided bin is a gap.
    inline std::vector<TH1D*> segments(const Series& s, Keep& keep, const std::string& id) {
        std::vector<TH1D*> out;
        size_t i = 0;
        while (i < s.size()) {
            if (!std::isfinite(s.y[i])) { ++i; continue; }
            size_t j = i;
            while (j < s.size() && std::isfinite(s.y[j]) && (j == i || close(s.lo[j], s.hi[j - 1]))) ++j;
            std::vector<double> edges(s.lo.begin() + i, s.lo.begin() + j);
            edges.push_back(s.hi[j - 1]);
            auto* h = keep.hold(new TH1D((id + "_" + std::to_string(i)).c_str(), "", static_cast<int>(edges.size()) - 1, edges.data()));
            h->SetDirectory(nullptr);
            for (size_t k = i; k < j; ++k) {
                h->SetBinContent(static_cast<int>(k - i + 1), s.y[k]);
                h->SetBinError(static_cast<int>(k - i + 1), s.err[k]);
            }
            out.push_back(h);
            i = j;
        }
        return out;
    }

    inline TGraphAsymmErrors* points(const Series& s, Keep& keep, double scale = 1.0, const Series* per = nullptr) {
        auto* g = keep.hold(new TGraphAsymmErrors());
        int n = 0;
        for (size_t i = 0; i < s.size(); ++i) {
            double y = s.y[i], e = s.err[i];
            if (per) {
                if (!(per->y[i] != 0.0) || !std::isfinite(per->y[i])) continue;
                y /= per->y[i], e /= per->y[i];
            }
            if (!std::isfinite(y)) continue;
            const double x = 0.5 * (s.lo[i] + s.hi[i]);
            g->SetPoint(n, x, y * scale);
            g->SetPointError(n, x - s.lo[i], s.hi[i] - x, e * scale, e * scale);
            ++n;
        }
        return g;
    }

    inline void legendBox(const std::string& where, double& x1, double& y1, double& x2, double& y2, size_t entries) {
        const double h = std::min(0.06 * static_cast<double>(entries) + 0.02, 0.45);
        if (where == "top-left") x1 = 0.16, x2 = 0.52, y2 = 0.88, y1 = y2 - h;
        else if (where == "bottom-right") x1 = 0.55, x2 = 0.9, y1 = 0.15, y2 = y1 + h;
        else if (where == "bottom-left") x1 = 0.16, x2 = 0.52, y1 = 0.15, y2 = y1 + h;
        else if (where == "top-right") x1 = 0.55, x2 = 0.9, y2 = 0.88, y1 = y2 - h;
        else throw std::runtime_error("legend must be top-right, top-left, bottom-right or bottom-left, not '" + where + "'");
    }

    struct RatioRange {
        double lo, hi;
    };

    // The ratio pad shows at least 0.5–1.5, widened to the ratios drawn, within 0–3: a curve far from
    // the reference (another beam energy against the data) is on the pad, one wild bin cannot flatten it.
    inline RatioRange ratioRange(const std::vector<std::pair<size_t, Series>>& ratios, Range x) {
        double lo = 0.5, hi = 1.5;
        for (const auto& [c, s] : ratios)
            for (size_t i = 0; i < s.size(); ++i)
                if (std::isfinite(s.y[i]) && s.hi[i] > x.lo && s.lo[i] < x.hi)
                    lo = std::min(lo, 0.9 * (s.y[i] - s.err[i])), hi = std::max(hi, 1.1 * (s.y[i] + s.err[i]));
        return {std::max(lo, 0.0), std::min(hi, 3.0)};
    }

    inline void draw(const Page& page, std::vector<Series>& curves, Series* data, Range x, YRange y) {
        gROOT->SetBatch(kTRUE);
        gStyle->SetOptStat(0);
        gStyle->SetOptTitle(0);
        Keep keep;
        const double textSize = page.fontSize / static_cast<double>(page.height) * 1.9;
        TCanvas canvas("paint", page.name.c_str(), page.width, page.height);
        TPad* top = &canvas;
        TPad* bottom = nullptr;
        if (page.ratio) {
            top = new TPad("top", "", 0, 0.3, 1, 1);           // the canvas owns its pads
            bottom = new TPad("bottom", "", 0, 0, 1, 0.3);
            top->SetBottomMargin(0.02);
            bottom->SetTopMargin(0.03);
            bottom->SetBottomMargin(0.32);
            for (TPad* p : {top, bottom}) p->SetLeftMargin(0.13), p->SetRightMargin(0.04), p->Draw();
        } else {
            canvas.SetLeftMargin(0.13), canvas.SetRightMargin(0.04), canvas.SetBottomMargin(0.12);
        }

        top->cd();
        top->SetLogx(page.logx);
        top->SetLogy(page.logy);
        TH1F* frame = top->DrawFrame(x.lo, y.lo, x.hi, y.hi);
        frame->GetYaxis()->SetTitle(page.yLabel.c_str());
        frame->GetXaxis()->SetTitle(page.ratio ? "" : page.xLabel.c_str());
        frame->GetYaxis()->SetTitleSize(textSize), frame->GetYaxis()->SetLabelSize(textSize * 0.85);
        frame->GetXaxis()->SetTitleSize(textSize), frame->GetXaxis()->SetLabelSize(page.ratio ? 0 : textSize * 0.85);
        frame->GetYaxis()->SetTitleOffset(1.1);

        double lx1, ly1, lx2, ly2;
        legendBox(page.legend, lx1, ly1, lx2, ly2, curves.size() + (data ? 1 : 0) + (page.title.empty() ? 0 : 1));
        auto* legend = keep.hold(new TLegend(lx1, ly1, lx2, ly2));
        legend->SetBorderSize(0), legend->SetFillStyle(0), legend->SetTextSize(textSize * 0.8);
        if (!page.title.empty()) legend->SetHeader(page.title.c_str());

        for (size_t c = 0; c < curves.size(); ++c) {
            const int colourIndex = colour(page.palette[c % page.palette.size()]);
            bool first = true;
            for (TH1D* h : segments(curves[c], keep, "c" + std::to_string(c))) {
                h->SetLineColor(colourIndex), h->SetLineWidth(2), h->SetMarkerSize(0);
                h->Draw("HIST SAME");
                auto* errors = static_cast<TH1D*>(keep.hold(h->Clone()));
                errors->SetFillColorAlpha(colourIndex, 0.25), errors->SetLineWidth(0);
                errors->Draw("E2 SAME");
                if (first) legend->AddEntry(h, curves[c].label.c_str(), "l"), first = false;
            }
            if (first)                                 // every bin voided: listed, not drawn
                legend->AddEntry(static_cast<TObject*>(nullptr), (curves[c].label + " (no entries)").c_str(), "");
        }
        if (data) {
            auto* g = points(*data, keep);
            g->SetMarkerStyle(20), g->SetMarkerSize(0.9), g->SetLineColor(kBlack);
            g->Draw("P SAME");
            legend->AddEntry(g, data->label.c_str(), "pe");
        }
        legend->Draw();
        top->RedrawAxis();

        if (bottom) {
            bottom->cd();
            bottom->SetLogx(page.logx);
            const Series& reference = data ? *data : curves.front();
            std::vector<std::pair<size_t, Series>> ratios;     // each curve over the reference, on its bins
            for (size_t c = 0; c < curves.size(); ++c) {
                if (!data && c == 0) continue;
                Series ratio = reference;
                for (size_t i = 0; i < reference.size(); ++i) {
                    const auto [value, error] = rebinned(curves[c], reference.lo[i], reference.hi[i]);
                    const bool ok = std::isfinite(value) && std::isfinite(reference.y[i]) && reference.y[i] != 0.0;
                    ratio.y[i] = ok ? value / reference.y[i] : std::numeric_limits<double>::quiet_NaN();
                    ratio.err[i] = ok ? error / std::fabs(reference.y[i]) : 0.0;
                }
                ratios.emplace_back(c, ratio);
            }
            const RatioRange r = ratioRange(ratios, x);
            TH1F* rframe = bottom->DrawFrame(x.lo, r.lo, x.hi, r.hi);
            rframe->GetXaxis()->SetTitle(page.xLabel.c_str());
            rframe->GetYaxis()->SetTitle(page.ratioLabel.c_str());
            const double rsize = textSize * 0.7 / 0.3;
            rframe->GetXaxis()->SetTitleSize(rsize), rframe->GetXaxis()->SetLabelSize(rsize * 0.85);
            rframe->GetYaxis()->SetTitleSize(rsize), rframe->GetYaxis()->SetLabelSize(rsize * 0.85);
            rframe->GetYaxis()->SetTitleOffset(0.45), rframe->GetYaxis()->SetNdivisions(505);
            if (data) {                                // the reference's own error, as a band
                auto* band = points(reference, keep, 1.0, &reference);
                band->SetFillColor(kGray), band->Draw("2 SAME");
            }
            auto* one = keep.hold(new TLine(x.lo, 1, x.hi, 1));
            one->SetLineStyle(2), one->Draw();
            for (auto& [c, ratio] : ratios) {
                auto* g = points(ratio, keep);
                const int colourIndex = colour(page.palette[c % page.palette.size()]);
                g->SetLineColor(colourIndex), g->SetMarkerColor(colourIndex), g->SetMarkerStyle(20 + static_cast<int>(c) % 4),
                    g->SetMarkerSize(0.6);
                g->Draw("P SAME");
            }
            bottom->RedrawAxis();
        }

        const std::string dir = gSystem->GetDirName(page.output.c_str()).Data();
        gSystem->mkdir(dir.c_str(), kTRUE);
        for (const auto& format : page.formats) {
            if (format != "pdf" && format != "png" && format != "svg" && format != "eps")
                throw std::runtime_error("format must be pdf, png, svg or eps, not '" + format + "'");
            canvas.SaveAs((page.output + "." + format).c_str());
        }
    }

}  // namespace Paint
