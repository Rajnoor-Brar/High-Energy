#pragma once

#include <algorithm>
#include <array>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <unordered_map>
#include <unordered_set>
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

inline FlatReader::FlatReader(TFile* file, const EventParticleSpec& spec,
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
            ev.particle[label_];
            auto& auxMap = ev.node[label_];
            for (std::size_t i = 0; i < auxNames_.size(); ++i)
                if (auxMap.find(auxNames_[i]) == auxMap.end())
                    auxMap[auxNames_[i]] = makeAuxCol(auxTypes_[i]);
        }

inline void FlatReader::drain(const EventKey& key, Event& ev) {
            const Long64_t target = key.components[0];
            auto& pvec   = ev.particle[label_];
            auto& auxMap = ev.node[label_];

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

// ── Phase 6: EventStream (polymorphic rewrite) ────────────────────────────────

inline EventStream::EventStream(const std::string& filepath,
                                const ProbeConfig& cfg,
                                Long64_t firstEvent,
                                Long64_t lastEvent,
                                std::size_t /*nEventsHint*/,
                                const std::vector<Bounds>& entryBounds)
    : filepath_(filepath)
    , firstEvent_(firstEvent), lastEvent_(lastEvent), nextEvent_(firstEvent)
    , nEvents_(lastEvent >= firstEvent
               ? static_cast<std::size_t>(lastEvent - firstEvent + 1) : 0)
{
    file_ = TFile::Open(filepath.c_str(), "READ");
    if (!file_ || file_->IsZombie())
        throw std::runtime_error("[Probe] Failed to open file '" + filepath + "'");

    const bool hasEB = !entryBounds.empty();

    // EventParticle specs
    std::size_t ebIdx = 0;
    for (const auto& pspec : cfg.eventParticles) {
        const Bounds b = (hasEB && ebIdx < entryBounds.size()) ? entryBounds[ebIdx] : Bounds{};
        if (pspec.indexBranches.empty()) {
            readers_.push_back(std::make_unique<EventParticleReaderArray>(
                file_, pspec, filepath, firstEvent, lastEvent));
        } else {
            readers_.push_back(std::make_unique<EventParticleReaderRowJoin>(
                file_, pspec, filepath, firstEvent, lastEvent, b, hasEB));
        }
        if (hasEB) ++ebIdx;
    }
    // EventNode specs
    for (const auto& nspec : cfg.eventNodes) {
        const Bounds b = (hasEB && ebIdx < entryBounds.size()) ? entryBounds[ebIdx] : Bounds{};
        if (nspec.indexBranches.empty()) {
            readers_.push_back(std::make_unique<EventNodeReaderArray>(
                file_, nspec, filepath, firstEvent, lastEvent));
        } else {
            readers_.push_back(std::make_unique<EventNodeReaderRowJoin>(
                file_, nspec, filepath, firstEvent, lastEvent, b, hasEB));
        }
        if (hasEB) ++ebIdx;
    }
}

inline EventStream::~EventStream() { if (file_) { file_->Close(); delete file_; } }

inline bool EventStream::next() {
    if (nextEvent_ > lastEvent_) return false;
    const Long64_t K = nextEvent_++;
    current_.particle.clear();
    current_.node.clear();
    current_.index = K;

    // Dedup seekToEvent for readers that share the same underlying TTree
    // (NanoAOD-style configs put multiple labels on one "Events" tree).
    std::unordered_set<const TTree*> tickled;
    for (auto& r : readers_) {
        if (tickled.insert(r->treePtr()).second)
            r->seekToEvent(K);
        r->readForEvent(K, current_);
    }
    ++index_;
    return true;
}

inline const Event& EventStream::event()    const { return current_; }
inline Event        EventStream::takeEvent()       { return std::move(current_); }
inline std::size_t  EventStream::nEvents()  const  { return nEvents_; }
inline std::size_t  EventStream::index()    const  { return index_ == 0 ? 0 : index_ - 1; }

// ── EventParticleReaderRowJoin non-virtual helpers ────────────────────────────

inline bool     EventParticleReaderRowJoin::exhausted()  const { return inner_->exhausted(); }
inline EventKey EventParticleReaderRowJoin::currentKey() const { return inner_->currentKey(); }
inline bool     EventParticleReaderRowJoin::keyRange(Long64_t lo, Long64_t hi,
                                                     Long64_t& outMin, Long64_t& outMax) const {
    return inner_->keyRange(lo, hi, outMin, outMax);
}

// ── Phase 6: FeedStream ───────────────────────────────────────────────────────

inline FeedStream::FeedStream(const std::string& filepath,
                              const ProbeConfig& cfg,
                              Long64_t firstEntry, Long64_t lastEntry)
    : filepath_(filepath)
    , firstEntry_(firstEntry), lastEntry_(lastEntry), nextEntry_(firstEntry)
{
    file_ = TFile::Open(filepath.c_str(), "READ");
    if (!file_ || file_->IsZombie())
        throw std::runtime_error("[Probe] Failed to open file '" + filepath + "'");

    for (const auto& pspec : cfg.feedParticles)
        readers_.push_back(std::make_unique<FeedParticleReader>(
            file_, pspec, filepath, firstEntry, lastEntry));

    for (const auto& nspec : cfg.feedNodes)
        readers_.push_back(std::make_unique<FeedNodeReader>(
            file_, nspec, filepath, firstEntry, lastEntry));
}

inline FeedStream::~FeedStream() { if (file_) { file_->Close(); delete file_; } }

inline bool FeedStream::next() {
    if (nextEntry_ > lastEntry_) return false;
    const Long64_t N = nextEntry_++;
    current_ = Feed{};
    current_.index = N;
    for (auto& r : readers_) r->readEntry(N, current_);
    return true;
}

inline Long64_t FeedStream::entryCount() const {
    return lastEntry_ >= firstEntry_ ? lastEntry_ - firstEntry_ + 1 : 0;
}

// ── Phase 4: BranchHandle implementations ────────────────────────────────────

namespace detail {

    // Single-switch factory for both scalar (TTreeReaderValue) and array (TTreeReaderArray)
    // branch handles. ReaderT is TTreeReaderValue or TTreeReaderArray.
    template<template<typename> class ReaderT>
    inline BranchHandle makeHandle(TTreeReader& reader,
                                   const std::string& name,
                                   BranchType type)
    {
        switch (type) {
            case BranchType::Float:   return BranchHandle(std::make_unique<ReaderT<float>>  (reader, name.c_str()));
            case BranchType::Double:  return BranchHandle(std::make_unique<ReaderT<double>> (reader, name.c_str()));
            case BranchType::Int32:   return BranchHandle(std::make_unique<ReaderT<int32_t>>(reader, name.c_str()));
            case BranchType::UInt32:  return BranchHandle(std::make_unique<ReaderT<uint32_t>>(reader, name.c_str()));
            case BranchType::Int64:   return BranchHandle(std::make_unique<ReaderT<int64_t>>(reader, name.c_str()));
            case BranchType::UInt64:  return BranchHandle(std::make_unique<ReaderT<uint64_t>>(reader, name.c_str()));
            case BranchType::Bool:    return BranchHandle(std::make_unique<ReaderT<bool>>   (reader, name.c_str()));
            default:
                throw std::runtime_error("[Probe] makeHandle: unsupported type for '" + name + "'");
        }
    }

    inline BranchHandle makeScalarHandle(TTreeReader& r, const std::string& n, BranchType t) {
        return makeHandle<TTreeReaderValue>(r, n, t);
    }
    inline BranchHandle makeArrayHandle(TTreeReader& r, const std::string& n, BranchType t) {
        return makeHandle<TTreeReaderArray>(r, n, t);
    }

inline AuxValue BranchHandle::readScalar() const {
    return std::visit([](const auto& uptr) -> AuxValue {
        using ReaderT = typename std::decay_t<decltype(uptr)>::element_type;
        if constexpr (detail::IsReaderValue<ReaderT>::value) {
            using ElemT = std::decay_t<decltype(**uptr)>;
            return AuxValue{static_cast<ElemT>(**uptr)};
        } else {
            // Unreachable when called on a scalar handle
            throw std::runtime_error("[Probe] BranchHandle::readScalar called on array branch");
        }
    }, h);
}

inline AuxColumn BranchHandle::readArray() const {
    return std::visit([](const auto& uptr) -> AuxColumn {
        using ReaderT = typename std::decay_t<decltype(uptr)>::element_type;
        if constexpr (detail::IsReaderArray<ReaderT>::value) {
            using ElemT = std::decay_t<decltype((*uptr)[0])>;
            const std::size_t n = uptr->GetSize();
            std::vector<ElemT> vec;
            vec.reserve(n);
            for (std::size_t i = 0; i < n; ++i) vec.push_back((*uptr)[i]);
            AuxColumn col;
            col.data = std::move(vec);
            return col;
        } else {
            throw std::runtime_error("[Probe] BranchHandle::readArray called on scalar branch");
        }
    }, h);
}

inline void BranchHandle::appendInto(AuxColumn& col) const {
    std::visit([&col](const auto& uptr) {
        using ReaderT = typename std::decay_t<decltype(uptr)>::element_type;
        if constexpr (detail::IsReaderValue<ReaderT>::value) {
            using ElemT = std::decay_t<decltype(**uptr)>;
            std::get<std::vector<ElemT>>(col.data).push_back(**uptr);
        } else {
            throw std::runtime_error("[Probe] BranchHandle::appendInto called on array branch");
        }
    }, h);
}

// ── EventParticleReaderArray ──────────────────────────────────────────────────

inline EventParticleReaderArray::EventParticleReaderArray(
    TFile* file, const EventParticleSpec& spec,
    const std::string& filepath, Long64_t firstEntry, Long64_t lastEntry)
    : label_(spec.label), treeName_(spec.tree), coords_(spec.coords)
    , firstEntry_(firstEntry), lastEntry_(lastEntry)
{
    tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
    if (!tree_)
        throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in '" + filepath + "'");

    reader_.SetTree(tree_);

    // Restrict the reader to [firstEntry, lastEntry]
    const Long64_t total = tree_->GetEntries();
    const Long64_t lo = std::max<Long64_t>(0, firstEntry);
    const Long64_t hi = std::min<Long64_t>(total - 1, lastEntry);
    if (lo <= hi) reader_.SetEntriesRange(lo, hi + 1);

    tree_->SetBranchStatus("*", 0);
    const auto knames = BranchControl::coordNames(spec.coords);
    for (int i = 0; i < 4; ++i) {
        BranchControl::requireBranch(tree_, knames[i], filepath);
        tree_->SetBranchStatus(knames[i].c_str(), 1);
        kinArrays_[i] = std::make_unique<TTreeReaderArray<float>>(reader_, knames[i].c_str());
    }
    for (const auto& bspec : spec.auxBranches) {
        BranchControl::requireBranch(tree_, bspec.name, filepath);
        tree_->SetBranchStatus(bspec.name.c_str(), 1);
        auxNames_.push_back(bspec.name);
        // Aux branches in a per-entry array source are always array-typed leaves.
        const BranchType t = (bspec.type == BranchType::Other) ? BranchType::Float : bspec.type;
        auxHandles_.push_back(detail::makeArrayHandle(reader_, bspec.name, t));
    }
}

inline void EventParticleReaderArray::seekToEvent(Long64_t K) {
    reader_.SetEntry(K);
}

inline void EventParticleReaderArray::readForEvent(Long64_t K, Event& out) {
    const std::size_t nParts = kinArrays_[0]->GetSize();
    auto& pvec = out.particle[label_];
    pvec.clear();
    pvec.reserve(nParts);
    for (std::size_t i = 0; i < nParts; ++i)
        pvec.emplace_back(BranchControl::makeLorentz(coords_,
            (*kinArrays_[0])[i], (*kinArrays_[1])[i],
            (*kinArrays_[2])[i], (*kinArrays_[3])[i]));

    auto& auxMap = out.node[label_];
    for (std::size_t ai = 0; ai < auxHandles_.size(); ++ai)
        auxMap[auxNames_[ai]] = auxHandles_[ai].readArray();

    out.index = K;
}

// ── EventParticleReaderRowJoin ────────────────────────────────────────────────

inline EventParticleReaderRowJoin::EventParticleReaderRowJoin(
    TFile* file, const EventParticleSpec& spec,
    const std::string& filepath, Long64_t minKey, Long64_t maxKey,
    Bounds entryBounds, bool hasEntryBounds)
    : inner_(std::make_unique<FlatReader>(file, spec, filepath, minKey, maxKey,
                                          entryBounds, hasEntryBounds))
    , minKey_(minKey), maxKey_(maxKey)
{}

inline void EventParticleReaderRowJoin::readForEvent(Long64_t K, Event& out) {
    inner_->ensureLabel(out);
    const EventKey key{{K}};
    if (!inner_->exhausted() && inner_->currentKey().components[0] == K)
        inner_->drain(key, out);
}

inline std::string EventParticleReaderRowJoin::treeName() const {
    return inner_->treePtr() ? inner_->treePtr()->GetName() : "";
}

inline const TTree* EventParticleReaderRowJoin::treePtr() const {
    return inner_->treePtr();
}

// ── EventNodeReaderArray ──────────────────────────────────────────────────────

inline EventNodeReaderArray::EventNodeReaderArray(
    TFile* file, const EventNodeSpec& spec,
    const std::string& filepath, Long64_t firstEntry, Long64_t lastEntry)
    : label_(spec.label), treeName_(spec.tree)
    , firstEntry_(firstEntry), lastEntry_(lastEntry)
{
    tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
    if (!tree_)
        throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in '" + filepath + "'");

    reader_.SetTree(tree_);

    const Long64_t total = tree_->GetEntries();
    const Long64_t lo = std::max<Long64_t>(0, firstEntry);
    const Long64_t hi = std::min<Long64_t>(total - 1, lastEntry);
    if (lo <= hi) reader_.SetEntriesRange(lo, hi + 1);

    tree_->SetBranchStatus("*", 0);
    for (const auto& bspec : spec.branches) {
        BranchControl::requireBranch(tree_, bspec.name, filepath);
        tree_->SetBranchStatus(bspec.name.c_str(), 1);
        branchNames_.push_back(bspec.name);
        const BranchType t = (bspec.type == BranchType::Other) ? BranchType::Float : bspec.type;
        handles_.push_back(detail::makeArrayHandle(reader_, bspec.name, t));
    }
}

inline void EventNodeReaderArray::seekToEvent(Long64_t K) {
    reader_.SetEntry(K);
}

inline void EventNodeReaderArray::readForEvent(Long64_t K, Event& out) {
    auto& nodeMap = out.node[label_];
    for (std::size_t i = 0; i < handles_.size(); ++i)
        nodeMap[branchNames_[i]] = handles_[i].readArray();
    out.index = K;
}

// ── EventNodeReaderRowJoin ────────────────────────────────────────────────────

inline EventNodeReaderRowJoin::EventNodeReaderRowJoin(
    TFile* file, const EventNodeSpec& spec,
    const std::string& filepath, Long64_t minKey, Long64_t maxKey,
    Bounds entryBounds, bool hasEntryBounds)
    : label_(spec.label), treeName_(spec.tree), minKey_(minKey), maxKey_(maxKey)
{
    tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
    if (!tree_)
        throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in '" + filepath + "'");

    tree_->SetBranchStatus("*", 0);

    // Index branch
    const std::string& idxName = spec.indexBranches[0].name;
    TBranch* idxBr = BranchControl::requireBranch(tree_, idxName, filepath);
    const BranchType it = RootUtil::detectBranchType(idxBr);
    idxIsLong_ = (it == BranchType::Int64);
    tree_->SetBranchStatus(idxName.c_str(), 1);
    if (idxIsLong_) tree_->SetBranchAddress(idxName.c_str(), &idxL_);
    else            tree_->SetBranchAddress(idxName.c_str(), &idxI_);

    for (const auto& bspec : spec.branches) {
        TBranch* br = BranchControl::requireBranch(tree_, bspec.name, filepath);
        BranchControl::requireType(br, bspec.type, filepath);
        tree_->SetBranchStatus(bspec.name.c_str(), 1);
        branchNames_.push_back(bspec.name);
        branchTypes_.push_back(bspec.type);
        bindBranch(bspec);
    }

    tree_->SetCacheSize(10 * 1024 * 1024);
    tree_->AddBranchToCache("*", kTRUE);
    tree_->StopCacheLearningPhase();

    totalEntries_ = tree_->GetEntries();
    entryEnd_     = totalEntries_;

    if (hasEntryBounds && !entryBounds.valid()) {
        cursor_ = 0; entryEnd_ = 0; return;
    }
    if (hasEntryBounds) {
        cursor_   = std::max<Long64_t>(0, entryBounds.first);
        entryEnd_ = std::min(totalEntries_, entryBounds.last + 1);
        if (cursor_ >= entryEnd_) { cursor_ = entryEnd_; return; }
        tree_->GetEntry(cursor_);
        while (cursor_ < entryEnd_ && idxVal() < minKey) { ++cursor_; if (cursor_ < entryEnd_) tree_->GetEntry(cursor_); }
        return;
    }
    if (totalEntries_ > 0) tree_->GetEntry(cursor_);
    while (cursor_ < entryEnd_ && idxVal() < minKey) { ++cursor_; if (cursor_ < entryEnd_) tree_->GetEntry(cursor_); }
}

inline void EventNodeReaderRowJoin::readForEvent(Long64_t K, Event& out) {
    auto& nodeMap = out.node[label_];
    for (std::size_t i = 0; i < branchNames_.size(); ++i)
        if (nodeMap.find(branchNames_[i]) == nodeMap.end())
            nodeMap[branchNames_[i]] = makeAuxCol(branchTypes_[i]);

    while (cursor_ < entryEnd_ && idxVal() == K) {
        appendRow(nodeMap);
        ++cursor_;
        if (cursor_ < entryEnd_) tree_->GetEntry(cursor_);
    }
    out.index = K;
}

inline AuxColumn EventNodeReaderRowJoin::makeAuxCol(BranchType t) {
    AuxColumn col;
    switch (t) {
        case BranchType::Float:   col.data = std::vector<float>{};   break;
        case BranchType::Double:  col.data = std::vector<double>{};  break;
        case BranchType::Int32:   col.data = std::vector<int32_t>{}; break;
        case BranchType::UInt32:  col.data = std::vector<uint32_t>{}; break;
        case BranchType::Int64:   col.data = std::vector<int64_t>{}; break;
        case BranchType::UInt64:  col.data = std::vector<uint64_t>{}; break;
        case BranchType::Bool:    col.data = std::vector<bool>{};    break;
        default: break;
    }
    return col;
}

inline void EventNodeReaderRowJoin::bindBranch(const BranchSpec& bspec) {
    bufs_.emplace_back();
    NodeBuf& buf = bufs_.back();
    const char* n = bspec.name.c_str();
    switch (bspec.type) {
        case BranchType::Float:  tree_->SetBranchAddress(n, &buf.f);   break;
        case BranchType::Double: tree_->SetBranchAddress(n, &buf.d);   break;
        case BranchType::Int32:  tree_->SetBranchAddress(n, &buf.i32); break;
        case BranchType::UInt32: tree_->SetBranchAddress(n, &buf.u32); break;
        case BranchType::Int64:  tree_->SetBranchAddress(n, &buf.i64); break;
        case BranchType::UInt64: tree_->SetBranchAddress(n, &buf.u64); break;
        case BranchType::Bool:   tree_->SetBranchAddress(n, &buf.b);   break;
        default: throw std::runtime_error("[Probe] EventNodeReaderRowJoin: unsupported type for '" + bspec.name + "'");
    }
}

inline void EventNodeReaderRowJoin::appendRow(std::unordered_map<std::string, AuxColumn>& nodeMap) {
    for (std::size_t i = 0; i < branchNames_.size(); ++i) {
        const NodeBuf& buf = bufs_[i];
        AuxColumn& col = nodeMap[branchNames_[i]];
        switch (branchTypes_[i]) {
            case BranchType::Float:  std::get<std::vector<float>>  (col.data).push_back(buf.f);   break;
            case BranchType::Double: std::get<std::vector<double>> (col.data).push_back(buf.d);   break;
            case BranchType::Int32:  std::get<std::vector<int32_t>>(col.data).push_back(buf.i32); break;
            case BranchType::UInt32: std::get<std::vector<uint32_t>>(col.data).push_back(buf.u32); break;
            case BranchType::Int64:  std::get<std::vector<int64_t>>(col.data).push_back(buf.i64); break;
            case BranchType::UInt64: std::get<std::vector<uint64_t>>(col.data).push_back(buf.u64); break;
            case BranchType::Bool:   std::get<std::vector<bool>>   (col.data).push_back(buf.b);   break;
            default: break;
        }
    }
}

// ── Phase 5: helpers ─────────────────────────────────────────────────────────

    // Convert AuxColumn (vector-only variant) into the matching AuxValue alternative.
    // AuxColumn.data holds vector<T>; AuxValue holds the same vector<T> alternatives
    // at indices 7–13, so visiting and moving works directly.
    inline AuxValue auxColToValue(AuxColumn col) {
        return std::visit([](auto&& vec) -> AuxValue {
            return AuxValue{std::move(vec)};
        }, std::move(col.data));
    }

    // Extract a scalar AuxValue as double (throws if the AuxValue holds a vector).
    inline double scalarToDouble(const AuxValue& v) {
        return std::visit([](const auto& x) -> double {
            using T = std::decay_t<decltype(x)>;
            if constexpr (std::is_scalar_v<T>)
                return static_cast<double>(x);
            else
                throw std::runtime_error("[Probe] scalarToDouble: AuxValue holds a vector, not a scalar");
        }, v);
    }

// ── Phase 5: FeedParticleReader ───────────────────────────────────────────────

inline FeedParticleReader::FeedParticleReader(
    TFile* file, const FeedParticleSpec& spec,
    const std::string& filepath, Long64_t firstEntry, Long64_t lastEntry)
    : label_(spec.label), treeName_(spec.tree), coords_(spec.coords)
{
    tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
    if (!tree_)
        throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in '" + filepath + "'");

    reader_.SetTree(tree_);

    const Long64_t total = tree_->GetEntries();
    const Long64_t lo = std::max<Long64_t>(0, firstEntry);
    const Long64_t hi = std::min<Long64_t>(total - 1, lastEntry);
    if (lo <= hi) {
        reader_.SetEntriesRange(lo, hi + 1);
        entryCount_ = hi - lo + 1;
    } else {
        entryCount_ = 0;
    }

    tree_->SetBranchStatus("*", 0);
    const auto knames = BranchControl::coordNames(spec.coords);
    kinHandles_.reserve(4);
    std::visit([&](const auto& cspec) {
        for (int i = 0; i < 4; ++i) {
            const BranchType t = (cspec.branches[i].type == BranchType::Other)
                                 ? BranchType::Float : cspec.branches[i].type;
            BranchControl::requireBranch(tree_, knames[i], filepath);
            tree_->SetBranchStatus(knames[i].c_str(), 1);
            kinHandles_.push_back(detail::makeScalarHandle(reader_, knames[i], t));
        }
    }, spec.coords);
}

inline void FeedParticleReader::readEntry(Long64_t N, Feed& out) {
    reader_.SetEntry(N);
    const double a = detail::scalarToDouble(kinHandles_[0].readScalar());
    const double b = detail::scalarToDouble(kinHandles_[1].readScalar());
    const double c = detail::scalarToDouble(kinHandles_[2].readScalar());
    const double d = detail::scalarToDouble(kinHandles_[3].readScalar());
    out.particle[label_] = BranchControl::makeLorentz(coords_, a, b, c, d);
    out.index = N;
}

// ── Phase 5: FeedNodeReader ───────────────────────────────────────────────────

inline FeedNodeReader::FeedNodeReader(
    TFile* file, const FeedNodeSpec& spec,
    const std::string& filepath, Long64_t firstEntry, Long64_t lastEntry)
    : label_(spec.label), treeName_(spec.tree)
{
    tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
    if (!tree_)
        throw std::runtime_error("[Probe] Missing tree '" + spec.tree + "' in '" + filepath + "'");

    reader_.SetTree(tree_);

    const Long64_t total = tree_->GetEntries();
    const Long64_t lo = std::max<Long64_t>(0, firstEntry);
    const Long64_t hi = std::min<Long64_t>(total - 1, lastEntry);
    if (lo <= hi) {
        reader_.SetEntriesRange(lo, hi + 1);
        entryCount_ = hi - lo + 1;
    } else {
        entryCount_ = 0;
    }

    tree_->SetBranchStatus("*", 0);
    for (const auto& bspec : spec.branches) {
        TBranch* br = BranchControl::requireBranch(tree_, bspec.name, filepath);
        tree_->SetBranchStatus(bspec.name.c_str(), 1);

        // Auto-detect: if branch title contains "[", treat as variable-length array.
        const std::string title = br->GetTitle() ? br->GetTitle() : "";
        const bool arr = (title.find('[') != std::string::npos);
        const BranchType t = (bspec.type == BranchType::Other) ? BranchType::Float : bspec.type;

        branchNames_.push_back(bspec.name);
        isArray_.push_back(arr);
        if (arr)
            handles_.push_back(detail::makeArrayHandle(reader_, bspec.name, t));
        else
            handles_.push_back(detail::makeScalarHandle(reader_, bspec.name, t));
    }
}

inline void FeedNodeReader::readEntry(Long64_t N, Feed& out) {
    reader_.SetEntry(N);
    auto& nodeMap = out.node[label_];
    for (std::size_t i = 0; i < handles_.size(); ++i) {
        if (isArray_[i])
            nodeMap[branchNames_[i]] = detail::auxColToValue(handles_[i].readArray());
        else
            nodeMap[branchNames_[i]] = handles_[i].readScalar();
    }
    out.index = N;
}

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

inline void ProbeIMT::readSpecInto(const EventParticleSpec& spec,
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
