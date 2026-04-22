#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <limits>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <utility>
#include <variant>
#include <vector>

#include "Analysis.hh"
#include "Config.hh"
#include "TBranch.h"
#include "TFile.h"
#include "TTree.h"
#include "TTreeReader.h"
#include "TTreeReaderArray.h"
#include "TROOT.h"
#include "Math/Vector4D.h"

namespace Explore {
    using Lorentz = Analysis::Lorentz;

    // ── Coordinate specs ─────────────────────────────────────────────────────
    struct CartesianSpec  { std::string px, py, pz, E; };
    struct PtEtaPhiESpec  { std::string pt, eta, phi, E; };
    struct PtEtaPhiMSpec  { std::string pt, eta, phi, M; };
    using CoordSpec = std::variant<CartesianSpec, PtEtaPhiESpec, PtEtaPhiMSpec>;

    // ── Branch type declarations ──────────────────────────────────────────────
    enum class BranchType         { Float, Double, Int32, UInt32, Int64, UInt64, Bool, Other };
    enum class MissingBranchPolicy{ Error };   // v1: only Error implemented

    struct BranchSpec {
        std::string          name;
        BranchType           type;
        MissingBranchPolicy  policy = MissingBranchPolicy::Error;
    };

    // ── Schema descriptors ───────────────────────────────────────────────────
    struct CollectionSpec {
        std::string              label;
        std::string              tree;
        CoordSpec                coords;
        std::vector<std::string> indexBranches;   // empty → VecReader; non-empty → FlatReader
        std::vector<BranchSpec>  auxBranches;
    };

    struct ScalarSpec {
        std::string name;
        std::string tree;
        std::string branch;
        BranchType  type;
    };

    // ── Typed aux column ─────────────────────────────────────────────────────
    struct AuxColumn {
        std::variant<
            std::vector<int64_t>,
            std::vector<uint64_t>,
            std::vector<double>,
            std::vector<bool>
        > data;

        template<typename T>
        const std::vector<T>& as() const {
            if (const auto* p = std::get_if<std::vector<T>>(&data)) return *p;
            throw std::runtime_error("[Explore] AuxColumn type mismatch");
        }
        void clear() { std::visit([](auto& v){ v.clear(); }, data); }
    };

    using ScalarValue = std::variant<int64_t, uint64_t, double, bool>;

    // ── Event key (supports future composite keys) ────────────────────────────
    struct EventKey {
        std::vector<Long64_t> components;
        bool operator< (const EventKey& o) const { return components <  o.components; }
        bool operator==(const EventKey& o) const { return components == o.components; }
        bool operator!=(const EventKey& o) const { return !(*this == o); }
    };

    // ── Event ─────────────────────────────────────────────────────────────────
    struct Event {
        Long64_t index{-1};
        std::unordered_map<std::string, std::vector<Lorentz>>                        particles;
        std::unordered_map<std::string, std::unordered_map<std::string, AuxColumn>>  aux;
        std::unordered_map<std::string, ScalarValue>                                 scalars;

        const std::vector<Lorentz>& operator[](const std::string& label) const {
            auto it = particles.find(label);
            if (it == particles.end())
                throw std::runtime_error("[Explore] Event: unknown label '" + label + "'");
            return it->second;
        }
        std::size_t n(const std::string& label) const {
            auto it = particles.find(label);
            return it == particles.end() ? 0 : it->second.size();
        }
        template<typename T>
        const std::vector<T>& column(const std::string& label, const std::string& col) const {
            auto li = aux.find(label);
            if (li == aux.end())
                throw std::runtime_error("[Explore] Event: unknown label '" + label + "'");
            auto ci = li->second.find(col);
            if (ci == li->second.end())
                throw std::runtime_error("[Explore] Event: unknown column '" + col + "' in '" + label + "'");
            return ci->second.as<T>();
        }
        template<typename T>
        T scalar(const std::string& name) const {
            auto it = scalars.find(name);
            if (it == scalars.end())
                throw std::runtime_error("[Explore] Event: unknown scalar '" + name + "'");
            if (const auto* p = std::get_if<T>(&it->second)) return *p;
            throw std::runtime_error("[Explore] Event: scalar '" + name + "' type mismatch");
        }
    };

    // ──────────────────────────────────────────────────────────────────────────
    // Internal utilities
    // ──────────────────────────────────────────────────────────────────────────
    namespace detail {

        struct Partition { Long64_t firstEvent; Long64_t lastEvent; };

        inline void enableRootThreadSafety() {
            static std::once_flag flag;
            std::call_once(flag, []{ ROOT::EnableThreadSafety(); });
        }

        inline std::string branchTypeStr(BranchType t) {
            switch (t) {
                case BranchType::Float:   return "Float_t";
                case BranchType::Double:  return "Double_t";
                case BranchType::Int32:   return "Int_t";
                case BranchType::UInt32:  return "UInt_t";
                case BranchType::Int64:   return "Long64_t";
                case BranchType::UInt64:  return "ULong64_t";
                case BranchType::Bool:    return "Bool_t";
                case BranchType::Other:   return "other";
            }
            return "unknown";
        }

        // Parse the ROOT type code from TBranch::GetTitle() — format is "branchname/T"
        // where T is one of: F=float, D=double, I=int, i=uint, L=Long64, l=ULong64, O=bool
        inline BranchType detectType(TBranch* br) {
            const std::string title = br->GetTitle();
            if (title.size() >= 2 && title[title.size() - 2] == '/') {
                switch (title.back()) {
                    case 'F': return BranchType::Float;
                    case 'D': return BranchType::Double;
                    case 'I': return BranchType::Int32;
                    case 'i': return BranchType::UInt32;
                    case 'L': return BranchType::Int64;
                    case 'l': return BranchType::UInt64;
                    case 'O': return BranchType::Bool;
                    default:  break;
                }
            }
            return BranchType::Other;
        }

        inline TBranch* requireBranch(TTree* tree, const std::string& name, const std::string& file) {
            TBranch* br = tree->GetBranch(name.c_str());
            if (br == nullptr)
                throw std::runtime_error(
                    "[Explore] Missing branch '" + name +
                    "' in tree '"   + tree->GetName() +
                    "' of file '"   + file + "'");
            return br;
        }

        inline void requireType(TBranch* br, BranchType expected, const std::string& file) {
            const BranchType actual = detectType(br);
            if (actual != expected)
                throw std::runtime_error(
                    "[Explore] Type mismatch: branch '" + std::string(br->GetName()) +
                    "' in tree '"   + std::string(br->GetTree()->GetName()) +
                    "' of file '"   + file +
                    "': declared "  + branchTypeStr(expected) +
                    ", actual "     + branchTypeStr(actual));
        }

        // Scalar kinematic buffer — auto-detects Float vs Double at bind time
        struct KinBuf {
            bool   isFloat = false;
            float  f = 0.f;
            double d = 0.0;
            double value() const { return isFloat ? static_cast<double>(f) : d; }

            void bind(TTree* tree, const std::string& name, const std::string& file) {
                TBranch* br = requireBranch(tree, name, file);
                const BranchType t = detectType(br);
                if (t != BranchType::Float && t != BranchType::Double)
                    throw std::runtime_error(
                        "[Explore] Kinematic branch '" + name +
                        "' in tree '" + std::string(tree->GetName()) +
                        "' of file '" + file +
                        "': must be Float_t or Double_t, got " + branchTypeStr(t));
                isFloat = (t == BranchType::Float);
                tree->SetBranchStatus(name.c_str(), 1);
                if (isFloat) tree->SetBranchAddress(name.c_str(), &f);
                else         tree->SetBranchAddress(name.c_str(), &d);
            }
        };

        // Returns the four branch names declared in a CoordSpec, in order
        inline std::vector<std::string> coordNames(const CoordSpec& cs) {
            return std::visit([](const auto& s) -> std::vector<std::string> {
                using T = std::decay_t<decltype(s)>;
                if constexpr      (std::is_same_v<T, CartesianSpec>)
                    return { s.px, s.py, s.pz, s.E };
                else if constexpr (std::is_same_v<T, PtEtaPhiESpec>)
                    return { s.pt, s.eta, s.phi, s.E };
                else
                    return { s.pt, s.eta, s.phi, s.M };
            }, cs);
        }

        // Build a PxPyPzEVector from four scalar values and a coordinate spec
        inline Lorentz makeLorentz(const CoordSpec& cs, double a, double b, double c, double d) {
            return std::visit([&](const auto& s) -> Lorentz {
                using T = std::decay_t<decltype(s)>;
                (void)s;
                if constexpr (std::is_same_v<T, CartesianSpec>) {
                    return Lorentz(a, b, c, d);   // px, py, pz, E
                } else if constexpr (std::is_same_v<T, PtEtaPhiESpec>) {
                    ROOT::Math::PtEtaPhiEVector v(a, b, c, d);
                    return Lorentz(v.Px(), v.Py(), v.Pz(), v.E());
                } else {                           // PtEtaPhiMSpec
                    ROOT::Math::PtEtaPhiMVector v(a, b, c, d);
                    return Lorentz(v.Px(), v.Py(), v.Pz(), v.E());
                }
            }, cs);
        }

        inline std::vector<Partition> partitionEvents(const std::vector<Long64_t>& ids, std::size_t n) {
            std::vector<Partition> parts;
            if (ids.empty() || n == 0) return parts;
            const std::size_t chunk = (ids.size() + n - 1) / n;
            for (std::size_t i = 0; i < ids.size(); i += chunk) {
                const std::size_t j = std::min(ids.size(), i + chunk) - 1;
                parts.push_back({ids[i], ids[j]});
            }
            return parts;
        }

        // Scan one tree's index branch and insert distinct keys into 'out'
        inline void scanIndexBranch(TFile* file,
                                     const std::string& treeName,
                                     const std::string& idxName,
                                     std::set<Long64_t>& out,
                                     const std::string& filepath)
        {
            TTree* tree = dynamic_cast<TTree*>(file->Get(treeName.c_str()));
            if (!tree)
                throw std::runtime_error("[Explore] Missing tree '" + treeName + "' in file '" + filepath + "'");

            TBranch* br = requireBranch(tree, idxName, filepath);
            const BranchType t = detectType(br);
            if (t != BranchType::Int32 && t != BranchType::Int64 && t != BranchType::UInt32)
                throw std::runtime_error(
                    "[Explore] Index branch '" + idxName + "' in tree '" + treeName +
                    "' of file '" + filepath + "' must be Int_t, UInt_t, or Long64_t");

            tree->SetBranchStatus("*", 0);
            tree->SetBranchStatus(idxName.c_str(), 1);
            const Long64_t n = tree->GetEntries();

            if (t == BranchType::Int64) {
                Long64_t val = 0;
                tree->SetBranchAddress(idxName.c_str(), &val);
                Long64_t last = std::numeric_limits<Long64_t>::min();
                for (Long64_t i = 0; i < n; ++i) {
                    tree->GetEntry(i);
                    if (val != last) { last = val; out.insert(last); }
                }
            } else {
                Int_t val = 0;
                tree->SetBranchAddress(idxName.c_str(), &val);
                Int_t last = std::numeric_limits<Int_t>::min();
                for (Long64_t i = 0; i < n; ++i) {
                    tree->GetEntry(i);
                    if (val != last) { last = val; out.insert(static_cast<Long64_t>(last)); }
                }
            }
            tree->ResetBranchAddresses();
        }

    } // namespace detail

    // ──────────────────────────────────────────────────────────────────────────
    // FlatReader — one TTree, one row per particle, joined by an integer key
    // ──────────────────────────────────────────────────────────────────────────
    class FlatReader {
      public:
        FlatReader(TFile* file, const CollectionSpec& spec,
                   const std::string& filepath,
                   Long64_t minKey, Long64_t maxKey)
            : label_(spec.label), filepath_(filepath),
              coords_(spec.coords), minKey_(minKey), maxKey_(maxKey)
        {
            tree_ = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
            if (!tree_)
                throw std::runtime_error("[Explore] Missing tree '" + spec.tree + "' in file '" + filepath + "'");

            tree_->SetBranchStatus("*", 0);

            // Index branch (v1: single key, Int32 or Int64)
            const std::string& idxName = spec.indexBranches[0];
            TBranch* idxBr = detail::requireBranch(tree_, idxName, filepath);
            const BranchType it = detail::detectType(idxBr);
            if (it != BranchType::Int32 && it != BranchType::Int64 && it != BranchType::UInt32)
                throw std::runtime_error(
                    "[Explore] Index branch '" + idxName + "' in tree '" + spec.tree +
                    "' of file '" + filepath + "': must be Int_t, UInt_t, or Long64_t");
            idxIsLong_ = (it == BranchType::Int64);
            tree_->SetBranchStatus(idxName.c_str(), 1);
            if (idxIsLong_) tree_->SetBranchAddress(idxName.c_str(), &idxL_);
            else            tree_->SetBranchAddress(idxName.c_str(), &idxI_);

            // Kinematic branches
            const auto knames = detail::coordNames(spec.coords);
            for (int i = 0; i < 4; ++i)
                kinBuf_[i].bind(tree_, knames[i], filepath);

            // Aux branches
            for (const auto& bspec : spec.auxBranches) {
                TBranch* br = detail::requireBranch(tree_, bspec.name, filepath);
                detail::requireType(br, bspec.type, filepath);
                tree_->SetBranchStatus(bspec.name.c_str(), 1);
                auxNames_.push_back(bspec.name);
                auxTypes_.push_back(bspec.type);
                bindAux(bspec);
            }

            totalEntries_ = tree_->GetEntries();
            if (totalEntries_ > 0) tree_->GetEntry(cursor_);

            // Advance past minKey
            while (cursor_ < totalEntries_ && idxValue() < minKey_) {
                ++cursor_;
                if (cursor_ < totalEntries_) tree_->GetEntry(cursor_);
            }
        }

        FlatReader(const FlatReader&)            = delete;
        FlatReader& operator=(const FlatReader&) = delete;

        const std::string& label() const { return label_; }

        EventKey currentKey() const { return EventKey{{idxValue()}}; }
        bool exhausted()       const { return cursor_ >= totalEntries_; }
        bool beyondMax()       const { return !exhausted() && idxValue() > maxKey_; }

        // Ensure map entries exist for this reader's label on the current event,
        // regardless of whether drain() will be called. Keeps Event shape stable
        // when readers have asymmetric event-key coverage.
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

            // Ensure aux column entries exist
            for (std::size_t i = 0; i < auxNames_.size(); ++i)
                if (auxMap.find(auxNames_[i]) == auxMap.end())
                    auxMap[auxNames_[i]] = makeAuxCol(auxTypes_[i]);

            while (cursor_ < totalEntries_ && idxValue() == target) {
                pvec.emplace_back(detail::makeLorentz(coords_,
                    kinBuf_[0].value(), kinBuf_[1].value(),
                    kinBuf_[2].value(), kinBuf_[3].value()));
                appendAux(auxMap);
                ++cursor_;
                if (cursor_ < totalEntries_) tree_->GetEntry(cursor_);
            }
        }

        // Collect distinct event keys in [lo, hi] without consuming the stream cursor
        void collectKeys(Long64_t lo, Long64_t hi, std::set<Long64_t>& out) {
            const Long64_t saved = cursor_;
            for (Long64_t i = 0; i < totalEntries_; ++i) {
                tree_->GetEntry(i);
                const Long64_t v = idxValue();
                if (v >= lo && v <= hi) out.insert(v);
            }
            cursor_ = saved;
            if (cursor_ < totalEntries_) tree_->GetEntry(cursor_);
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
                case BranchType::Other:
                    throw std::runtime_error("[Explore] BranchType::Other not supported in v1 for '" + bspec.name + "'");
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
                    default: break;
                }
            }
        }

        std::string              label_;
        std::string              filepath_;
        CoordSpec                coords_;
        TTree*                   tree_         = nullptr;
        Long64_t                 cursor_       = 0;
        Long64_t                 totalEntries_ = 0;
        Long64_t                 minKey_;
        Long64_t                 maxKey_;
        bool                     idxIsLong_   = false;
        Int_t                    idxI_         = 0;
        Long64_t                 idxL_         = 0;
        detail::KinBuf           kinBuf_[4];
        std::vector<std::string> auxNames_;
        std::vector<BranchType>  auxTypes_;
        std::vector<AuxBuf>      auxBufs_;
    };

    // ──────────────────────────────────────────────────────────────────────────
    // VecReader — one TTree, one row per event, array branches (RVec-style)
    //             Uses TTreeReaderArray<float> for all kinematic + aux branches.
    //             v1: only Float kinematic branches supported in VecReader mode.
    // ──────────────────────────────────────────────────────────────────────────
    class VecReader {
      public:
        VecReader(TFile* file, const CollectionSpec& spec,
                  const std::string& filepath,
                  Long64_t minEntry = 0,
                  Long64_t maxEntry = std::numeric_limits<Long64_t>::max())
            : label_(spec.label), filepath_(filepath), coords_(spec.coords)
        {
            TTree* tree = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
            if (!tree)
                throw std::runtime_error("[Explore] Missing tree '" + spec.tree + "' in file '" + filepath + "'");

            reader_.SetTree(tree);
            totalEntries_ = tree->GetEntries();

            if (minEntry > 0 || maxEntry < totalEntries_ - 1) {
                const Long64_t lo = std::max<Long64_t>(0, minEntry);
                const Long64_t hi = std::min<Long64_t>(totalEntries_ - 1, maxEntry);
                reader_.SetEntriesRange(lo, hi + 1);   // ROOT: [begin, end)
                totalEntries_ = hi - lo + 1;
            }

            tree->SetBranchStatus("*", 0);
            const auto knames = detail::coordNames(spec.coords);
            for (int i = 0; i < 4; ++i) {
                detail::requireBranch(tree, knames[i], filepath);
                tree->SetBranchStatus(knames[i].c_str(), 1);
                kinArrays_[i] = std::make_unique<TTreeReaderArray<float>>(reader_, knames[i].c_str());
            }
            for (const auto& bspec : spec.auxBranches) {
                detail::requireBranch(tree, bspec.name, filepath);
                tree->SetBranchStatus(bspec.name.c_str(), 1);
                auxNames_.push_back(bspec.name);
                auxArrays_.push_back(std::make_unique<TTreeReaderArray<float>>(reader_, bspec.name.c_str()));
            }
        }

        VecReader(const VecReader&)            = delete;
        VecReader& operator=(const VecReader&) = delete;

        bool next() { return reader_.Next(); }
        Long64_t totalEntries() const { return totalEntries_; }

        void fill(Event& ev) {
            const std::size_t nParts = kinArrays_[0]->GetSize();
            for (std::size_t ai = 0; ai < auxArrays_.size(); ++ai) {
                if (auxArrays_[ai]->GetSize() != nParts)
                    throw std::runtime_error(
                        "[Explore] VecReader '" + label_ + "': array length mismatch, branch '" +
                        auxNames_[ai] + "' has " + std::to_string(auxArrays_[ai]->GetSize()) +
                        " elements, kinematics have " + std::to_string(nParts) +
                        " at entry " + std::to_string(reader_.GetCurrentEntry()));
            }

            auto& pvec = ev.particles[label_];
            pvec.clear();
            pvec.reserve(nParts);
            for (std::size_t i = 0; i < nParts; ++i)
                pvec.emplace_back(detail::makeLorentz(coords_,
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

      private:
        std::string  label_;
        std::string  filepath_;
        CoordSpec    coords_;
        TTreeReader  reader_;
        Long64_t     totalEntries_ = 0;
        std::unique_ptr<TTreeReaderArray<float>> kinArrays_[4];
        std::vector<std::string>                            auxNames_;
        std::vector<std::unique_ptr<TTreeReaderArray<float>>> auxArrays_;
    };

    // ──────────────────────────────────────────────────────────────────────────
    // EventStream — schema-agnostic streaming iterator over a ROOT file
    // ──────────────────────────────────────────────────────────────────────────
    class EventStream {
      public:
        EventStream(const std::string& filepath,
                    const std::vector<CollectionSpec>& collections,
                    const std::vector<ScalarSpec>&     scalars = {},
                    Long64_t minBound = std::numeric_limits<Long64_t>::min(),
                    Long64_t maxBound = std::numeric_limits<Long64_t>::max())
            : filepath_(filepath), minBound_(minBound), maxBound_(maxBound)
        {
            if (collections.empty())
                throw std::runtime_error("[Explore] EventStream: no collections specified");

            bool anyFlat = false, anyVec = false;
            for (const auto& cs : collections) {
                if (cs.indexBranches.empty()) anyVec  = true;
                else                          anyFlat = true;
            }
            if (anyFlat && anyVec)
                throw std::runtime_error(
                    "[Explore] EventStream: cannot mix Flat (indexBranches non-empty) "
                    "and Vec (indexBranches empty) collections in one EventStream");

            isVec_ = anyVec;

            file_ = TFile::Open(filepath.c_str(), "READ");
            if (!file_ || file_->IsZombie())
                throw std::runtime_error("[Explore] Failed to open file '" + filepath + "'");

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
                nEvents_ = computeFlatCount();
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
            // Two-pointer merge: pick min current key across all non-exhausted readers
            bool any = false;
            EventKey minKey;
            for (auto& r : flatReaders_) {
                if (r->exhausted() || r->beyondMax()) continue;
                const EventKey k = r->currentKey();
                if (!any || k < minKey) { minKey = k; any = true; }
            }
            if (!any) return false;
            if (minKey.components[0] > maxBound_) return false;

            current_.index = minKey.components[0];
            // Every declared label gets an entry (possibly empty) for this event,
            // so downstream code can index Event by label even when a reader has
            // no rows at this key (or is already exhausted).
            for (auto& r : flatReaders_) r->ensureLabel(current_);
            for (auto& r : flatReaders_)
                if (!r->exhausted()) r->drain(minKey, current_);

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

        std::size_t computeFlatCount() {
            std::set<Long64_t> keys;
            for (auto& r : flatReaders_)
                r->collectKeys(minBound_, maxBound_, keys);
            return keys.size();
        }

        std::string   filepath_;
        TFile*        file_     = nullptr;
        bool          isVec_   = false;
        Long64_t      minBound_;
        Long64_t      maxBound_;
        Event         current_;
        std::size_t   index_   = 0;
        std::size_t   nEvents_ = 0;

        std::vector<std::unique_ptr<FlatReader>> flatReaders_;
        std::vector<std::unique_ptr<VecReader>>  vecReaders_;
    };

    // ──────────────────────────────────────────────────────────────────────────
    // runParallel — multi-threaded event loop
    // ──────────────────────────────────────────────────────────────────────────
    template<typename Callback>
    inline void runParallel(const std::string& filepath,
                             const std::vector<CollectionSpec>& collections,
                             const std::vector<ScalarSpec>&     scalars,
                             Callback&& callback,
                             std::size_t nThreads = 0)
    {
        detail::enableRootThreadSafety();

        bool anyFlat = false, anyVec = false;
        for (const auto& cs : collections) {
            if (cs.indexBranches.empty()) anyVec = true; else anyFlat = true;
        }
        if (anyFlat && anyVec)
            throw std::runtime_error("[Explore] runParallel: cannot mix Flat and Vec collections");

        if (anyVec) {
            // VecReader parallel: partition by entry range
            const std::size_t threads = nThreads > 0 ? nThreads : Config::resolveThreadCount(0);

            // Total entries from first collection's tree
            TFile* sf = TFile::Open(filepath.c_str(), "READ");
            if (!sf || sf->IsZombie())
                throw std::runtime_error("[Explore] Failed to open file '" + filepath + "'");
            TTree* t0 = dynamic_cast<TTree*>(sf->Get(collections[0].tree.c_str()));
            const Long64_t total = t0 ? t0->GetEntries() : 0;
            sf->Close(); delete sf;

            if (total == 0) return;

            // Build entry-range partitions
            const Long64_t chunk = (total + static_cast<Long64_t>(threads) - 1) / static_cast<Long64_t>(threads);
            std::vector<detail::Partition> parts;
            for (Long64_t start = 0; start < total; start += chunk)
                parts.push_back({start, std::min(total - 1, start + chunk - 1)});

            std::vector<std::thread>       workers;
            std::vector<std::exception_ptr> errors(parts.size());
            workers.reserve(parts.size());
            for (std::size_t t = 0; t < parts.size(); ++t) {
                workers.emplace_back([&, t]{
                    try {
                        EventStream stream(filepath, collections, scalars,
                                           parts[t].firstEvent, parts[t].lastEvent);
                        while (stream.next()) callback(stream.event(), static_cast<int>(t));
                    } catch (...) { errors[t] = std::current_exception(); }
                });
            }
            for (auto& w : workers) w.join();
            for (auto& e : errors)  if (e) std::rethrow_exception(e);
            return;
        }

        // FlatReader parallel: partition by event-key
        const std::size_t threads = nThreads > 0 ? nThreads : Config::resolveThreadCount(0);

        TFile* sf = TFile::Open(filepath.c_str(), "READ");
        if (!sf || sf->IsZombie())
            throw std::runtime_error("[Explore] Failed to open file '" + filepath + "'");

        std::set<Long64_t> keySet;
        for (const auto& cs : collections)
            if (!cs.indexBranches.empty())
                detail::scanIndexBranch(sf, cs.tree, cs.indexBranches[0], keySet, filepath);
        sf->Close(); delete sf;

        const std::vector<Long64_t> keys(keySet.begin(), keySet.end());
        if (keys.empty()) return;
        const auto parts = detail::partitionEvents(keys, threads);

        std::vector<std::thread>       workers;
        std::vector<std::exception_ptr> errors(parts.size());
        workers.reserve(parts.size());
        for (std::size_t t = 0; t < parts.size(); ++t) {
            workers.emplace_back([&, t]{
                try {
                    EventStream stream(filepath, collections, scalars,
                                       parts[t].firstEvent, parts[t].lastEvent);
                    while (stream.next()) callback(stream.event(), static_cast<int>(t));
                } catch (...) { errors[t] = std::current_exception(); }
            });
        }
        for (auto& w : workers) w.join();
        for (auto& e : errors)  if (e) std::rethrow_exception(e);
    }

    // Convenience overload — no scalars (most callers don't use scalars)
    template<typename Callback>
    inline void runParallel(const std::string& filepath,
                             const std::vector<CollectionSpec>& collections,
                             Callback&& callback,
                             std::size_t nThreads = 0)
    {
        runParallel(filepath, collections, {}, std::forward<Callback>(callback), nThreads);
    }

    // [MEMORY WARNING] Loads all events into RAM — unsafe for large files
    inline std::vector<Event> readAllParallel(const std::string& filepath,
                                               const std::vector<CollectionSpec>& collections,
                                               const std::vector<ScalarSpec>&     scalars = {},
                                               std::size_t nThreads = 0)
    {
        detail::enableRootThreadSafety();
        std::vector<Event> out;
        std::mutex mtx;
        runParallel(filepath, collections, scalars,
            [&](const Event& ev, int) {
                std::lock_guard<std::mutex> lk(mtx);
                out.push_back(ev);  // copy — Event& valid only within callback
            }, nThreads);
        return out;
    }

} // namespace Explore
