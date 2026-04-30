#pragma once

#include <array>
#include <cstddef>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

#include "Config.hh"
#include "Physics.hh"
#include "Record/Types.hh"
#include "Record/Extract.hh"
#include "TDirectory.h"
#include "TH1.h"
#include "TH1D.h"
#include "TH2.h"
#include "TGraph.h"
#include "TProfile.h"
#include "TTree.h"

namespace Record {

    using Physics::Lorentz;

    template <std::size_t N>
    inline TreeRecord declareTree(
        TDirectory* dir,
        const std::string& name,
        const std::string& title,
        const std::array<Physics::ParticleProperty, N>& properties
    ) {
        if (dir == nullptr)
            throw std::invalid_argument("Tree directory must not be null");

        TreeRecord record{};
        record.properties.assign(properties.begin(), properties.end());
        record.branchValues = std::make_unique<std::vector<Double_t>>(record.properties.size(), 0.0);

        dir->cd();
        record.tree = new TTree(name.c_str(), title.c_str());

        for (std::size_t i = 0; i < record.properties.size(); ++i) {
            const std::string branchName = Physics::particlePropertyName(record.properties[i]);
            const std::string branchType = branchName + "/D";
            record.tree->Branch(branchName.c_str(), record.branchValues->data() + i, branchType.c_str());
        }

        return record;
    }

    template <typename Basis>
    inline void count(RootObjects<Basis>& object) {
        if (object.count != nullptr) object.count->Fill(object.candidateCount);
    }

    template <typename Basis>
    inline void countAll(RootArray<Basis>& objects) {
        for (auto& object : objects) count(object);
    }

    template <typename Basis>
    inline void resetCount(RootObjects<Basis>& object) { object.candidateCount = 0; }

    template <typename Basis>
    inline void resetAllCounts(RootArray<Basis>& objects) {
        for (auto& object : objects) resetCount(object);
    }

    inline void fill(TH1Record& record, const Lorentz& particle) {
        if (record.hist != nullptr)
            record.hist->Fill(Physics::valueOf(particle, record.property));
    }

    inline void fill(EventTH1Record& record, const std::vector<Lorentz>& particles) {
        if (record.hist != nullptr)
            record.hist->Fill(Physics::valueOf(particles, record.property));
    }

    inline void fill(TreeRecord& record, const Lorentz& particle) {
        if (record.tree == nullptr || record.branchValues == nullptr) return;
        for (std::size_t i = 0; i < record.properties.size(); ++i)
            (*record.branchValues)[i] = Physics::valueOf(particle, record.properties[i]);
        record.tree->Fill();
    }

    inline void fill(ExtractHist1D& record, const Record::Extract::Event& ev) {
        if (record.hist == nullptr || !record.extractor) return;
        const Record::Extract::Scalars values = record.extractor(ev);
        for (Double_t v : values) record.hist->Fill(v);
    }

    inline void fill(ExtractHist2D& record, const Record::Extract::Event& ev) {
        if (record.hist == nullptr || !record.extractorX || !record.extractorY) return;
        const Record::Extract::Scalars xs = record.extractorX(ev);
        const Record::Extract::Scalars ys = record.extractorY(ev);
        if (xs.empty() || ys.empty()) return;
        if (xs.size() == ys.size()) {
            for (std::size_t i = 0; i < xs.size(); ++i) record.hist->Fill(xs[i], ys[i]);
        } else {
            for (Double_t x : xs)
                for (Double_t y : ys)
                    record.hist->Fill(x, y);
        }
    }

    inline void scaleAndWrite(TObject* object, Double_t histScale, std::size_t nEvents, bool width = true) {
        if (object == nullptr) return;
        if (object->InheritsFrom(TH1::Class())) {
            TH1* hist = static_cast<TH1*>(object);
            std::unique_ptr<TH1> snapshot(static_cast<TH1*>(hist->Clone(hist->GetName())));
            if (!snapshot) return;
            if (nEvents > 0) {
                const Double_t scale = histScale / static_cast<Double_t>(nEvents);
                if (width && !object->InheritsFrom(TH2::Class())) snapshot->Scale(scale, "width");
                else snapshot->Scale(scale);
            }
            snapshot->Write("", TObject::kOverwrite);
            return;
        }
        object->Write("", TObject::kOverwrite);
    }

    inline void scaleAndWriteToDir(TDirectory* dir, TObject* object, Double_t histScale, std::size_t nEvents, bool width = true) {
        if (dir == nullptr || object == nullptr) return;
        dir->cd();
        scaleAndWrite(object, histScale, nEvents, width);
    }

    template <typename Basis>
    inline void write(RootObjects<Basis>& object, Double_t histScale, std::size_t nEvents, bool checkpoint = false) {
        if (object.dir == nullptr) return;
        object.dir->cd();
        scaleAndWrite(object.count, histScale, nEvents, false);
        for (auto& hist : object.hists1D)        scaleAndWrite(hist.hist,  histScale, nEvents, true);
        for (auto& hist : object.eventHists1D)   scaleAndWrite(hist.hist,  histScale, nEvents, false);
        for (TH2* hist : object.hists2D)         scaleAndWrite(hist,       histScale, nEvents, false);
        for (auto& hist : object.extractHists1D) scaleAndWrite(hist.hist,  histScale, nEvents, false);
        for (auto& hist : object.extractHists2D) scaleAndWrite(hist.hist,  histScale, nEvents, false);
        for (TGraph* graph : object.graphs)      scaleAndWrite(graph,      histScale, nEvents, false);
        for (TProfile* p : object.profiles)      scaleAndWrite(p,          histScale, nEvents, false);
        if (!checkpoint) {
            for (auto& tree : object.trees) scaleAndWrite(tree.tree, histScale, nEvents, false);
        }
    }

    template <typename Basis>
    inline void writeToDir(RootObjects<Basis>& object, TDirectory* dir, Double_t histScale, std::size_t nEvents, bool checkpoint = false) {
        if (dir == nullptr) return;
        scaleAndWriteToDir(dir, object.count, histScale, nEvents, false);
        for (auto& hist : object.hists1D)        scaleAndWriteToDir(dir, hist.hist,  histScale, nEvents, true);
        for (auto& hist : object.eventHists1D)   scaleAndWriteToDir(dir, hist.hist,  histScale, nEvents, false);
        for (TH2* hist : object.hists2D)         scaleAndWriteToDir(dir, hist,       histScale, nEvents, false);
        for (auto& hist : object.extractHists1D) scaleAndWriteToDir(dir, hist.hist,  histScale, nEvents, false);
        for (auto& hist : object.extractHists2D) scaleAndWriteToDir(dir, hist.hist,  histScale, nEvents, false);
        for (TGraph* graph : object.graphs)      scaleAndWriteToDir(dir, graph,      histScale, nEvents, false);
        for (TProfile* p : object.profiles)      scaleAndWriteToDir(dir, p,          histScale, nEvents, false);
        if (!checkpoint) {
            for (auto& tree : object.trees) scaleAndWriteToDir(dir, tree.tree, histScale, nEvents, false);
        }
    }

    template <typename Basis>
    inline void writeAll(RootArray<Basis>& objects, Double_t histScale, std::size_t nEvents) {
        for (auto& object : objects) write(object, histScale, nEvents);
    }
}
