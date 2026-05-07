#pragma once

#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <algorithm>
#include <type_traits>
#include <vector>

#include "Probe/Types.hh"
#include "Physics.hh"
#include "TBranch.h"
#include "TFile.h"
#include "TTree.h"
#include "TTreeIndex.h"
#include "TROOT.h"
#include "Math/Vector4D.h"

namespace Probe {

    // ── Branch-control utilities ─────────────────────────────────────────────
    namespace BranchControl {

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

        inline BranchType detectType(char c) {
            switch (c) {
                case 'F': return BranchType::Float;
                case 'D': return BranchType::Double;
                case 'I': return BranchType::Int32;
                case 'i': return BranchType::UInt32;
                case 'L': return BranchType::Int64;
                case 'l': return BranchType::UInt64;
                case 'O': return BranchType::Bool;
                default:  return BranchType::Other;
            }
        }

        inline BranchType detectType(const std::string& s) {
            return s.empty() ? BranchType::Other : detectType(s[0]);
        }

        inline BranchType detectType(TBranch* br) {
            const std::string title = br->GetTitle();
            if (title.size() >= 2 && title[title.size() - 2] == '/') {
                return detectType(title.back());
            }
            return BranchType::Other;
        }

        inline TBranch* requireBranch(TTree* tree, const std::string& name, const std::string& file) {
            TBranch* br = tree->GetBranch(name.c_str());
            if (br == nullptr)
                throw std::runtime_error(
                    "[Probe] Missing branch '" + name +
                    "' in tree '"   + tree->GetName() +
                    "' of file '"   + file + "'");
            return br;
        }

        inline void requireType(TBranch* br, BranchType expected, const std::string& file) {
            const BranchType actual = detectType(br);
            if (actual != expected)
                throw std::runtime_error(
                    "[Probe] Type mismatch: branch '" + std::string(br->GetName()) +
                    "' in tree '"   + std::string(br->GetTree()->GetName()) +
                    "' of file '"   + file +
                    "': declared "  + branchTypeStr(expected) +
                    ", actual "     + branchTypeStr(actual));
        }

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
                        "[Probe] Kinematic branch '" + name +
                        "' in tree '" + std::string(tree->GetName()) +
                        "' of file '" + file +
                        "': must be Float_t or Double_t, got " + branchTypeStr(t));
                isFloat = (t == BranchType::Float);
                tree->SetBranchStatus(name.c_str(), 1);
                if (isFloat) tree->SetBranchAddress(name.c_str(), &f);
                else         tree->SetBranchAddress(name.c_str(), &d);
            }
        };

        inline std::vector<std::string> coordNames(const CoordSpec& cs) {
            return std::visit([](const auto& s) -> std::vector<std::string> {
                return { s.branches[0].name, s.branches[1].name, s.branches[2].name, s.branches[3].name };
            }, cs);
        }

        inline Lorentz makeLorentz(const CoordSpec& cs, double a, double b, double c, double d) {
            return std::visit([&](const auto& s) -> Lorentz {
                using T = std::decay_t<decltype(s)>;
                (void)s;
                if constexpr (std::is_same_v<T, CartesianSpec>) {
                    return Lorentz(a, b, c, d);
                } else if constexpr (std::is_same_v<T, PtEtaPhiESpec>) {
                    ROOT::Math::PtEtaPhiEVector v(a, b, c, d);
                    return Lorentz(v.Px(), v.Py(), v.Pz(), v.E());
                } else {
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

        inline Long64_t probeFirstKey(const std::string& filepath,
                                       const std::vector<CollectionSpec>& collections) {
            std::unique_ptr<TFile> f(TFile::Open(filepath.c_str(), "READ"));
            if (!f || f->IsZombie()) return 0;
            for (const auto& cs : collections) {
                if (cs.indexBranches.empty()) continue;
                TTree* t = dynamic_cast<TTree*>(f->Get(cs.tree.c_str()));
                if (!t || t->GetEntries() == 0) continue;
                const std::string& name = cs.indexBranches[0].name;
                TBranch* br = t->GetBranch(name.c_str());
                if (!br) continue;
                t->SetBranchStatus("*", 0);
                t->SetBranchStatus(name.c_str(), 1);
                const BranchType bt = detectType(br);
                Long64_t v64 = 0; Int_t v32 = 0;
                if (bt == BranchType::Int64) t->SetBranchAddress(name.c_str(), &v64);
                else                         t->SetBranchAddress(name.c_str(), &v32);
                t->GetEntry(0);
                t->ResetBranchAddresses();
                return (bt == BranchType::Int64) ? v64 : static_cast<Long64_t>(v32);
            }
            return 0;
        }

        inline void scanIndexBranch(TFile* file,
                                     const std::string& treeName,
                                     const std::string& idxName,
                                     std::set<Long64_t>& out,
                                     const std::string& filepath)
        {
            TTree* tree = dynamic_cast<TTree*>(file->Get(treeName.c_str()));
            if (!tree)
                throw std::runtime_error("[Probe] Missing tree '" + treeName + "' in file '" + filepath + "'");

            TBranch* br = requireBranch(tree, idxName, filepath);
            const BranchType t = detectType(br);
            if (t != BranchType::Int32 && t != BranchType::Int64 && t != BranchType::UInt32)
                throw std::runtime_error(
                    "[Probe] Index branch '" + idxName + "' in tree '" + treeName +
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

    } // namespace BranchControl

} // namespace Probe
