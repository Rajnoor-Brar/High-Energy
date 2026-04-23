#pragma once

// ── Part 5: event-centric extractor layer ────────────────────────────────────
//
// An `Extract::Fn` maps an `Explore::Event` → a `std::vector<Double_t>`. Each
// element produced represents one fill into a downstream ROOT object. This is
// the representation-first complement to `Config::ParticleProperty` /
// `Config::EventProperty`: enums handle simple per-particle / per-event
// kinematics driven by TOML; extractors handle anything composed over the
// whole event (pair masses, ΔR, aux columns, filtered/leading selections).
//
// The extractor path is **additive** — it does not replace the enum path, and
// existing `TH1Record` / `EventTH1Record` fill sites keep working unchanged.
//
// See: plans/along-with-these-the-toasty-beaver.md (Part 5).

#include <algorithm>
#include <cstddef>
#include <functional>
#include <string>
#include <utility>
#include <vector>

#include "Analysis.hh"
#include "Config.hh"
#include "Explore.hh"
#include "Math/Vector4D.h"
#include "RtypesCore.h"

namespace Extract {
    using Event   = Explore::Event;
    using Lorentz = Analysis::Lorentz;
    using Scalars = std::vector<Double_t>;
    using Fn      = std::function<Scalars(const Event&)>;

    // ── Primitive extractors ─────────────────────────────────────────────────

    // One value per particle in the named collection, via the Part-3 enum
    // traits (Analysis::valueOf).
    inline Fn property(std::string label, Config::ParticleProperty p) {
        return [lbl = std::move(label), p](const Event& ev) -> Scalars {
            const auto it = ev.particles.find(lbl);
            if (it == ev.particles.end()) return {};
            Scalars out;
            out.reserve(it->second.size());
            for (const auto& particle : it->second)
                out.push_back(Analysis::valueOf(particle, p));
            return out;
        };
    }

    // One scalar per event: the multiplicity of a named collection.
    inline Fn multiplicity(std::string label) {
        return [lbl = std::move(label)](const Event& ev) -> Scalars {
            const auto it = ev.particles.find(lbl);
            return { it == ev.particles.end()
                         ? 0.0
                         : static_cast<Double_t>(it->second.size()) };
        };
    }

    // One scalar per event: size(a) + size(b) + ... (useful for combined sets).
    inline Fn totalMultiplicity(std::vector<std::string> labels) {
        return [lbls = std::move(labels)](const Event& ev) -> Scalars {
            std::size_t total = 0;
            for (const auto& l : lbls) {
                const auto it = ev.particles.find(l);
                if (it != ev.particles.end()) total += it->second.size();
            }
            return { static_cast<Double_t>(total) };
        };
    }

    // Cross-product pair invariant masses over two collections.
    // Length = |A| × |B|. When A==B, pairs (i,j) with i<j only (no self, no dup).
    inline Fn pairInvariantMass(std::string labelA, std::string labelB) {
        return [a = std::move(labelA), b = std::move(labelB)](const Event& ev) -> Scalars {
            const auto ia = ev.particles.find(a);
            const auto ib = ev.particles.find(b);
            if (ia == ev.particles.end() || ib == ev.particles.end()) return {};
            const auto& A = ia->second;
            const auto& B = ib->second;
            Scalars out;
            if (a == b) {
                // Unordered unique pairs within a single collection
                if (A.size() < 2) return {};
                out.reserve(A.size() * (A.size() - 1) / 2);
                for (std::size_t i = 0; i < A.size(); ++i)
                    for (std::size_t j = i + 1; j < A.size(); ++j)
                        out.push_back((A[i] + A[j]).M());
            } else {
                out.reserve(A.size() * B.size());
                for (const auto& pa : A)
                    for (const auto& pb : B)
                        out.push_back((pa + pb).M());
            }
            return out;
        };
    }

    // Cross-product ΔR over two collections (same pairing rules as above).
    inline Fn deltaR(std::string labelA, std::string labelB) {
        return [a = std::move(labelA), b = std::move(labelB)](const Event& ev) -> Scalars {
            const auto ia = ev.particles.find(a);
            const auto ib = ev.particles.find(b);
            if (ia == ev.particles.end() || ib == ev.particles.end()) return {};
            const auto& A = ia->second;
            const auto& B = ib->second;
            Scalars out;
            if (a == b) {
                if (A.size() < 2) return {};
                out.reserve(A.size() * (A.size() - 1) / 2);
                for (std::size_t i = 0; i < A.size(); ++i)
                    for (std::size_t j = i + 1; j < A.size(); ++j)
                        out.push_back(Analysis::deltaR(A[i], A[j]));
            } else {
                out.reserve(A.size() * B.size());
                for (const auto& pa : A)
                    for (const auto& pb : B)
                        out.push_back(Analysis::deltaR(pa, pb));
            }
            return out;
        };
    }

    // Read a typed aux column off the named collection. Returns empty Scalars
    // if the label or column is missing — no throw (fills just do nothing).
    inline Fn column(std::string label, std::string columnName) {
        return [lbl = std::move(label), col = std::move(columnName)](const Event& ev) -> Scalars {
            const auto li = ev.aux.find(lbl);
            if (li == ev.aux.end()) return {};
            const auto ci = li->second.find(col);
            if (ci == li->second.end()) return {};
            try {
                const auto& v = ci->second.as<double>();
                return Scalars(v.begin(), v.end());
            } catch (...) {
                return {};
            }
        };
    }

    // One-scalar extractor from a per-event ScalarValue.
    inline Fn scalar(std::string name) {
        return [n = std::move(name)](const Event& ev) -> Scalars {
            const auto it = ev.scalars.find(n);
            if (it == ev.scalars.end()) return {};
            Double_t v = 0.0;
            std::visit([&](auto value) { v = static_cast<Double_t>(value); }, it->second);
            return { v };
        };
    }

    // Constant — useful for cross-product 2D fills against a fixed x (or y).
    inline Fn constant(Double_t value) {
        return [value](const Event&) -> Scalars { return { value }; };
    }

    // ── Combinators ──────────────────────────────────────────────────────────

    // Keep only the largest value produced by `inner` (leading-particle style).
    // Returns empty Scalars if `inner` produced nothing.
    inline Fn leadingOf(Fn inner) {
        return [fn = std::move(inner)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            if (vals.empty()) return {};
            return { *std::max_element(vals.begin(), vals.end()) };
        };
    }

    // Keep only the smallest value produced by `inner`.
    inline Fn trailingOf(Fn inner) {
        return [fn = std::move(inner)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            if (vals.empty()) return {};
            return { *std::min_element(vals.begin(), vals.end()) };
        };
    }

    // Filter the scalars produced by `inner` by a numeric predicate.
    inline Fn filtered(Fn inner, std::function<bool(Double_t)> pred) {
        return [fn = std::move(inner), p = std::move(pred)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            Scalars out;
            out.reserve(vals.size());
            for (Double_t v : vals) if (p(v)) out.push_back(v);
            return out;
        };
    }

    // Sum of all values produced by `inner` (e.g. Σpt).
    inline Fn sumOf(Fn inner) {
        return [fn = std::move(inner)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            Double_t s = 0.0;
            for (Double_t v : vals) s += v;
            return { s };
        };
    }

    // Count of values produced by `inner` that satisfy `pred` (e.g. N(pt>5)).
    inline Fn countIf(Fn inner, std::function<bool(Double_t)> pred) {
        return [fn = std::move(inner), p = std::move(pred)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            std::size_t n = 0;
            for (Double_t v : vals) if (p(v)) ++n;
            return { static_cast<Double_t>(n) };
        };
    }
}
