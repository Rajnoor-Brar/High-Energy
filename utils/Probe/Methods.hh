#pragma once

#include <algorithm>
#include <array>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <variant>

#include "TChain.h"
#include "TObjArray.h"
#include "TTreeReader.h"
#include "TTreeReaderValue.h"
#include "TTreeIndex.h"
#include "ROOT/TTreeProcessorMT.hxx"

#include "Probe/ParallelIMT.hh"
#include "Probe/Readers.hh"

namespace Probe {

inline FlatReader::FlatReader(TFile* file, const CollectionSpec& spec,
                              const std::string& filepath,
                              Long64_t minKey, Long64_t maxKey,
                              Bounds entryBounds,
                              bool hasEntryBounds)
            : label_(spec.label), filepath_(filepath),
              coords_(spec.coords), minKey_(minKey), maxKey_(maxKey) {
            tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
            if (!tree_)
                throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in file '" + filepath + "'");

            tree_->SetBranchStatus("*", 0);

            idxName_ = spec.indexBranches[0].name;
            TBranch* idxBr = BranchControl::requireBranch(tree_, idxName_, filepath);
            const BranchType it = RootUtil::detectBranchType(idxBr);
            if (it != BranchType::Int32 && it != BranchType::Int64 && it != BranchType::UInt32)
                throw std::runtime_error(
                    "[Probe] Index branch '" + idxName_ + "' in tree '" + spec.tree +
                    "' of file '" + filepath + "': must be Int_t, UInt_t, or Long64_t");
            if (spec.indexBranches[0].type != BranchType::Other && it != spec.indexBranches[0].type)
                throw std::runtime_error(
                    "[Probe] Type mismatch: index branch '" + idxName_ + "' declared as " + 
                    RootUtil::typeName(spec.indexBranches[0].type) +
                    ", actual " + RootUtil::typeName(it));
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

inline const std::string& FlatReader::label() const { return label_; }

inline EventKey FlatReader::currentKey() const { return EventKey{{idxValue()}}; }

inline bool FlatReader::exhausted()       const { return cursor_ >= entryEnd_; }

inline bool FlatReader::beyondMax()       const { return !exhausted() && idxValue() > maxKey_; }

inline void FlatReader::ensureLabel(Event& ev) const {
            ev.particles[label_];
            auto& auxMap = ev.aux[label_];
            for (std::size_t i = 0; i < auxNames_.size(); ++i)
                if (auxMap.find(auxNames_[i]) == auxMap.end())
                    auxMap[auxNames_[i]] = makeAuxCol(auxTypes_[i]);
        }

inline void FlatReader::drain(const EventKey& key, Event& ev) {
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

inline bool FlatReader::keyRange(Long64_t lo, Long64_t hi, Long64_t& outMin, Long64_t& outMax) {
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

inline Long64_t FlatReader::idxValue() const {
            return idxIsLong_ ? idxL_ : static_cast<Long64_t>(idxI_);
        }

inline void FlatReader::bindAux(const BranchSpec& bspec) {
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

inline AuxColumn FlatReader::makeAuxCol(BranchType t) {
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

inline void FlatReader::appendAux(std::unordered_map<std::string, AuxColumn>& m) {
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

inline VecReader::VecReader(TFile* file, const CollectionSpec& spec,
                            const std::string& filepath,
                            Long64_t minEntry,
                            Long64_t maxEntry)
            : label_(spec.label), filepath_(filepath), coords_(spec.coords) {
            TTree* tree = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
            if (!tree)
                throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in file '" + filepath + "'");

            reader_.SetTree(tree);
            totalEntries_ = tree->GetEntries();

            if (minEntry > 0 || maxEntry < totalEntries_ - 1) {
                const Long64_t lo = std::max<Long64_t>(0, minEntry);
                const Long64_t hi = std::min<Long64_t>(totalEntries_ - 1, maxEntry);
                reader_.SetEntriesRange(lo, hi + 1);
                totalEntries_ = hi - lo + 1;
            }

            tree->SetBranchStatus("*", 0);
            const auto knames = BranchControl::coordNames(spec.coords);
            for (int i = 0; i < 4; ++i) {
                BranchControl::requireBranch(tree, knames[i], filepath);
                tree->SetBranchStatus(knames[i].c_str(), 1);
                kinArrays_[i] = std::make_unique<TTreeReaderArray<float>>(reader_, knames[i].c_str());
            }
            for (const auto& bspec : spec.auxBranches) {
                BranchControl::requireBranch(tree, bspec.name, filepath);
                tree->SetBranchStatus(bspec.name.c_str(), 1);
                auxNames_.push_back(bspec.name);
                auxArrays_.push_back(std::make_unique<TTreeReaderArray<float>>(reader_, bspec.name.c_str()));
            }
        }

inline bool VecReader::next() { return reader_.Next(); }

inline Long64_t VecReader::totalEntries() const { return totalEntries_; }

inline void VecReader::fill(Event& ev) {
            const std::size_t nParts = kinArrays_[0]->GetSize();
            for (std::size_t ai = 0; ai < auxArrays_.size(); ++ai) {
                if (auxArrays_[ai]->GetSize() != nParts)
                    throw std::runtime_error(
                        "[Probe] VecReader '" + label_ + "': array length mismatch, branch '" +
                        auxNames_[ai] + "' has " + std::to_string(auxArrays_[ai]->GetSize()) +
                        " elements, kinematics have " + std::to_string(nParts) +
                        " at entry " + std::to_string(reader_.GetCurrentEntry()));
            }

            auto& pvec = ev.particles[label_];
            pvec.clear();
            pvec.reserve(nParts);
            for (std::size_t i = 0; i < nParts; ++i)
                pvec.emplace_back(BranchControl::makeLorentz(coords_,
                    (*kinArrays_[0])[i], (*kinArrays_[1])[i],
                    (*kinArrays_[2])[i], (*kinArrays_[3])[i]));

            auto& auxMap = ev.aux[label_];
            for (std::size_t ai = 0; ai < auxArrays_.size(); ++ai) {
                auto& col = auxMap[auxNames_[ai]];
                col.data  = std::vector<double>{};
                auto& vec = std::get<std::vector<double>>(col.data);
                vec.reserve(nParts);
                for (std::size_t i = 0; i < nParts; ++i)
                    vec.push_back((*auxArrays_[ai])[i]);
            }

            ev.index = reader_.GetCurrentEntry();
        }

inline EventStream::EventStream(const std::string& filepath,
                                const std::vector<CollectionSpec>& collections,
                                Long64_t minBound,
                                Long64_t maxBound,
                                std::size_t nEventsHint,
                                const std::vector<Bounds>& entryBounds)
            : filepath_(filepath), minBound_(minBound), maxBound_(maxBound) {
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
                if (!entryBounds.empty() && entryBounds.size() != collections.size())
                    throw std::runtime_error(
                        "[Probe] EventStream: entryBounds size does not match particle specs");

                const bool hasEntryBounds = !entryBounds.empty();
                for (std::size_t i = 0; i < collections.size(); ++i) {
                    const Bounds bounds = hasEntryBounds ? entryBounds[i] : Bounds{};
                    flatReaders_.push_back(std::make_unique<FlatReader>(
                        file_, collections[i], filepath, minBound, maxBound, bounds, hasEntryBounds));
                }

                if (nEventsHint > 0) {
                    if (minBound != std::numeric_limits<Long64_t>::min()
                        && maxBound != std::numeric_limits<Long64_t>::max()
                        && minBound <= maxBound) {
                        denseLo_ = minBound;
                        denseHi_ = maxBound;
                        nextKey_  = denseLo_;
                        nEvents_  = static_cast<std::size_t>(denseHi_ - denseLo_ + 1);
                    } else {
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

inline EventStream::~EventStream() { if (file_) { file_->Close(); delete file_; } }

inline bool EventStream::next() {
            current_.particles.clear();
            current_.aux.clear();
            return isVec_ ? nextVec() : nextFlat();
        }

inline const Event& EventStream::event()   const { return current_; }

inline Event        EventStream::takeEvent() { return std::move(current_); }

inline std::size_t  EventStream::nEvents() const { return nEvents_; }

inline std::size_t  EventStream::index()   const { return index_ == 0 ? 0 : index_ - 1; }

inline bool EventStream::nextFlat() {
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

inline bool EventStream::nextVec() {
            if (vecReaders_.empty()) return false;
            if (!vecReaders_[0]->next()) return false;
            for (std::size_t i = 1; i < vecReaders_.size(); ++i) vecReaders_[i]->next();
            for (auto& r : vecReaders_) r->fill(current_);
            ++index_;
            return true;
        }

namespace detail {

    struct IMTValueBinder {
        virtual ~IMTValueBinder() = default;
        virtual double asDouble() = 0;
        virtual Long64_t asInteger() = 0;
    };

    template<typename T>
    class IMTTypedBinder final : public IMTValueBinder {
      public:
        IMTTypedBinder(TTreeReader& reader, const std::string& name)
            : value_(reader, name.c_str()) {}

        double asDouble() override { return static_cast<double>(*value_); }
        Long64_t asInteger() override { return static_cast<Long64_t>(*value_); }

      private:
        TTreeReaderValue<T> value_;
    };

    inline std::unique_ptr<IMTValueBinder>
    makeIMTBinder(TTreeReader& reader, const std::string& name, BranchType type)
    {
        switch (type) {
            case BranchType::Double: return std::make_unique<IMTTypedBinder<Double_t>>(reader, name);
            case BranchType::Float:  return std::make_unique<IMTTypedBinder<Float_t>>(reader, name);
            case BranchType::Int32:  return std::make_unique<IMTTypedBinder<Int_t>>(reader, name);
            case BranchType::Int64:  return std::make_unique<IMTTypedBinder<Long64_t>>(reader, name);
            case BranchType::UInt32: return std::make_unique<IMTTypedBinder<UInt_t>>(reader, name);
            default:
                throw std::runtime_error(
                    "[Probe::IMT] unsupported branch type for '" + name + "'");
        }
    }

    inline std::array<BranchType, 4> coordBranchTypes(const CoordSpec& coords) {
        std::array<BranchType, 4> types{};
        std::visit([&](const auto& spec) {
            for (std::size_t i = 0; i < types.size(); ++i)
                types[i] = spec.branches[i].type;
        }, coords);
        return types;
    }

} // namespace detail

inline void ProbeIMT::readSpecInto(const CollectionSpec& spec,
                                   std::size_t specOrdinal,
                                   BufferT& buffer) {
            using PartialMap = std::unordered_map<Long64_t, std::vector<Lorentz>>;

            const Long64_t first = firstEventKey_;
            const Long64_t last  = first + Long64_t(eventCount_) - 1;

            std::mutex collectMutex;
            std::vector<std::unique_ptr<PartialMap>> collected;

            TChain chain(spec.tree.c_str());
            chain.Add(inputFile_.c_str());

            ROOT::TTreeProcessorMT processor(chain);
            processor.Process([&](TTreeReader& reader) {
                const BranchSpec& idx = spec.indexBranches[0];
                auto idxBinder = detail::makeIMTBinder(reader, idx.name, idx.type);

                const auto names = BranchControl::coordNames(spec.coords);
                const auto types = detail::coordBranchTypes(spec.coords);
                std::array<std::unique_ptr<detail::IMTValueBinder>, 4> momBinders;
                for (std::size_t i = 0; i < momBinders.size(); ++i)
                    momBinders[i] = detail::makeIMTBinder(reader, names[i], types[i]);

                auto local = std::make_unique<PartialMap>();

                while (reader.Next()) {
                    const Long64_t K = idxBinder->asInteger();
                    if (K > last)  break;
                    if (K < first) continue;
                    const double a = momBinders[0]->asDouble();
                    const double b = momBinders[1]->asDouble();
                    const double c = momBinders[2]->asDouble();
                    const double d = momBinders[3]->asDouble();
                    const Lorentz p = BranchControl::makeLorentz(spec.coords, a, b, c, d);
                    (*local)[K].push_back(p);
                }

                std::lock_guard<std::mutex> lock(collectMutex);
                collected.push_back(std::move(local));
            });

            for (auto& partial : collected) {
                for (auto& [K, particles] : *partial) {
                    auto& target = buffer[std::size_t(K - first)][specOrdinal];
                    target.insert(target.end(),
                                  std::make_move_iterator(particles.begin()),
                                  std::make_move_iterator(particles.end()));
                }
            }
        }

} // namespace Probe
