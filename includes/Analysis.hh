#pragma once

#include <array>
#include <cstddef>
#include <vector>

#include "TDirectory.h"
#include "TH1.h"
#include "TH1D.h"
#include "TH1I.h"

namespace Analysis {
    template <typename Enum>
    constexpr std::size_t toIndex(Enum value) {
        return static_cast<std::size_t>(value);
    }

    template <typename Basis, std::size_t HistCount>
    struct RootObjects {
        Basis basis{};
        TDirectory* dir{};
        TH1I* count{};
        Int_t validatedCount{};
        std::array<TH1D*, HistCount> hists{};
    };

    template <typename Basis, std::size_t HistCount>
    using RootArray = std::vector<RootObjects<Basis, HistCount>>;

    template <typename Basis, std::size_t HistCount>
    inline void count(RootObjects<Basis, HistCount>& object) {
        if (object.count != nullptr) {
            object.count->Fill(object.validatedCount);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void countAll(RootArray<Basis, HistCount>& objects) {
        for (auto& object : objects) {
            count(object);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void resetCount(RootObjects<Basis, HistCount>& object) {
        object.validatedCount = 0;
    }

    template <typename Basis, std::size_t HistCount>
    inline void resetAllCounts(RootArray<Basis, HistCount>& objects) {
        for (auto& object : objects) {
            resetCount(object);
        }
    }

    inline void scaleAndWrite(TH1* hist, Double_t histScale, Int_t nEvents, bool width = true) {
        if (hist == nullptr) {
            return;
        }

        if (nEvents > 0) {
            const Double_t scale = histScale / static_cast<Double_t>(nEvents);
            if (width) {
                hist->Scale(scale, "width");
            } else {
                hist->Scale(scale);
            }
        }

        hist->Write();
    }

    template <typename Basis, std::size_t HistCount>
    inline void write(RootObjects<Basis, HistCount>& object, Double_t histScale, Int_t nEvents) {
        if (object.dir == nullptr) {
            return;
        }

        object.dir->cd();
        scaleAndWrite(object.count, histScale, nEvents, false);

        for (TH1D* hist : object.hists) {
            scaleAndWrite(hist, histScale, nEvents, true);
        }
    }

    template <typename Basis, std::size_t HistCount>
    inline void writeAll(RootArray<Basis, HistCount>& objects, Double_t histScale, Int_t nEvents) {
        for (auto& object : objects) {
            write(object, histScale, nEvents);
        }
    }
}
