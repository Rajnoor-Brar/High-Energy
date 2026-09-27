#pragma once
// utils/Apps/Paint/Draw.hh — loading series from ROOT files, and drawing a page with ROOT.
//
// The look is rivet-mkhtml's (see "the look" below). Curves are steps, drawn per run of non-void
// bins, so a voided bin is a gap rather than a drop to zero. Data are points with x bars. The
// optional ratio pad divides each curve by the reference: the data when there are any, otherwise
// the first curve. Curves are rebinned onto the reference bins, which the alignment guarantees are
// MC edges.

#include "Page.hh"
#include "Transform.hh"

#include "TCanvas.h"
#include "TColor.h"
#include "TFile.h"
#include "TGraphAsymmErrors.h"
#include "TH1.h"
#include "TH1D.h"
#include "TLatex.h"
#include "TMarker.h"
#include "TLine.h"
#include "TPad.h"
#include "TROOT.h"
#include "TStyle.h"
#include "TSystem.h"

#include <algorithm>
#include <cmath>
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

    // Points at the bin centres, x bars optional; `per` divides by a series on the same bins.
    inline TGraphAsymmErrors* points(const Series& s, Keep& keep, bool xbars, const Series* per = nullptr) {
        auto* g = keep.hold(new TGraphAsymmErrors());
        int n = 0;
        for (size_t i = 0; i < s.size(); ++i) {
            double y = s.y[i], e = s.err[i];
            if (per) {
                if (!(per->y[i] != 0.0) || !std::isfinite(per->y[i])) continue;
                y /= per->y[i], e /= std::fabs(per->y[i]);
            }
            if (!std::isfinite(y)) continue;
            const double x = 0.5 * (s.lo[i] + s.hi[i]);
            g->SetPoint(n, x, y);
            g->SetPointError(n, xbars ? x - s.lo[i] : 0.0, xbars ? s.hi[i] - x : 0.0, e, e);
            ++n;
        }
        return g;
    }

    // ── the look: rivet-mkhtml's (its default.mplstyle) ──────────────────────────────────────
    //
    // The page is mkhtml's, 4.67 in wide whatever its pixels: sizes are points of that page, and a
    // PDF comes out at its size. Serif text sized in pixels (one size in both pads), ticks inside on
    // all four sides, the x title at the right end and the y title at the top, a frameless legend
    // with a "+" beside each entry, MC as steps with bars at the bin centres over black data points,
    // and a ratio pad of a third of the axes with no gap.

    struct Look {
        double px, text, label, tick;                     // pixels per point; the rest in pixels
        int width, font = 133;                            // Times, precision 3: sized in pixels
        explicit Look(const Page& page)
            : px(page.width / 336.0), text(page.fontSize * px), label(0.8 * text), tick(6.0 * px),
              width(std::max(1, static_cast<int>(std::lround(px)))) {}
    };

    struct Frame {                                        // a pad in pixels, its margins in NDC
        double w, h, l, r, b, t;
        double fw() const { return w * (1 - l - r); }
        double fh() const { return h * (1 - b - t); }
    };

    inline void style(TH1F* frame, const Look& look, const Frame& f, bool xText) {
        TAxis* ax = frame->GetXaxis();
        TAxis* ay = frame->GetYaxis();
        for (TAxis* a : {ax, ay}) {
            a->SetTitleFont(look.font), a->SetLabelFont(look.font);
            a->SetTitleSize(look.text), a->SetLabelSize(look.label);
        }
        ax->SetTickLength(look.tick / f.fh()), ay->SetTickLength(look.tick / f.fw());
        ax->SetLabelOffset(2.5 * look.px / f.h), ay->SetLabelOffset(2.5 * look.px / f.w);
        ax->SetTitleOffset(1.0), ay->SetTitleOffset(1.55);
        if (!xText) ax->SetLabelSize(0), ax->SetTitleSize(0);
    }

    // Steps per run of finite bins, with the bars at the centres.
    inline void curve(const Series& s, int colourIndex, const Look& look, Keep& keep, const std::string& id) {
        for (TH1D* h : segments(s, keep, id)) {
            h->SetLineColor(colourIndex), h->SetLineWidth(look.width);
            h->Draw("HIST ][ SAME");                    // ][: a run does not drop to the axis at its ends
        }
        auto* bars = points(s, keep, false);
        bars->SetLineColor(colourIndex), bars->SetLineWidth(look.width), bars->SetMarkerSize(0);
        bars->Draw("PZ");
    }

    inline void dataPoints(const Series& s, const Look& look, Keep& keep, const Series* per = nullptr) {
        auto* g = points(s, keep, true, per);
        g->SetLineColor(kBlack), g->SetLineWidth(look.width);
        g->SetMarkerStyle(20), g->SetMarkerColor(kBlack), g->SetMarkerSize(static_cast<float>(0.25 * look.px));
        g->Draw("PZ");
    }

    struct Entry {
        std::string label;
        int colour;
        bool data, drawn;
    };

    // mkhtml's legend: no frame, the title as its header, and a "+" beside each entry — on the right
    // of right-aligned text, on the left of left-aligned text. Data come first, as in mkhtml.
    inline void legend(const std::string& where, const std::string& title, const std::vector<Entry>& entries,
                       const Look& look, const Frame& f, Keep& keep) {
        if (where != "top-right" && where != "top-left" && where != "bottom-right" && where != "bottom-left")
            throw std::runtime_error("legend must be top-right, top-left, bottom-right or bottom-left, not '" + where + "'");
        const bool right = where.find("right") != std::string::npos, top = where.find("top") != std::string::npos;
        const double dy = 1.2 * look.text / f.h, sw = 1.6 * look.text / f.w, gap = 0.5 * look.text / f.w;
        const double inset = 0.5 * look.text;
        const double lines = static_cast<double>(entries.size() + (title.empty() ? 0 : 1));
        const double x0 = right ? 1 - f.r - inset / f.w : f.l + inset / f.w;       // the outer edge
        double y = top ? 1 - f.t - inset / f.h - 0.5 * dy : f.b + inset / f.h + (lines - 0.5) * dy;
        auto text = [&](double x, double at, const std::string& s, int align) {
            auto* t = keep.hold(new TLatex(x, at, s.c_str()));
            t->SetNDC(), t->SetTextFont(look.font), t->SetTextSize(look.text), t->SetTextAlign(align), t->Draw();
        };
        auto line = [&](double x1, double y1, double x2, double y2, int colourIndex) {
            auto* l = keep.hold(new TLine(x1, y1, x2, y2));
            l->SetNDC(), l->SetLineColor(colourIndex), l->SetLineWidth(look.width), l->Draw();
        };
        if (!title.empty()) text(x0, y, title, right ? 32 : 12), y -= dy;
        for (const auto& e : entries) {
            const double s1 = right ? x0 - sw : x0, s2 = right ? x0 : x0 + sw, xc = 0.5 * (s1 + s2);
            if (e.drawn) {
                line(s1, y, s2, y, e.colour);
                line(xc, y - 0.4 * dy, xc, y + 0.4 * dy, e.colour);
                if (e.data) {
                    auto* m = keep.hold(new TMarker(xc, y, 20));
                    m->SetNDC(), m->SetMarkerColor(e.colour), m->SetMarkerSize(static_cast<float>(0.25 * look.px)), m->Draw();
                }
            }
            text(right ? s1 - gap : s2 + gap, y, e.label, right ? 32 : 12);
            y -= dy;
        }
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
        gStyle->SetOptStat(0), gStyle->SetOptTitle(0), gStyle->SetEndErrorSize(0), gStyle->SetFrameLineWidth(1);
        const double cm = 4.67 * 2.54;                                         // mkhtml's page width
        gStyle->SetPaperSize(static_cast<float>(cm), static_cast<float>(cm * page.height / page.width));
        const Look look(page);
        Keep keep;
        TCanvas canvas("paint", page.name.c_str(), page.width, page.height);
        canvas.SetCanvasSize(page.width, page.height);

        // mkhtml's margins (left .125, right .032, top .066, bottom .092 of the page), a little wider
        // at the left and bottom for ROOT's titles; with a ratio the axes split 2:1 with no gap
        const double W = page.width, H = page.height, left = 0.16, right = 0.032, topM = 0.066, bottomM = 0.11;
        Frame ft{W, H, left, right, bottomM, topM}, fb{};
        TPad* top = &canvas;
        TPad* bottom = nullptr;
        if (page.ratio) {
            const double split = bottomM + (1 - topM - bottomM) / 3.0;
            top = new TPad("top", "", 0, split, 1, 1);                         // the canvas owns its pads
            bottom = new TPad("bottom", "", 0, 0, 1, split);
            ft = {W, H * (1 - split), left, right, 0.0, topM / (1 - split)};
            fb = {W, H * split, left, right, bottomM / split, 0.0};
            bottom->SetMargin(fb.l, fb.r, fb.b, fb.t);
            for (TPad* p : {top, bottom}) p->SetFillStyle(0), p->SetBorderMode(0), p->Draw();
        }
        top->SetMargin(ft.l, ft.r, ft.b, ft.t);
        for (TPad* p : {top, bottom})
            if (p) p->SetTickx(1), p->SetTicky(1), p->SetLogx(page.logx);

        top->cd();
        top->SetLogy(page.logy);
        TH1F* frame = top->DrawFrame(x.lo, y.lo, x.hi, y.hi);
        style(frame, look, ft, !page.ratio);
        frame->GetYaxis()->SetTitle(page.yLabel.c_str());
        frame->GetXaxis()->SetTitle(page.ratio ? "" : page.xLabel.c_str());
        if (page.ratio && !page.logy && y.lo == 0.0) frame->GetYaxis()->ChangeLabel(1, -1, 0);   // the joint's "0"

        std::vector<Entry> entries;
        if (data) {
            dataPoints(*data, look, keep);
            entries.push_back({data->label, kBlack, true, true});
        }
        for (size_t c = 0; c < curves.size(); ++c) {
            const int colourIndex = colour(page.palette[c % page.palette.size()]);
            curve(curves[c], colourIndex, look, keep, "c" + std::to_string(c));
            const bool drawn = std::any_of(curves[c].y.begin(), curves[c].y.end(), [](double v) { return std::isfinite(v); });
            entries.push_back({drawn ? curves[c].label : curves[c].label + " (no entries)", colourIndex, false, drawn});
        }
        legend(page.legend, page.title, entries, look, ft, keep);
        top->RedrawAxis();

        if (bottom) {
            bottom->cd();
            const Series& reference = data ? *data : curves.front();
            std::vector<std::pair<size_t, Series>> ratios;     // each curve over the reference, on its bins
            for (size_t c = 0; c < curves.size(); ++c) {
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
            TH1F* rframe = bottom->DrawFrame(x.lo, r.lo, x.hi, r.hi - 1e-6 * (r.hi - r.lo));   // no label at the joint
            style(rframe, look, fb, true);
            rframe->GetXaxis()->SetTitle(page.xLabel.c_str());
            rframe->GetYaxis()->SetTitle(page.ratioLabel.c_str());
            rframe->GetYaxis()->SetNdivisions(508), rframe->GetYaxis()->SetDecimals();   // 1.0, as mkhtml
            if (data) dataPoints(reference, look, keep, &reference);          // the data at 1, with their errors
            for (auto& [c, ratio] : ratios)
                curve(ratio, colour(page.palette[c % page.palette.size()]), look, keep, "r" + std::to_string(c));
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
