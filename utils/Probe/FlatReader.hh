#pragma once

#include <algorithm>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>

#include "Probe/BranchControl.hh"
#include "TObjArray.h"
#include "TTreeIndex.h"

namespace Probe {

    class FlatReader {
      public:
        FlatReader(TFile* file, const CollectionSpec& spec,
                   const std::string& filepath,
                   Long64_t minKey, Long64_t maxKey,
                   Bounds entryBounds = {},
                   bool hasEntryBounds = false)
            : label_(spec.label), filepath_(filepath),
              coords_(spec.coords), minKey_(minKey), maxKey_(maxKey)
        {
            tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
            if (!tree_)
                throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in file '" + filepath + "'");

            tree_->SetBranchStatus("*", 0);

            idxName_ = spec.indexBranches[0].name;
            TBranch* idxBr = BranchControl::requireBranch(tree_, idxName_, filepath);
            const BranchType it = BranchControl::detectType(idxBr);
            if (it != BranchType::Int32 && it != BranchType::Int64 && it != BranchType::UInt32)
                throw std::runtime_error(
                    "[Probe] Index branch '" + idxName_ + "' in tree '" + spec.tree +
                    "' of file '" + filepath + "': must be Int_t, UInt_t, or Long64_t");
            if (spec.indexBranches[0].type != BranchType::Other && it != spec.indexBranches[0].type)
                throw std::runtime_error(
                    "[Probe] Type mismatch: index branch '" + idxName_ + "' declared as " + 
                    BranchControl::branchTypeStr(spec.indexBranches[0].type) + 
                    ", actual " + BranchControl::branchTypeStr(it));
            idxIsLong_ = (it == BranchType::Int64);
            tree_->SetBranchStatus(idxName_.c_str(), 1);
            if (idxIsLong_) tree_->SetBranchAddress(idxName_.c_str(), &idxL_);
            else            tree_->SetBranchAddress(idxName_.c_str(), &idxI_);

            const auto knames = BranchControl::coordNames(spec.coords);
            for (int i = 0; i < 4; ++i)
                kinBuf_[i].bind(tree_, knames[i], filepath);

            for (const auto& bspec : spec.auxBranches) {
                TBranch* br = BranchControl::requireBranch(tree_, bspec.name, filepath);
                BranchControl::requireType(br, bspec.type, filepath);
                tree_->SetBranchStatus(bspec.name.c_str(), 1);
                auxNames_.push_back(bspec.name);
                auxTypes_.push_back(bspec.type);
                bindAux(bspec);
            }

            tree_->SetCacheSize(10 * 1024 * 1024);
            tree_->AddBranchToCache("*", kTRUE);
            tree_->StopCacheLearningPhase();

            totalEntries_ = tree_->GetEntries();
            entryEnd_ = totalEntries_;

            if (hasEntryBounds && !entryBounds.valid()) {
                cursor_ = 0;
                entryEnd_ = 0;
                return;
            }

            if (hasEntryBounds) {
                cursor_ = std::max<Long64_t>(0, entryBounds.first);
                entryEnd_ = std::min(totalEntries_, entryBounds.last + 1);
                if (cursor_ >= entryEnd_) {
                    cursor_ = entryEnd_;
                    return;
                }
                tree_->GetEntry(cursor_);
                while (cursor_ < entryEnd_ && idxValue() < minKey_) {
                    ++cursor_;
                    if (cursor_ < entryEnd_) tree_->GetEntry(cursor_);
                }
                return;
            }

            if (auto* idx = dynamic_cast<TTreeIndex*>(tree_->GetTreeIndex())) {
                (void)idx;
                Long64_t entry = tree_->GetEntryNumberWithIndex(minKey_, 0);
                if (entry >= 0 && entry < totalEntries_) {
                    cursor_ = entry;
                    tree_->GetEntry(cursor_);
                    return;
                }
            }

            if (totalEntries_ > 0) tree_->GetEntry(cursor_);

            while (cursor_ < entryEnd_ && idxValue() < minKey_) {
                ++cursor_;
                if (cursor_ < entryEnd_) tree_->GetEntry(cursor_);
            }
        }

        FlatReader(const FlatReader&)            = delete;
        FlatReader& operator=(const FlatReader&) = delete;

        const std::string& label() const { return label_; }

        EventKey currentKey() const { return EventKey{{idxValue()}}; }
        bool exhausted()       const { return cursor_ >= entryEnd_; }
        bool beyondMax()       const { return !exhausted() && idxValue() > maxKey_; }

        void ensureLabel(Event& ev) const {
            ev.particles[label_];
            auto& auxMap = ev.aux[label_];
            for (std::size_t i = 0; i < auxNames_.size(); ++i)
                if (auxMap.find(auxNames_[i]) == auxMap.end())
                    auxMap[auxNames_[i]] = makeAuxCol(auxTypes_[i]);
        }

        void drain(const EventKey& key, Event& ev) {
            const Long64_t target = key.components[0];
            auto& pvec   = ev.particles[label_];
            auto& auxMap = ev.aux[label_];

            for (std::size_t i = 0; i < auxNames_.size(); ++i)
                if (auxMap.find(auxNames_[i]) == auxMap.end())
                    auxMap[auxNames_[i]] = makeAuxCol(auxTypes_[i]);

            while (cursor_ < entryEnd_ && idxValue() == target) {
                pvec.emplace_back(BranchControl::makeLorentz(coords_,
                    kinBuf_[0].value(), kinBuf_[1].value(),
                    kinBuf_[2].value(), kinBuf_[3].value()));
                appendAux(auxMap);
                ++cursor_;
                if (cursor_ < entryEnd_) tree_->GetEntry(cursor_);
            }
        }

        bool keyRange(Long64_t lo, Long64_t hi, Long64_t& outMin, Long64_t& outMax) {
            std::vector<std::pair<TBranch*, bool>> saved;
            if (TObjArray* branches = tree_->GetListOfBranches()) {
                const int n = branches->GetEntries();
                saved.reserve(static_cast<std::size_t>(n));
                for (int i = 0; i < n; ++i) {
                    TBranch* b = static_cast<TBranch*>(branches->At(i));
                    if (b == nullptr) continue;
                    const std::string bname = b->GetName();
                    if (bname == idxName_) continue;
                    const bool wasActive = !b->TestBit(kDoNotProcess);
                    saved.emplace_back(b, wasActive);
                    tree_->SetBranchStatus(bname.c_str(), 0);
                }
            }

            const Long64_t savedCursor = cursor_;
            bool found = false;
            for (Long64_t i = 0; i < entryEnd_; ++i) {
                tree_->GetEntry(i);
                const Long64_t v = idxValue();
                if (v < lo || v > hi) continue;
                if (!found) { outMin = outMax = v; found = true; }
                else        { outMin = std::min(outMin, v); outMax = std::max(outMax, v); }
            }

            for (auto& [b, wasActive] : saved)
                tree_->SetBranchStatus(b->GetName(), wasActive ? 1 : 0);

            cursor_ = savedCursor;
            if (cursor_ < totalEntries_) tree_->GetEntry(cursor_);
            return found;
        }

      private:
        Long64_t idxValue() const {
            return idxIsLong_ ? idxL_ : static_cast<Long64_t>(idxI_);
        }

        struct AuxBuf {
            float    f  = 0.f;  double   d  = 0.0;
            int32_t  i  = 0;    uint32_t u  = 0;
            int64_t  l  = 0;    uint64_t ul = 0;
            bool     b  = false;
        };

        void bindAux(const BranchSpec& bspec) {
            auxBufs_.emplace_back();
            AuxBuf& buf = auxBufs_.back();
            const char* n = bspec.name.c_str();
            switch (bspec.type) {
                case BranchType::Float:   tree_->SetBranchAddress(n, &buf.f);  break;
                case BranchType::Double:  tree_->SetBranchAddress(n, &buf.d);  break;
                case BranchType::Int32:   tree_->SetBranchAddress(n, &buf.i);  break;
                case BranchType::UInt32:  tree_->SetBranchAddress(n, &buf.u);  break;
                case BranchType::Int64:   tree_->SetBranchAddress(n, &buf.l);  break;
                case BranchType::UInt64:  tree_->SetBranchAddress(n, &buf.ul); break;
                case BranchType::Bool:    tree_->SetBranchAddress(n, &buf.b);  break;
                case BranchType::Char:
                case BranchType::String:
                case BranchType::Other:
                    throw std::runtime_error("[Probe] BranchType::Other not supported for '" + bspec.name + "'");
            }
        }

        static AuxColumn makeAuxCol(BranchType t) {
            AuxColumn col;
            switch (t) {
                case BranchType::Float:
                case BranchType::Double:  col.data = std::vector<double>{};   break;
                case BranchType::Int32:
                case BranchType::Int64:   col.data = std::vector<int64_t>{};  break;
                case BranchType::UInt32:
                case BranchType::UInt64:  col.data = std::vector<uint64_t>{}; break;
                case BranchType::Bool:    col.data = std::vector<bool>{};     break;
                case BranchType::Char:
                case BranchType::String:
                default: break;
            }
            return col;
        }

        void appendAux(std::unordered_map<std::string, AuxColumn>& m) {
            for (std::size_t i = 0; i < auxNames_.size(); ++i) {
                const AuxBuf& buf = auxBufs_[i];
                AuxColumn& col    = m[auxNames_[i]];
                switch (auxTypes_[i]) {
                    case BranchType::Float:   std::get<std::vector<double>>  (col.data).push_back(buf.f);  break;
                    case BranchType::Double:  std::get<std::vector<double>>  (col.data).push_back(buf.d);  break;
                    case BranchType::Int32:   std::get<std::vector<int64_t>> (col.data).push_back(buf.i);  break;
                    case BranchType::UInt32:  std::get<std::vector<uint64_t>>(col.data).push_back(buf.u);  break;
                    case BranchType::Int64:   std::get<std::vector<int64_t>> (col.data).push_back(buf.l);  break;
                    case BranchType::UInt64:  std::get<std::vector<uint64_t>>(col.data).push_back(buf.ul); break;
                    case BranchType::Bool:    std::get<std::vector<bool>>    (col.data).push_back(buf.b);  break;
                    case BranchType::Char:
                    case BranchType::String:
                    default: break;
                }
            }
        }

        std::string              label_;
        std::string              filepath_;
        CoordSpec                coords_;
        TTree*                   tree_         = nullptr;
        std::string              idxName_;
        Long64_t                 cursor_       = 0;
        Long64_t                 totalEntries_ = 0;
        Long64_t                 entryEnd_     = 0;
        Long64_t                 minKey_;
        Long64_t                 maxKey_;
        bool                     idxIsLong_   = false;
        Int_t                    idxI_         = 0;
        Long64_t                 idxL_         = 0;
        BranchControl::KinBuf    kinBuf_[4];
        std::vector<std::string> auxNames_;
        std::vector<BranchType>  auxTypes_;
        std::vector<AuxBuf>      auxBufs_;
    };

} // namespace Probe
