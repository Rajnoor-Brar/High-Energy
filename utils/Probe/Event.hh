#pragma once

#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "Probe/BranchControl.hh"
#include "Probe/FlatReader.hh"
#include "Probe/VecReader.hh"

namespace Probe {

    class EventStream {
      public:
        EventStream(const std::string& filepath,
                    const std::vector<CollectionSpec>& collections,
                    Long64_t minBound = std::numeric_limits<Long64_t>::min(),
                    Long64_t maxBound = std::numeric_limits<Long64_t>::max(),
                    std::size_t nEventsHint = 0)
            : filepath_(filepath), minBound_(minBound), maxBound_(maxBound)
        {
            if (collections.empty())
                throw std::runtime_error("[Probe] EventStream: no collections specified");

            bool anyFlat = false, anyVec = false;
            for (const auto& cs : collections) {
                if (cs.indexBranches.empty()) anyVec  = true;
                else                          anyFlat = true;
            }
            if (anyFlat && anyVec)
                throw std::runtime_error(
                    "[Probe] EventStream: cannot mix Flat and Vec collections in one EventStream");

            isVec_ = anyVec;

            file_ = TFile::Open(filepath.c_str(), "READ");
            if (!file_ || file_->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + filepath + "'");

            if (isVec_) {
                for (const auto& cs : collections)
                    vecReaders_.push_back(std::make_unique<VecReader>(
                        file_, cs, filepath, minBound, maxBound));
                nEvents_ = vecReaders_.empty() ? 0
                         : static_cast<std::size_t>(vecReaders_[0]->totalEntries());
            } else {
                for (const auto& cs : collections)
                    flatReaders_.push_back(std::make_unique<FlatReader>(
                        file_, cs, filepath, minBound, maxBound));

                if (nEventsHint > 0) {
                    Long64_t gLo = std::numeric_limits<Long64_t>::max();
                    for (auto& r : flatReaders_) {
                        if (!r->exhausted())
                            gLo = std::min(gLo, r->currentKey().components[0]);
                    }
                    if (gLo != std::numeric_limits<Long64_t>::max()) {
                        const Long64_t lastKey = gLo + static_cast<Long64_t>(nEventsHint) - 1;
                        denseLo_ = std::max<Long64_t>(gLo, minBound);
                        denseHi_ = std::min<Long64_t>(lastKey, maxBound);
                        if (denseHi_ >= denseLo_) {
                            nextKey_ = denseLo_;
                            nEvents_ = static_cast<std::size_t>(denseHi_ - denseLo_ + 1);
                        }
                    }
                } else {
                    Long64_t gMin = std::numeric_limits<Long64_t>::max();
                    Long64_t gMax = std::numeric_limits<Long64_t>::min();
                    bool anyKeys = false;
                    for (auto& r : flatReaders_) {
                        Long64_t lo, hi;
                        if (r->keyRange(minBound, maxBound, lo, hi)) {
                            gMin = std::min(gMin, lo);
                            gMax = std::max(gMax, hi);
                            anyKeys = true;
                        }
                    }
                    if (anyKeys) {
                        denseLo_ = gMin;
                        denseHi_ = gMax;
                        nextKey_  = denseLo_;
                        nEvents_  = static_cast<std::size_t>(denseHi_ - denseLo_ + 1);
                    }
                }
            }
        }

        ~EventStream() { if (file_) { file_->Close(); delete file_; } }

        EventStream(const EventStream&)            = delete;
        EventStream& operator=(const EventStream&) = delete;

        bool next() {
            current_.particles.clear();
            current_.aux.clear();
            return isVec_ ? nextVec() : nextFlat();
        }

        const Event& event()   const { return current_; }
        std::size_t  nEvents() const { return nEvents_; }
        std::size_t  index()   const { return index_ == 0 ? 0 : index_ - 1; }

      private:
        bool nextFlat() {
            if (nextKey_ > denseHi_) return false;
            const Long64_t K = nextKey_++;
            current_.index = K;
            for (auto& r : flatReaders_) r->ensureLabel(current_);
            const EventKey key{{K}};
            for (auto& r : flatReaders_)
                if (!r->exhausted() && r->currentKey().components[0] == K)
                    r->drain(key, current_);
            ++index_;
            return true;
        }

        bool nextVec() {
            if (vecReaders_.empty()) return false;
            if (!vecReaders_[0]->next()) return false;
            for (std::size_t i = 1; i < vecReaders_.size(); ++i) vecReaders_[i]->next();
            for (auto& r : vecReaders_) r->fill(current_);
            ++index_;
            return true;
        }

        std::string   filepath_;
        TFile*        file_     = nullptr;
        bool          isVec_   = false;
        Long64_t      minBound_;
        Long64_t      maxBound_;
        Event         current_;
        std::size_t   index_   = 0;
        std::size_t   nEvents_ = 0;
        Long64_t      denseLo_  = 0;
        Long64_t      denseHi_  = -1;
        Long64_t      nextKey_  = 0;

        std::vector<std::unique_ptr<FlatReader>> flatReaders_;
        std::vector<std::unique_ptr<VecReader>>  vecReaders_;
    };

} // namespace Probe
