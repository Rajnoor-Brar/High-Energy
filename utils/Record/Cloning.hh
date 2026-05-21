#pragma once

#include "Record/Writer.hh"

namespace Record {

// Walks every declared record and allocates nRecordThreads_ clones.
// Clones are detached from any TDirectory so they do not end up in
// outFile_; only masters are written.
inline void Writer::allocateAllClones() {
        for (auto& [key, obj] : particleObjects_) {
            (void)key;
            cloneTH1Impl(obj.count);
            for (auto& h : obj.hists1D)  cloneTH1Impl(h);
            for (auto& h : obj.hists2D)  cloneTH2Impl(h);
            for (auto& g : obj.graphs)   cloneGraphImpl(g);
            for (auto& p : obj.profiles) cloneProfileImpl(p);
            // tree: shared, no clones
        }
        for (auto& [key, r] : hists1D_)  { (void)key; cloneTH1Impl(r); }
        for (auto& [key, r] : hists2D_)  { (void)key; cloneTH2Impl(r); }
        for (auto& [key, r] : graphs_)   { (void)key; cloneGraphImpl(r); }
        for (auto& [key, r] : profiles_) { (void)key; cloneProfileImpl(r); }
        // trees: shared, no clones
    }

// Helpers — accept any record with `.hist`/`.graph`/`.profile` master
    // pointer and a parallel `.clones` vector.  Templated to apply to
    // both ParticleTH1 and Hist1DRecord (same shape).
template <typename Rec>
inline void Writer::cloneTH1Impl(Rec& r) {
        r.clones.clear();
        if (!r.hist) return;
        r.clones.reserve(nRecordThreads_);
        for (std::size_t i = 0; i < nRecordThreads_; ++i) {
            std::unique_ptr<TH1> clone(static_cast<TH1*>(
                r.hist->Clone((std::string(r.hist->GetName()) + "_w"
                               + std::to_string(i)).c_str())));
            clone->SetDirectory(nullptr);
            clone->Reset("ICESM");
            r.clones.push_back(std::move(clone));
        }
    }

template <typename Rec>
inline void Writer::cloneTH2Impl(Rec& r) {
        r.clones.clear();
        if (!r.hist) return;
        r.clones.reserve(nRecordThreads_);
        for (std::size_t i = 0; i < nRecordThreads_; ++i) {
            std::unique_ptr<TH2> clone(static_cast<TH2*>(
                r.hist->Clone((std::string(r.hist->GetName()) + "_w"
                               + std::to_string(i)).c_str())));
            clone->SetDirectory(nullptr);
            clone->Reset("ICESM");
            r.clones.push_back(std::move(clone));
        }
    }

template <typename Rec>
inline void Writer::cloneGraphImpl(Rec& r) {
        r.clones.clear();
        r.nextPoint.clear();
        if (!r.graph) return;
        r.clones.reserve(nRecordThreads_);
        r.nextPoint.assign(nRecordThreads_, 0);
        for (std::size_t i = 0; i < nRecordThreads_; ++i) {
            // TGraph clones live in-memory only; not registered in any
            // TDirectory.  TGraph doesn't have SetDirectory.
            std::unique_ptr<TGraph> clone(static_cast<TGraph*>(r.graph->Clone(
                (std::string(r.graph->GetName()) + "_w"
                 + std::to_string(i)).c_str())));
            clone->Set(0);  // reset point count
            r.clones.push_back(std::move(clone));
        }
    }

template <typename Rec>
inline void Writer::cloneProfileImpl(Rec& r) {
        r.clones.clear();
        if (!r.profile) return;
        r.clones.reserve(nRecordThreads_);
        for (std::size_t i = 0; i < nRecordThreads_; ++i) {
            std::unique_ptr<TProfile> clone(static_cast<TProfile*>(
                r.profile->Clone((std::string(r.profile->GetName()) + "_w"
                                  + std::to_string(i)).c_str())));
            clone->SetDirectory(nullptr);
            clone->Reset("ICESM");
            r.clones.push_back(std::move(clone));
        }
    }

// ── Merge clones into masters (at finalize / fatal) ─────────────────
    // Watchdog calls this AFTER drainAndStopWorkers, BEFORE writing.
inline         void Writer::mergeAllClones() {
        for (auto& [key, obj] : particleObjects_) {
            (void)key;
            mergeTH1Impl(obj.count);
            for (auto& h : obj.hists1D) mergeTH1Impl(h);
            for (auto& h : obj.hists2D) mergeTH2Impl(h);
            for (auto& g : obj.graphs)  mergeGraphImpl(g);
            for (auto& p : obj.profiles) mergeProfileImpl(p);
        }
        for (auto& [key, r] : hists1D_)  { (void)key; mergeTH1Impl(r); }
        for (auto& [key, r] : hists2D_)  { (void)key; mergeTH2Impl(r); }
        for (auto& [key, r] : graphs_)   { (void)key; mergeGraphImpl(r); }
        for (auto& [key, r] : profiles_) { (void)key; mergeProfileImpl(r); }
    }

template <typename Rec>
inline void Writer::mergeTH1Impl(Rec& r) {
        if (!r.hist || r.clones.empty()) return;
        r.hist->Reset("ICESM");
        for (auto& c : r.clones) r.hist->Add(c.get());
    }

template <typename Rec>
inline void Writer::mergeTH2Impl(Rec& r) {
        if (!r.hist || r.clones.empty()) return;
        r.hist->Reset("ICESM");
        for (auto& c : r.clones) r.hist->Add(c.get());
    }

template <typename Rec>
inline void Writer::mergeProfileImpl(Rec& r) {
        if (!r.profile || r.clones.empty()) return;
        r.profile->Reset("ICESM");
        for (auto& c : r.clones) r.profile->Add(c.get());
    }

template <typename Rec>
inline void Writer::mergeGraphImpl(Rec& r) {
        if (!r.graph || r.clones.empty()) return;
        r.graph->Set(0);
        int p = 0;
        for (auto& c : r.clones) {
            const int n = c->GetN();
            for (int i = 0; i < n; ++i) {
                double x = 0.0, y = 0.0;
                c->GetPoint(i, x, y);
                r.graph->SetPoint(p++, x, y);
            }
        }
    }

} // namespace Record
