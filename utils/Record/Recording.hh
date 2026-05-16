#pragma once

#include "Record/Writer.hh"
#include "TDirectory.h"
#include "TH1.h"
#include "TH2.h"

namespace Record {

inline void scaleAndWrite(TObject* object,
                          Double_t histScale,
                          std::size_t nEvents,
                          bool width = true) {
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

inline void scaleAndWriteToDir(TDirectory* dir,
                               TObject* object,
                               Double_t histScale,
                               std::size_t nEvents,
                               bool width = true) {
        if (dir == nullptr || object == nullptr) return;
        dir->cd();
        scaleAndWrite(object, histScale, nEvents, width);
    }

template <typename Basis>
inline void Writer::fillParticleEvent(
        std::vector<std::pair<Basis, std::vector<Physics::Lorentz>>> fills) {
        requireEnumBasis<Basis>();
        for (auto& [basis, particles] : fills) {
            ParticleRequest req;
            req.basis     = keyOf(basis);
            req.particles = std::move(particles);
            pushFill(std::move(req));
        }
    }

template <typename Basis>
inline void Writer::fillHist1D(Basis basis, Value value) {
        requireEnumBasis<Basis>();
        pushFill(Hist1DRequest{keyOf(basis), std::move(value)});
    }

template <typename Basis>
inline void Writer::fillHist2D(Basis basis, Value x, Value y) {
        requireEnumBasis<Basis>();
        pushFill(Hist2DRequest{keyOf(basis), std::move(x), std::move(y)});
    }

template <typename Basis>
inline void Writer::fillGraph(Basis basis, Value x, Value y) {
        requireEnumBasis<Basis>();
        pushFill(GraphRequest{keyOf(basis), std::move(x), std::move(y)});
    }

template <typename Basis>
inline void Writer::fillProfile(Basis basis, Value x, Value y) {
        requireEnumBasis<Basis>();
        pushFill(ProfileRequest{keyOf(basis), std::move(x), std::move(y)});
    }

template <typename TreeBasis, typename BranchBasis>
inline void Writer::fillTree(TreeBasis tree,
                  std::initializer_list<std::pair<BranchBasis, Value>> values) {
        requireEnumBasis<TreeBasis>();
        requireEnumBasis<BranchBasis>();
        TreeRowRequest request;
        request.tree = keyOf(tree);
        request.values.reserve(values.size());
        for (const auto& [branch, value] : values)
            request.values.push_back({keyOf(branch), value});
        pushFill(std::move(request));
    }

// ── apply* methods — WriterMT.md Phase 2 ─────────────────────────────
    // Each apply* takes a workerIdx and writes into the worker's local
    // clone of the relevant ROOT object.  No cross-worker synchronisation
    // for histograms (per-worker clones are independent memory).  Trees
    // are mutex-guarded shared state in v1.
inline         void Writer::applyParticleRequest(const ParticleRequest& request, int workerIdx) {
        auto it = particleObjects_.find(request.basis);
        if (it == particleObjects_.end())
            throw std::runtime_error("[Record::Writer] missing particle group " + keyString(request.basis));

        ParticleObjects& object = it->second;
        std::int32_t candidateCount = 0;
        for (const Physics::Lorentz& particle : request.particles) {
            ++candidateCount;
            for (auto& hist : object.hists1D)
                hist.clones[workerIdx]->Fill(Physics::valueOf(particle, hist.property));
            for (auto& hist : object.hists2D)
                hist.clones[workerIdx]->Fill(Physics::valueOf(particle, hist.propertyX),
                                              Physics::valueOf(particle, hist.propertyY));
            for (auto& graph : object.graphs)
                graph.clones[workerIdx]->SetPoint(graph.nextPoint[workerIdx]++,
                                                   Physics::valueOf(particle, graph.propertyX),
                                                   Physics::valueOf(particle, graph.propertyY));
            for (auto& profile : object.profiles)
                profile.clones[workerIdx]->Fill(Physics::valueOf(particle, profile.propertyX),
                                                 Physics::valueOf(particle, profile.propertyY));
            if (object.tree.tree != nullptr) {
                std::lock_guard<std::mutex> lock(*object.tree.mutex);
                fillParticleTreeLocked(object.tree, particle);
            }
        }
        if (object.count.hist != nullptr)
            object.count.clones[workerIdx]->Fill(candidateCount);
    }

inline void Writer::fillParticleTreeLocked(ParticleTree& tree, const Physics::Lorentz& particle) {
        if (tree.tree == nullptr) return;
        if (tree.properties.size() != tree.branches.size())
            throw std::runtime_error("[Record::Writer] particle tree branch/property size mismatch");
        for (std::size_t i = 0; i < tree.properties.size(); ++i)
            setBranchBuffer(tree.branches[i], Value{Physics::valueOf(particle, tree.properties[i])});
        tree.tree->Fill();
    }

inline void Writer::applyHist1DRequest(const Hist1DRequest& request, int workerIdx) {
        auto it = hists1D_.find(request.basis);
        if (it == hists1D_.end())
            throw std::runtime_error("[Record::Writer] missing hist1D " + keyString(request.basis));
        it->second.clones[workerIdx]->Fill(RootUtil::toDouble(request.value));
    }

inline void Writer::applyHist2DRequest(const Hist2DRequest& request, int workerIdx) {
        auto it = hists2D_.find(request.basis);
        if (it == hists2D_.end())
            throw std::runtime_error("[Record::Writer] missing hist2D " + keyString(request.basis));
        it->second.clones[workerIdx]->Fill(RootUtil::toDouble(request.x), RootUtil::toDouble(request.y));
    }

inline void Writer::applyGraphRequest(const GraphRequest& request, int workerIdx) {
        auto it = graphs_.find(request.basis);
        if (it == graphs_.end())
            throw std::runtime_error("[Record::Writer] missing graph " + keyString(request.basis));
        GraphRecord& record = it->second;
        record.clones[workerIdx]->SetPoint(record.nextPoint[workerIdx]++,
                                            RootUtil::toDouble(request.x),
                                            RootUtil::toDouble(request.y));
    }

inline void Writer::applyProfileRequest(const ProfileRequest& request, int workerIdx) {
        auto it = profiles_.find(request.basis);
        if (it == profiles_.end())
            throw std::runtime_error("[Record::Writer] missing profile " + keyString(request.basis));
        it->second.clones[workerIdx]->Fill(RootUtil::toDouble(request.x), RootUtil::toDouble(request.y));
    }

inline void Writer::applyTreeRowRequest(const TreeRowRequest& request, int /*workerIdx*/) {
        auto treeIt = trees_.find(request.tree);
        if (treeIt == trees_.end())
            throw std::runtime_error("[Record::Writer] missing tree " + keyString(request.tree));

        ExplicitTreeRecord& tree = treeIt->second;
        if (request.values.size() != tree.branchOrder.size())
            throw std::runtime_error("[Record::Writer] tree row for " + keyString(request.tree) +
                                     " does not supply exactly all branches");

        // Single mutex covers both buffer writes and TTree::Fill().
        std::lock_guard<std::mutex> lock(*tree.mutex);
        std::unordered_map<RecordKey, bool, RecordKeyHash> supplied;
        supplied.reserve(tree.branchOrder.size());
        for (const auto& [branchKey, value] : request.values) {
            auto branchIt = tree.branches.find(branchKey);
            if (branchIt == tree.branches.end())
                throw std::runtime_error("[Record::Writer] missing tree branch " + keyString(branchKey));
            if (supplied[branchKey])
                throw std::runtime_error("[Record::Writer] duplicate tree branch value " + keyString(branchKey));
            supplied[branchKey] = true;
            setBranchBuffer(branchIt->second, value);
        }
        for (const RecordKey& branchKey : tree.branchOrder) {
            if (!supplied[branchKey])
                throw std::runtime_error("[Record::Writer] missing tree branch value " + keyString(branchKey));
        }
        tree.tree->Fill();
    }

inline void Writer::writeCheckpointFile(std::size_t eventIndex) {
        TFile cpFile(paths_.checkpointOutName.Data(), "RECREATE");
        if (!cpFile.IsOpen() || cpFile.IsZombie())
            throw std::runtime_error("[Record::Writer] failed to open checkpoint ROOT file: " +
                                     std::string(paths_.checkpointOutName.Data()));

        for (auto& [key, object] : particleObjects_) {
            (void)key;
            if (object.dir == nullptr) continue;
            TDirectory* cpDir = cpFile.mkdir(object.dir->GetName());
            writeParticleObjectsToDir(object, cpDir, eventIndex, true);
        }
        cpFile.cd();
        writeIndependentObjectsToDir(&cpFile, eventIndex, true);
        cpFile.Write("", TObject::kOverwrite);
        cpFile.Close();
    }

inline void Writer::writeAllToCurrentFile(std::size_t eventCount, bool checkpoint) {
        if (outFile_ == nullptr) return;
        for (auto& [key, object] : particleObjects_) {
            (void)key;
            writeParticleObjects(object, eventCount, checkpoint);
        }
        writeIndependentObjects(eventCount, checkpoint);
        if (!checkpoint) {
            Meta::writeAbout(outFile_, meta_);
            if (preCloseHook_) preCloseHook_();
            outFile_->Write("", TObject::kOverwrite);
            outFile_->Close();
            delete outFile_;
            outFile_ = nullptr;
            clearRecords();
        }
    }

inline void Writer::writeParticleObjects(ParticleObjects& object,
                              std::size_t eventCount,
                              bool checkpoint) {
        writeParticleObjectsToDir(object, object.dir, eventCount, checkpoint);
    }

inline void Writer::writeParticleObjectsToDir(ParticleObjects& object,
                                   TDirectory* dir,
                                   std::size_t eventCount,
                                   bool checkpoint) {
        if (dir == nullptr) return;
        scaleAndWriteToDir(dir, object.count.hist, hist_.histScale, eventCount, false);
        for (auto& hist : object.hists1D) scaleAndWriteToDir(dir, hist.hist, hist_.histScale, eventCount, true);
        for (auto& hist : object.hists2D) scaleAndWriteToDir(dir, hist.hist, hist_.histScale, eventCount, false);
        for (auto& graph : object.graphs) scaleAndWriteToDir(dir, graph.graph, hist_.histScale, eventCount, false);
        for (auto& profile : object.profiles) scaleAndWriteToDir(dir, profile.profile, hist_.histScale, eventCount, false);
        if (!checkpoint && object.tree.tree != nullptr)
            scaleAndWriteToDir(dir, object.tree.tree, hist_.histScale, eventCount, false);
    }

inline void Writer::writeIndependentObjects(std::size_t eventCount, bool checkpoint) {
        writeIndependentObjectsToDir(outFile_, eventCount, checkpoint);
    }

inline void Writer::writeIndependentObjectsToDir(TDirectory* dir,
                                      std::size_t eventCount,
                                      bool checkpoint) {
        if (dir == nullptr) return;
        for (auto& [key, record] : hists1D_) {
            (void)key;
            scaleAndWriteToDir(dir, record.hist, hist_.histScale, eventCount, true);
        }
        for (auto& [key, record] : hists2D_) {
            (void)key;
            scaleAndWriteToDir(dir, record.hist, hist_.histScale, eventCount, false);
        }
        for (auto& [key, record] : graphs_) {
            (void)key;
            scaleAndWriteToDir(dir, record.graph, hist_.histScale, eventCount, false);
        }
        for (auto& [key, record] : profiles_) {
            (void)key;
            scaleAndWriteToDir(dir, record.profile, hist_.histScale, eventCount, false);
        }
        if (!checkpoint) {
            for (auto& [key, record] : trees_) {
                (void)key;
                if (hasBranchNamed(record, "event_index"))
                    record.tree->BuildIndex("event_index");
                scaleAndWriteToDir(dir, record.tree, hist_.histScale, eventCount, false);
            }
        }
    }

inline bool Writer::hasBranchNamed(const ExplicitTreeRecord& record, const std::string& name) {
        for (const auto& [key, branch] : record.branches) {
            (void)key;
            if (branch.name == name) return true;
        }
        return false;
    }

} // namespace Record
