#pragma once

// ── Part 5: event-centric extractor layer ────────────────────────────────────
//
// A `Record::Extract::Fn` maps a `Probe::Event` → a `std::vector<Double_t>`. Each
// element produced represents one fill into a downstream ROOT object.

#include <algorithm>
#include <cstddef>
#include <functional>
#include <string>
#include <utility>
#include <vector>

#include "Physics.hh"
// #include "Config.hh"
#include "Probe.hh"
#include "Math/Vector4D.h"
#include "RtypesCore.h"

namespace Record::Extract {
    using Event   = Probe::Event;
    using Scalars = std::vector<Double_t>;
    using Fn      = std::function<Scalars(const Event&)>;

    // ── Primitive extractors ─────────────────────────────────────────────────

    inline Fn property(std::string label, Physics::ParticleProperty p) {
        return [lbl = std::move(label), p](const Event& ev) -> Scalars {
            const auto it = ev.particles.find(lbl);
            if (it == ev.particles.end()) return {};
            Scalars out;
            out.reserve(it->second.size());
            for (const auto& particle : it->second)
                out.push_back(Physics::valueOf(particle, p));
            return out;
        };
    }

    inline Fn multiplicity(std::string label) {
        return [lbl = std::move(label)](const Event& ev) -> Scalars {
            const auto it = ev.particles.find(lbl);
            return { it == ev.particles.end()
                         ? 0.0
                         : static_cast<Double_t>(it->second.size()) };
        };
    }

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

    inline Fn pairInvariantMass(std::string labelA, std::string labelB) {
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
                        out.push_back(Physics::deltaR(A[i], A[j]));
            } else {
                out.reserve(A.size() * B.size());
                for (const auto& pa : A)
                    for (const auto& pb : B)
                        out.push_back(Physics::deltaR(pa, pb));
            }
            return out;
        };
    }

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

    inline Fn constant(Double_t value) {
        return [value](const Event&) -> Scalars { return { value }; };
    }

    // ── Combinators ──────────────────────────────────────────────────────────

    inline Fn leadingOf(Fn inner) {
        return [fn = std::move(inner)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            if (vals.empty()) return {};
            return { *std::max_element(vals.begin(), vals.end()) };
        };
    }

    inline Fn trailingOf(Fn inner) {
        return [fn = std::move(inner)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            if (vals.empty()) return {};
            return { *std::min_element(vals.begin(), vals.end()) };
        };
    }

    inline Fn filtered(Fn inner, std::function<bool(Double_t)> pred) {
        return [fn = std::move(inner), p = std::move(pred)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            Scalars out;
            out.reserve(vals.size());
            for (Double_t v : vals) if (p(v)) out.push_back(v);
            return out;
        };
    }

    inline Fn sumOf(Fn inner) {
        return [fn = std::move(inner)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            Double_t s = 0.0;
            for (Double_t v : vals) s += v;
            return { s };
        };
    }

    inline Fn countIf(Fn inner, std::function<bool(Double_t)> pred) {
        return [fn = std::move(inner), p = std::move(pred)](const Event& ev) -> Scalars {
            Scalars vals = fn(ev);
            std::size_t n = 0;
            for (Double_t v : vals) if (p(v)) ++n;
            return { static_cast<Double_t>(n) };
        };
    }
} // namespace Record::Extract
