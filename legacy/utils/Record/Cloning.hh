#pragma once

#include "Record/Writer.hh"

namespace Record {

// Walks every declared record and allocates nRecordThreads_ clones.
// Clones are detached from any TDirectory so they do not end up in
// outFile_; only masters are written.
inline void Writer::allocateAllClones() {
        for (auto& [key, obj] : particleObjects_) {
            (void)key;
            cloneHistImpl(obj.count);
            for (auto& h : obj.hists1D)  cloneHistImpl(h);
            for (auto& h : obj.hists2D)  cloneHistImpl(h);
            for (auto& g : obj.graphs)   cloneGraphImpl(g);
            for (auto& p : obj.profiles) cloneHistImpl(p);
            // tree: shared, no clones
        }
        for (auto& [key, r] : hists1D_)  { (void)key; cloneHistImpl(r); }
        for (auto& [key, r] : hists2D_)  { (void)key; cloneHistImpl(r); }
        for (auto& [key, r] : graphs_)   { (void)key; cloneGraphImpl(r); }
        for (auto& [key, r] : profiles_) { (void)key; cloneHistImpl(r); }
        // trees: shared, no clones
    }

// cloneHistImpl — any CloneSet whose object supports SetDirectory + Reset
    // (TH1, TH2, TProfile). One template replaced three near-identical
    // per-type implementations.
template <typename Rec>
inline void Writer::cloneHistImpl(Rec& r) {
        using TObj = std::remove_pointer_t<decltype(r.master)>;
        r.clones.clear();
        if (!r.master) return;
        r.clones.reserve(nRecordThreads_);
        for (std::size_t i = 0; i < nRecordThreads_; ++i) {
            std::unique_ptr<TObj> clone(static_cast<TObj*>(
                r.master->Clone((std::string(r.master->GetName()) + "_w"
                                 + std::to_string(i)).c_str())));
            clone->SetDirectory(nullptr);
            clone->Reset("ICESM");
            r.clones.push_back(std::move(clone));
        }
    }

// cloneGraphImpl — TGraph has no SetDirectory/Reset; clones live in-memory
    // only, with a per-worker next-point cursor.
template <typename Rec>
inline void Writer::cloneGraphImpl(Rec& r) {
        r.clones.clear();
        r.nextPoint.clear();
        if (!r.master) return;
        r.clones.reserve(nRecordThreads_);
        r.nextPoint.assign(nRecordThreads_, 0);
        for (std::size_t i = 0; i < nRecordThreads_; ++i) {
            std::unique_ptr<TGraph> clone(static_cast<TGraph*>(r.master->Clone(
                (std::string(r.master->GetName()) + "_w"
                 + std::to_string(i)).c_str())));
            clone->Set(0);  // reset point count
            r.clones.push_back(std::move(clone));
        }
    }

// ── Merge clones into masters (at finalize / fatal) ─────────────────
    // Watchdog calls this AFTER drainAndStopWorkers, BEFORE writing.
inline void Writer::mergeAllClones() {
        for (auto& [key, obj] : particleObjects_) {
            (void)key;
            mergeHistImpl(obj.count);
            for (auto& h : obj.hists1D)  mergeHistImpl(h);
            for (auto& h : obj.hists2D)  mergeHistImpl(h);
            for (auto& g : obj.graphs)   mergeGraphImpl(g);
            for (auto& p : obj.profiles) mergeHistImpl(p);
        }
        for (auto& [key, r] : hists1D_)  { (void)key; mergeHistImpl(r); }
        for (auto& [key, r] : hists2D_)  { (void)key; mergeHistImpl(r); }
        for (auto& [key, r] : graphs_)   { (void)key; mergeGraphImpl(r); }
        for (auto& [key, r] : profiles_) { (void)key; mergeHistImpl(r); }
    }

template <typename Rec>
inline void Writer::mergeHistImpl(Rec& r) {
        if (!r.master || r.clones.empty()) return;
        r.master->Reset("ICESM");
        for (auto& c : r.clones) r.master->Add(c.get());
    }

template <typename Rec>
inline void Writer::mergeGraphImpl(Rec& r) {
        if (!r.master || r.clones.empty()) return;
        r.master->Set(0);
        int p = 0;
        for (auto& c : r.clones) {
            const int n = c->GetN();
            for (int i = 0; i < n; ++i) {
                double x = 0.0, y = 0.0;
                c->GetPoint(i, x, y);
                r.master->SetPoint(p++, x, y);
            }
        }
    }

} // namespace Record
