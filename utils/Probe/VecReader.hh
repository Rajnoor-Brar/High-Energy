#pragma once

#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "Probe/Schema.hh"
#include "TTreeReader.h"
#include "TTreeReaderArray.h"

namespace Probe {

    // One TTree row per event; array branches (RVec-style).
    // v1: only Float kinematic branches supported.
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
                        "[Probe] VecReader '" + label_ + "': array length mismatch, branch '" +
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

} // namespace Probe
