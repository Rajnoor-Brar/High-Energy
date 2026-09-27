#pragma once
// utils/Apps/Paint/Transform.hh — what makes a page readable, as pure functions over bins.
//
// The rules are v1's (plot/transform.py, itself a port of the legacy ydmrg), written again here:
//   * void   — a bin that is zero in every curve (void_empty), or that fewer than min_entries raw
//              entries went into in any curve, is blanked in ALL curves. It is decided across the
//              page, never per curve, or the curves would disagree about which bins exist.
//   * align  — reference data is trimmed to its longest run of bins whose edges are all MC edges,
//              or dropped (never rebinned past the end).
//   * range  — x is clipped to the bins that carry content, in curves and data, widened by
//              range_pad whole bins. Order: void, then align, then range (L18, v1 §5).
//   * gutter — y_gutter = g puts the top of the y axis at (1 + g) × the largest drawn value; x_gutter = g
//              widens x by g of its span. 0 (or "default") sets nothing: the range is ROOT's own choice.

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <string>
#include <vector>

namespace Paint {

    struct Series {
        std::string label;
        std::vector<double> lo, hi, y, err, raw;   // raw: per-bin entry counts when known
        bool data = false;
        size_t size() const { return y.size(); }
    };

    inline bool close(double a, double b) { return std::fabs(a - b) <= 1e-9 * std::max({1.0, std::fabs(a), std::fabs(b)}); }

    inline bool sameBinning(const Series& a, const Series& b) {
        if (a.size() != b.size()) return false;
        for (size_t i = 0; i < a.size(); ++i)
            if (!close(a.lo[i], b.lo[i]) || !close(a.hi[i], b.hi[i])) return false;
        return true;
    }

    // The void mask of a page's curves; empty when the curves do not share one binning.
    inline std::vector<bool> voidMask(const std::vector<Series>& curves, bool voidEmpty, int minEntries) {
        if (curves.empty() || (!voidEmpty && minEntries <= 0)) return {};
        for (const auto& c : curves)
            if (!sameBinning(c, curves.front())) return {};
        const size_t n = curves.front().size();
        std::vector<bool> mask(n, false);
        for (size_t i = 0; i < n; ++i) {
            bool zeroEverywhere = voidEmpty;
            bool sparse = false;
            for (const auto& c : curves) {
                if (!(c.y[i] == 0.0)) zeroEverywhere = false;
                if (minEntries > 0 && c.raw.size() == n && c.raw[i] < minEntries) sparse = true;
            }
            mask[i] = zeroEverywhere || sparse;
        }
        return mask;
    }

    inline void applyVoid(std::vector<Series>& curves, const std::vector<bool>& mask) {
        for (auto& c : curves)
            if (c.size() == mask.size())
                for (size_t i = 0; i < mask.size(); ++i)
                    if (mask[i]) c.y[i] = std::numeric_limits<double>::quiet_NaN(), c.err[i] = 0.0;
    }

    // Trim data to its longest run of consecutive bins whose edges are MC edges. false = drop it.
    inline bool alignTo(Series& data, const Series& mc) {
        std::vector<double> edges(mc.lo);
        if (!mc.hi.empty()) edges.push_back(mc.hi.back());
        auto isEdge = [&](double x) {
            return std::any_of(edges.begin(), edges.end(), [&](double e) { return close(e, x); });
        };
        size_t bestStart = 0, bestLength = 0, start = 0, length = 0;
        for (size_t j = 0; j < data.size(); ++j) {
            const bool ok = isEdge(data.lo[j]) && isEdge(data.hi[j]);
            const bool continues = ok && length > 0 && close(data.lo[j], data.hi[j - 1]);
            if (ok && (length == 0 || continues)) {
                if (length == 0) start = j;
                ++length;
            } else if (ok) {
                start = j, length = 1;
            } else {
                length = 0;
            }
            if (length > bestLength) bestStart = start, bestLength = length;
        }
        if (bestLength == 0) return false;
        auto cut = [&](std::vector<double>& v) {
            if (v.size() == data.size())
                v = std::vector<double>(v.begin() + bestStart, v.begin() + bestStart + bestLength);
        };
        const size_t n = data.size();
        cut(data.lo), cut(data.hi), cut(data.err);
        if (data.raw.size() == n) cut(data.raw);
        data.y = std::vector<double>(data.y.begin() + bestStart, data.y.begin() + bestStart + bestLength);
        return true;
    }

    struct Range {
        double lo, hi;
    };

    // The x span of the filled bins over every series, padded by whole bins of each series.
    inline Range autoRange(const std::vector<const Series*>& all, int pad) {
        Range out{std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()};
        for (const Series* s : all) {
            std::vector<size_t> filled;
            for (size_t i = 0; i < s->size(); ++i)
                if (std::isfinite(s->y[i]) && s->y[i] != 0.0) filled.push_back(i);
            if (filled.empty()) continue;
            const size_t first = filled.front() >= static_cast<size_t>(pad) ? filled.front() - pad : 0;
            const size_t last = std::min(filled.back() + pad, s->size() - 1);
            out.lo = std::min(out.lo, s->lo[first]);
            out.hi = std::max(out.hi, s->hi[last]);
        }
        return out;
    }

    inline Range fullRange(const std::vector<const Series*>& all) {
        Range out{std::numeric_limits<double>::infinity(), -std::numeric_limits<double>::infinity()};
        for (const Series* s : all)
            if (s->size()) out.lo = std::min(out.lo, s->lo.front()), out.hi = std::max(out.hi, s->hi.back());
        return out;
    }

    // x_gutter = g widens x symmetrically: the span becomes (1 + g) × itself, in decades on a log
    // axis. None (0 or "default") keeps the range the bins give, as ROOT draws a histogram.
    inline Range xWithGutter(Range x, std::optional<double> gutter, bool logx) {
        if (!gutter) return x;
        if (logx && x.lo > 0) {
            const double l = std::log10(x.lo), h = std::log10(x.hi), extra = (h - l) * *gutter / 2;
            return {std::pow(10, l - extra), std::pow(10, h + extra)};
        }
        const double extra = (x.hi - x.lo) * *gutter / 2;
        return {x.lo - extra, x.hi + extra};
    }

    struct YRange {
        double lo, hi, largest;
        bool tool = false;                 // ROOT's own choice (no gutter): another backend may choose its own
    };

    // ROOT's choice for a histogram drawn alone (THistPainter::PaintInit, HIST, gStyle's 5% top margin),
    // taken over every value on the page: what "let the tool decide" means for Paint.
    inline YRange rootRange(double smallest, double largest, bool logy) {
        constexpr double margin = 0.05;
        double lo = smallest, hi = largest;
        if (logy) {
            if (lo <= 0) lo = hi >= 1 ? std::max(0.005, hi * 1e-10) : 0.001 * hi;
            if (hi <= 0) return {0.01, 10.0, largest, true};
            if (lo >= hi) lo = 0.001 * hi;
            return {lo * 0.5, hi * 2 * (0.9 / 0.95), largest, true};
        }
        if (lo >= hi) {
            if (lo > 0) lo = 0, hi *= 2;
            else if (lo < 0) hi = 0, lo *= 2;
            else lo = 0, hi = 1;
        }
        const double below = margin * (hi - lo);
        lo = (lo >= 0 && lo - below <= 0) ? 0.0 : lo - below;
        hi += margin * (hi - lo);
        return {lo, hi, largest, true};
    }

    // y: 0 (or the smallest value) to (1 + y_gutter) × the largest drawn value, within the x range. On a
    // log axis the gutter is the same fraction of the decades shown. No gutter: ROOT's own choice.
    inline YRange yRange(const std::vector<const Series*>& all, Range x, std::optional<double> gutter, bool logy) {
        double largest = -std::numeric_limits<double>::infinity(), smallest = std::numeric_limits<double>::infinity();
        double smallestPositive = std::numeric_limits<double>::infinity();
        for (const Series* s : all)
            for (size_t i = 0; i < s->size(); ++i) {
                if (!std::isfinite(s->y[i]) || s->hi[i] <= x.lo || s->lo[i] >= x.hi) continue;
                largest = std::max(largest, s->y[i]);
                smallest = std::min(smallest, s->y[i]);
                if (s->y[i] > 0) smallestPositive = std::min(smallestPositive, s->y[i]);
            }
        if (!std::isfinite(largest)) return {0.0, 1.0, 0.0, !gutter};
        if (!gutter) return rootRange(smallest, largest, logy);
        const double g = 1.0 + *gutter;
        if (logy) {
            const double low = std::isfinite(smallestPositive) ? smallestPositive / 2 : largest / 1e3;
            const double decades = std::log10(largest) - std::log10(low);
            return {low, largest * std::pow(10, decades * *gutter), largest};
        }
        const double low = smallest >= 0 ? 0.0 : smallest * g;
        return {low, largest > 0 ? largest * g : 1.0, largest};
    }

    // A density rebinned onto [lo, hi) from the bins it covers (bin-width weighted, errors in
    // quadrature). NaN when a covered bin is void or the span is not covered exactly.
    inline std::pair<double, double> rebinned(const Series& s, double lo, double hi) {
        double sum = 0, var = 0, covered = 0;
        for (size_t i = 0; i < s.size(); ++i) {
            if (s.lo[i] < lo - 1e-9 * std::fabs(lo) - 1e-12 || s.hi[i] > hi + 1e-9 * std::fabs(hi) + 1e-12) continue;
            if (!std::isfinite(s.y[i])) return {std::numeric_limits<double>::quiet_NaN(), 0};
            const double w = s.hi[i] - s.lo[i];
            sum += s.y[i] * w, var += std::pow(s.err[i] * w, 2), covered += w;
        }
        if (!close(covered, hi - lo)) return {std::numeric_limits<double>::quiet_NaN(), 0};
        return {sum / covered, std::sqrt(var) / covered};
    }

}  // namespace Paint
