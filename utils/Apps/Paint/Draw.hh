#pragma once
// utils/Apps/Paint/Draw.hh — loading series from ROOT files, and drawing a page with ROOT.
//
// The look is the page's style (Style.hh; utils/Apps/Paint/base.toml is rivet-mkhtml's). Curves are steps, drawn per run of non-void
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

    // ── the look: utils/Apps/Paint/base.toml (rivet-mkhtml's), as merged for the page ─────────
    //
    // Sizes in the style are points of the page (size, in inches); here they become pixels at the
    // style's dpi. Text is sized in pixels (ROOT's precision 3), so both pads share one text size.

    struct Look {
        const Style& s;
        double px, title, labels, legend, header, tick;   // pixels per point; the rest in pixels
        int width, font;
        explicit Look(const Style& style)
            : s(style), px(style.px()), title(style.title * px), labels(style.labels * px), legend(style.legend * px),
              header(style.header * px), tick(style.tick * px),
              width(std::max(1, static_cast<int>(std::lround(style.lineWidth * px)))), font(style.fontCode()) {}
        float marker() const { return static_cast<float>(s.markerSize * px / 8.0); }   // ROOT's size 1 is 8 px
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
            a->SetTitleSize(look.title), a->SetLabelSize(look.labels);
            a->CenterTitle(!look.s.atEnds);
        }
        ax->SetTickLength(look.tick / f.fh()), ay->SetTickLength(look.tick / f.fw());
        ax->SetLabelOffset(look.s.labelOffset * look.px / f.h), ay->SetLabelOffset(look.s.labelOffset * look.px / f.w);
        ax->SetTitleOffset(look.s.titleOffsetX), ay->SetTitleOffset(look.s.titleOffsetY);
        if (!xText) ax->SetLabelSize(0), ax->SetTitleSize(0);
    }

    // Steps per run of finite bins, with their errors as bars at the centres, a band, or nothing.
    inline void curve(const Series& s, int colourIndex, const Look& look, Keep& keep, const std::string& id) {
        for (TH1D* h : segments(s, keep, id)) {
            h->SetLineColor(colourIndex), h->SetLineWidth(look.width);
            h->Draw("HIST ][ SAME");                    // ][: a run does not drop to the axis at its ends
            if (look.s.errors == "band") {
                auto* band = static_cast<TH1D*>(keep.hold(h->Clone()));
                band->SetFillColorAlpha(colourIndex, 0.25), band->SetLineWidth(0), band->SetMarkerSize(0);
                band->Draw("E2 SAME");
            }
        }
        if (look.s.errors != "bars") return;
        auto* bars = points(s, keep, false);
        bars->SetLineColor(colourIndex), bars->SetLineWidth(look.width), bars->SetMarkerSize(0);
        bars->Draw("PZ");
    }

    inline void dataPoints(const Series& s, const Look& look, Keep& keep, const Series* per = nullptr) {
        const int c = colour(look.s.dataColour);
        auto* g = points(s, keep, look.s.xBars, per);
        g->SetLineColor(c), g->SetLineWidth(look.width);
        g->SetMarkerStyle(look.s.marker), g->SetMarkerColor(c), g->SetMarkerSize(look.marker());
        g->Draw("PZ");
    }

    struct Entry {
        std::string label;
        int colour;
        bool data, drawn;
    };

    // mkhtml's legend: no frame, the title as its header, and a "+" beside each entry — on the right
    // of right-aligned text, on the left of left-aligned text. Data come first, as in mkhtml. A
    // corner is inset from the frame's; [x, y] places the top-right corner in fractions of the frame.
    // Where the drawn points are, in the frame's NDC: each bin's centre at its value, for "best".
    struct Placed { std::vector<std::pair<double, double>> points; };

    inline Placed placed(const std::vector<const Series*>& drawn, Range x, Range y, bool logx, bool logy, const Frame& f) {
        auto at = [](double v, Range r, bool log) {
            return log ? (std::log10(v) - std::log10(r.lo)) / (std::log10(r.hi) - std::log10(r.lo)) : (v - r.lo) / (r.hi - r.lo);
        };
        Placed out;
        for (const Series* series : drawn)
            for (size_t i = 0; i < series->size(); ++i) {
                const double xc = 0.5 * (series->lo[i] + series->hi[i]), v = series->y[i];
                if (!std::isfinite(v) || (logy && v <= 0) || (logx && xc <= 0)) continue;
                out.points.push_back({f.l + at(xc, x, logx) * (1 - f.l - f.r), f.b + at(v, y, logy) * (1 - f.b - f.t)});
            }
        return out;
    }

    inline void legend(const std::string& title, const std::vector<Entry>& entries, const Look& look, const Frame& f,
                       Keep& keep, const Placed& under = {}) {
        const Style& s = look.s;
        std::string corner = s.corner;
        if (corner == "best") {                       // the corner with the fewest drawn points under the legend
            size_t longest = title.size();
            for (const auto& e : entries) longest = std::max(longest, e.label.size());
            const double width = (s.symbol + s.gap) * look.px / f.w + 0.5 * longest * look.legend / f.w;
            const double rows = static_cast<double>(entries.size()) + (title.empty() ? 0.0 : 1.0);
            const double height = rows * s.spacing * look.legend / f.h;
            const double ix = s.insetX * look.px / f.w, iy = s.insetY * look.px / f.h;
            size_t fewest = std::numeric_limits<size_t>::max();
            for (const std::string option : {"top-right", "top-left", "bottom-right", "bottom-left"}) {
                const bool r = option.find("right") != std::string::npos, t = option.find("top") != std::string::npos;
                const double x1 = r ? 1 - f.r - ix : f.l + ix + width, x0 = x1 - width;
                const double y1 = t ? 1 - f.t - iy : f.b + iy + height, y0 = y1 - height;
                const size_t n = std::count_if(under.points.begin(), under.points.end(), [&](const auto& p) {
                    return p.first >= x0 && p.first <= x1 && p.second >= y0 && p.second <= y1; });
                if (n < fewest) fewest = n, corner = option;
            }
        }
        const bool right = corner.find("right") != std::string::npos, top = corner.find("top") != std::string::npos;
        const double dy = s.spacing * look.legend / f.h, sw = s.symbol * look.px / f.w, gap = s.gap * look.px / f.w;
        const double ix = s.insetX * look.px / f.w, iy = s.insetY * look.px / f.h;
        size_t rows = 1;                                                                // #splitline{a}{b}: two
        for (auto at = title.find("#splitline"); at != std::string::npos; at = title.find("#splitline", at + 1)) ++rows;
        const double first = title.empty() ? 0.0 : rows * s.spacing * look.header / f.h;   // the header's pitch
        const double height = first + static_cast<double>(entries.size()) * dy;
        double x0, yTop;                                                                // the outer edge, the top
        if (s.placed) {
            x0 = f.l + s.atX * (1 - f.l - f.r), yTop = f.b + s.atY * (1 - f.b - f.t);
        } else {
            x0 = right ? 1 - f.r - ix : f.l + ix;
            yTop = top ? 1 - f.t - iy : f.b + iy + height;
        }
        auto text = [&](double x, double at, const std::string& t, int align, double size) {
            auto* l = keep.hold(new TLatex(x, at, t.c_str()));
            l->SetNDC(), l->SetTextFont(look.font), l->SetTextSize(size), l->SetTextAlign(align), l->Draw();
        };
        auto line = [&](double x1, double y1, double x2, double y2, int colourIndex) {
            auto* l = keep.hold(new TLine(x1, y1, x2, y2));
            l->SetNDC(), l->SetLineColor(colourIndex), l->SetLineWidth(look.width), l->Draw();
        };
        if (!title.empty()) text(x0, yTop - 0.5 * first, title, right ? 32 : 12, look.header);
        double y = yTop - first - 0.5 * dy;
        for (const auto& e : entries) {
            const double s1 = right ? x0 - sw : x0, s2 = right ? x0 : x0 + sw, xc = 0.5 * (s1 + s2);
            if (e.drawn) {
                line(s1, y, s2, y, e.colour);
                line(xc, y - 0.4 * dy, xc, y + 0.4 * dy, e.colour);
                if (e.data) {
                    auto* m = keep.hold(new TMarker(xc, y, s.marker));
                    m->SetNDC(), m->SetMarkerColor(e.colour), m->SetMarkerSize(look.marker()), m->Draw();
                }
            }
            text(right ? s1 - gap : s2 + gap, y, e.label, right ? 32 : 12, look.legend);
            y -= dy;
        }
    }

    struct RatioRange {
        double lo, hi;
    };

    // The ratio pad shows at least the style's range, widened to the ratios drawn, within its limits:
    // a curve far from the reference (another beam energy against the data) is on the pad, one wild
    // bin cannot flatten it.
    inline RatioRange ratioRange(const std::vector<std::pair<size_t, Series>>& ratios, Range x, const Style& s) {
        double lo = s.rangeLo, hi = s.rangeHi;
        for (const auto& [c, r] : ratios)
            for (size_t i = 0; i < r.size(); ++i)
                if (std::isfinite(r.y[i]) && r.hi[i] > x.lo && r.lo[i] < x.hi)
                    lo = std::min(lo, 0.9 * (r.y[i] - r.err[i])), hi = std::max(hi, 1.1 * (r.y[i] + r.err[i]));
        return {std::max(lo, s.limitLo), std::min(hi, s.limitHi)};
    }

    inline void draw(const Page& page, std::vector<Series>& curves, Series* data, Range x, YRange y) {
        const Style& st = page.style;
        gROOT->SetBatch(kTRUE);
        gStyle->SetOptStat(0), gStyle->SetOptTitle(0), gStyle->SetEndErrorSize(0), gStyle->SetFrameLineWidth(1);
        gStyle->SetPaperSize(static_cast<float>(st.width * 2.54), static_cast<float>(st.height * 2.54));   // cm
        const Look look(st);
        Keep keep;
        const int W = st.pixelsWide(), H = st.pixelsHigh();
        TCanvas canvas("paint", page.name.c_str(), W, H);
        canvas.SetCanvasSize(W, H);

        // titles above the frame (V51): the corner line, then the main title over it; the top margin
        // grows by what they need, so a page without them is unchanged
        const bool corners = !page.titleLeft.empty() || !page.titleRight.empty(), main = !page.title.empty();
        const double cornerH = 1.5 * st.cornerTitle * look.px, mainH = 1.6 * st.pageTitle * look.px;
        const double topMargin = st.top + ((corners ? cornerH : 0.0) + (main ? mainH : 0.0)) / H;

        // with a ratio, the axes between the margins split by ratio.heights, with no gap
        Frame ft{double(W), double(H), st.left, st.right, st.bottom, topMargin}, fb{};
        TPad* top = &canvas;
        TPad* bottom = nullptr;
        if (page.ratio) {
            const double split = st.bottom + (1 - topMargin - st.bottom) * st.ratioHeight / (st.mainHeight + st.ratioHeight);
            top = new TPad("top", "", 0, split, 1, 1);                         // the canvas owns its pads
            bottom = new TPad("bottom", "", 0, 0, 1, split);
            ft = {double(W), H * (1 - split), st.left, st.right, 0.0, topMargin / (1 - split)};
            fb = {double(W), H * split, st.left, st.right, st.bottom / split, 0.0};
            bottom->SetMargin(fb.l, fb.r, fb.b, fb.t);
            for (TPad* p : {top, bottom}) p->SetFillStyle(0), p->SetBorderMode(0), p->Draw();
        }
        top->SetMargin(ft.l, ft.r, ft.b, ft.t);
        for (TPad* p : {top, bottom})
            if (p) p->SetTickx(st.allSides), p->SetTicky(st.allSides), p->SetLogx(page.logx);

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
            entries.push_back({data->label, colour(st.dataColour), true, true});
        }
        for (size_t c = 0; c < curves.size(); ++c) {
            const int colourIndex = colour(st.palette[c % st.palette.size()]);
            curve(curves[c], colourIndex, look, keep, "c" + std::to_string(c));
            const bool drawn = std::any_of(curves[c].y.begin(), curves[c].y.end(), [](double v) { return std::isfinite(v); });
            entries.push_back({drawn ? curves[c].label : curves[c].label + " (no entries)", colourIndex, false, drawn});
        }
        std::vector<const Series*> drawn;
        if (data) drawn.push_back(&*data);
        for (const Series& c : curves) drawn.push_back(&c);
        legend(page.legendHeader, entries, look, ft, keep, placed(drawn, x, Range{y.lo, y.hi}, page.logx, page.logy, ft));
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
            const RatioRange r = ratioRange(ratios, x, st);
            TH1F* rframe = bottom->DrawFrame(x.lo, r.lo, x.hi, r.hi - 5e-3 * (r.hi - r.lo));   // no label at the joint
            style(rframe, look, fb, true);
            rframe->GetXaxis()->SetTitle(page.xLabel.c_str());
            rframe->GetYaxis()->SetTitle(page.ratioLabel.c_str());
            rframe->GetYaxis()->SetNdivisions(st.divisions), rframe->GetYaxis()->SetDecimals(st.decimals);
            if (data) dataPoints(reference, look, keep, &reference);          // the data at 1, with their errors
            for (auto& [c, ratio] : ratios)
                curve(ratio, colour(st.palette[c % st.palette.size()]), look, keep, "r" + std::to_string(c));
            bottom->RedrawAxis();
        }

        if (corners || main) {                       // in the canvas's NDC, over the frame's top edge
            canvas.cd();
            const double edge = 1 - topMargin, gap = 0.25 * st.cornerTitle * look.px / H;
            auto put = [&](double x, double y, const std::string& t, int align, double size) {
                auto* l = keep.hold(new TLatex(x, y, t.c_str()));
                l->SetNDC(), l->SetTextFont(look.font), l->SetTextSize(size), l->SetTextAlign(align), l->Draw();
            };
            if (!page.titleLeft.empty()) put(st.left, edge + gap, page.titleLeft, 11, st.cornerTitle * look.px);
            if (!page.titleRight.empty()) put(1 - st.right, edge + gap, page.titleRight, 31, st.cornerTitle * look.px);
            if (main) put(st.left + 0.5 * (1 - st.left - st.right), edge + (corners ? cornerH / H : 0.0) + gap,
                          page.title, 21, st.pageTitle * look.px);
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
