#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <exception>
#include <functional>
#include <initializer_list>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>

#include "TFile.h"
#include "TGraph.h"
#include "TH1D.h"
#include "TH2D.h"
#include "TProfile.h"
#include "TROOT.h"
#include "TTree.h"

#include "Config.hh"
#include "Record/Configs.hh"
#include "Record/Histogram.hh"
#include "Record/Meta.hh"
#include "Record/Requests.hh"
#include "Record/Types.hh"

namespace Monitor {
    class AsyncLogger;
    struct RunSnapshot;
}

namespace Record {

    class Writer {
      public:
        Writer() = default;
        ~Writer() { cleanup(); }

        Writer(const Writer&)            = delete;
        Writer& operator=(const Writer&) = delete;
        Writer(Writer&&)                 = delete;
        Writer& operator=(Writer&&)      = delete;

        void open(Paths paths, HistConfig hist, Meta::Record initialMeta) {
            if (started_.load(std::memory_order_acquire))
                throw std::runtime_error("[Record::Writer] open() called while scribe is running");

            closeFile();
            paths_ = std::move(paths);
            hist_  = std::move(hist);
            meta_  = std::move(initialMeta);
            clearRecords();
            clearQueues();

            outFile_ = new TFile(paths_.outName, "RECREATE");
            if (outFile_ == nullptr || outFile_->IsZombie())
                throw std::runtime_error("[Record::Writer] Failed to create ROOT output file: " +
                                         std::string(paths_.outName.Data()));
        }

        void bind(Monitor::AsyncLogger&        logger,
                  std::function<std::string()> programLog,
                  std::function<void()>         printStats   = {},
                  std::function<void()>         listChanged  = {},
                  std::function<void()>         preCloseHook = {});

        void start() {
            if (outFile_ == nullptr)
                throw std::runtime_error("[Record::Writer] start() called before open()");
            enableRootThreadSafety();
            bool expected = false;
            if (!started_.compare_exchange_strong(expected, true))
                throw std::runtime_error("[Record::Writer] start() called more than once");

            accepting_.store(true, std::memory_order_release);
            stopRequested_.store(false, std::memory_order_release);
            scribeException_ = nullptr;
            scribe_ = std::thread(&Writer::scribeLoop, this);
        }

        void checkpoint(std::size_t eventIndex) {
            auto barrier = std::make_shared<BarrierState>();
            CheckpointRequest request{eventIndex, barrier};
            pushCheckpoint(std::move(request));
            waitBarrier(barrier);
        }

        void finish(std::size_t eventCount);

        bool fatalWrite(std::size_t eventCount, std::chrono::milliseconds timeout) {
            if (!started_.load(std::memory_order_acquire))
                throw std::runtime_error("[Record::Writer] fatalWrite() called before start()");

            accepting_.store(false, std::memory_order_release);
            queueNotFull_.notify_all();

            auto barrier = std::make_shared<BarrierState>();
            pushFatal(FatalWriteRequest{eventCount, barrier});

            std::unique_lock<std::mutex> lock(barrier->mutex);
            const bool done = barrier->cv.wait_for(lock, timeout, [&] { return barrier->done; });
            if (!done) return false;
            if (barrier->exception) std::rethrow_exception(barrier->exception);
            return barrier->completed;
        }

        void setQueueCapacity(std::size_t capacity) {
            if (capacity == 0)
                throw std::runtime_error("[Record::Writer] queue capacity must be positive");
            std::lock_guard<std::mutex> lock(queueMutex_);
            queueCapacity_ = capacity;
            queueNotFull_.notify_all();
        }

        std::size_t queueCapacity() const {
            std::lock_guard<std::mutex> lock(queueMutex_);
            return queueCapacity_;
        }

        // WriterMT.md Phase 0 stub.  Stores the [record].thread_count value
        // for use by Phase 2's worker pool.  No-op until Phase 2 lands; the
        // value is currently consulted only by stats() output.
        void setRecordThreadCount(std::size_t n) {
            if (started_.load(std::memory_order_acquire))
                throw std::runtime_error(
                    "[Record::Writer] setRecordThreadCount() called after start()");
            recordThreadCount_ = n;
        }

        std::size_t recordThreadCount() const { return recordThreadCount_; }

        std::string stats() const {
            std::lock_guard<std::mutex> lock(queueMutex_);
            std::ostringstream out;
            out << "Record::Writer{"
                << "started=" << started_.load(std::memory_order_relaxed)
                << ", accepting=" << accepting_.load(std::memory_order_relaxed)
                << ", queueCapacity=" << queueCapacity_
                << ", backlog=" << grandQueue_.size()
                << ", produced=" << produced_
                << ", consumed=" << consumed_
                << ", maxBacklog=" << maxBacklog_
                << "}";
            return out.str();
        }

        template <typename Basis>
        void declareParticleGroup(Basis basis,
                                  std::string directoryName,
                                  std::string displayName) {
            requireEnumBasis<Basis>();
            requireOpenForDeclaration("particle group");
            requireNotStarted("particle group");
            if (directoryName.empty())
                throw std::runtime_error("[Record::Writer] particle group directory name must not be empty");

            const RecordKey key = keyOf(basis);
            if (particleObjects_.count(key))
                throw std::runtime_error("[Record::Writer] duplicate particle group " + keyString(key));

            outFile_->cd();
            TDirectory* dir = outFile_->mkdir(directoryName.c_str());
            if (dir == nullptr)
                throw std::runtime_error("[Record::Writer] failed to create directory '" + directoryName + "'");

            ParticleObjects object{};
            object.basis = key;
            object.name  = std::move(displayName);
            object.dir   = dir;
            particleObjects_.emplace(key, std::move(object));
        }

        template <typename Basis>
        void declareParticleCount(Basis basis,
                                  std::string histName,
                                  std::string title,
                                  int bins,
                                  double low,
                                  double high) {
            ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle count");
            validateHistogramShape(histName, bins, low, high);
            if (object.count != nullptr)
                throw std::runtime_error("[Record::Writer] duplicate particle count for " +
                                         keyString(keyOf(basis)));

            object.dir->cd();
            object.count = new TH1D(histName.c_str(), title.c_str(), bins, low, high);
        }

        template <typename Basis>
        void declareParticleHist1D(Basis basis,
                                   Physics::ParticleProperty property,
                                   std::string histName,
                                   std::string title,
                                   int bins,
                                   double low,
                                   double high) {
            ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle hist1D");
            validateHistogramShape(histName, bins, low, high);
            ensureUniqueParticleName(object, histName);
            object.dir->cd();
            object.hists1D.push_back(ParticleTH1{
                new TH1D(histName.c_str(), title.c_str(), bins, low, high),
                property
            });
        }

        template <typename Basis>
        void declareParticleHist2D(Basis basis,
                                   Physics::ParticleProperty propertyX,
                                   Physics::ParticleProperty propertyY,
                                   std::string histName,
                                   std::string title,
                                   int binsX,
                                   double lowX,
                                   double highX,
                                   int binsY,
                                   double lowY,
                                   double highY) {
            ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle hist2D");
            validateHistogramShape(histName, binsX, lowX, highX);
            validateHistogramShape(histName, binsY, lowY, highY);
            ensureUniqueParticleName(object, histName);
            object.dir->cd();
            object.hists2D.push_back(ParticleTH2{
                new TH2D(histName.c_str(), title.c_str(), binsX, lowX, highX, binsY, lowY, highY),
                propertyX,
                propertyY
            });
        }

        template <typename Basis>
        void declareParticleGraph(Basis basis,
                                  Physics::ParticleProperty propertyX,
                                  Physics::ParticleProperty propertyY,
                                  std::string graphName,
                                  std::string title) {
            ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle graph");
            validateObjectName(graphName, "particle graph");
            ensureUniqueParticleName(object, graphName);
            object.dir->cd();
            auto* graph = new TGraph();
            graph->SetName(graphName.c_str());
            graph->SetTitle(title.c_str());
            object.graphs.push_back(ParticleGraph{graph, propertyX, propertyY, 0});
        }

        template <typename Basis>
        void declareParticleProfile(Basis basis,
                                    Physics::ParticleProperty propertyX,
                                    Physics::ParticleProperty propertyY,
                                    std::string profileName,
                                    std::string title,
                                    int binsX,
                                    double lowX,
                                    double highX) {
            ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle profile");
            validateHistogramShape(profileName, binsX, lowX, highX);
            ensureUniqueParticleName(object, profileName);
            object.dir->cd();
            object.profiles.push_back(ParticleProfile{
                new TProfile(profileName.c_str(), title.c_str(), binsX, lowX, highX),
                propertyX,
                propertyY
            });
        }

        template <typename Basis>
        void declareParticleTree(Basis basis,
                                 std::string treeName,
                                 std::string title,
                                 std::vector<Physics::ParticleProperty> properties) {
            ParticleObjects& object = requireParticleGroupForDeclaration(basis, "particle tree");
            validateObjectName(treeName, "particle tree");
            if (object.tree.tree != nullptr)
                throw std::runtime_error("[Record::Writer] duplicate particle tree for " +
                                         keyString(keyOf(basis)));
            if (properties.empty())
                throw std::runtime_error("[Record::Writer] particle tree '" + treeName +
                                         "' must have at least one branch");

            object.dir->cd();
            object.tree.tree = new TTree(treeName.c_str(), title.c_str());
            object.tree.properties = std::move(properties);
            object.tree.branches.reserve(object.tree.properties.size());
            for (Physics::ParticleProperty property : object.tree.properties) {
                BranchRecord branch{};
                branch.name = Physics::particlePropertyName(property);
                branch.type = DataType::Double;
                branch.buffer = makeBranchBuffer(branch.type);
                declareBranch(*object.tree.tree, branch);
                object.tree.branches.push_back(std::move(branch));
            }
        }

        template <typename Basis>
        void declareHist1D(Basis basis,
                           std::string histName,
                           std::string title,
                           int bins,
                           double low,
                           double high,
                           DataType type = DataType::Double) {
            requireEnumBasis<Basis>();
            requireOpenForDeclaration("hist1D");
            requireNotStarted("hist1D");
            validateHistogramShape(histName, bins, low, high);
            requireNumeric(type, "hist1D");
            const RecordKey key = keyOf(basis);
            if (hists1D_.count(key))
                throw std::runtime_error("[Record::Writer] duplicate hist1D " + keyString(key));
            outFile_->cd();
            hists1D_.emplace(key, Hist1DRecord{new TH1D(histName.c_str(), title.c_str(), bins, low, high), type});
        }

        template <typename Basis>
        void declareHist2D(Basis basis,
                           std::string histName,
                           std::string title,
                           int binsX,
                           double lowX,
                           double highX,
                           int binsY,
                           double lowY,
                           double highY,
                           DataType typeX = DataType::Double,
                           DataType typeY = DataType::Double) {
            requireEnumBasis<Basis>();
            requireOpenForDeclaration("hist2D");
            requireNotStarted("hist2D");
            validateHistogramShape(histName, binsX, lowX, highX);
            validateHistogramShape(histName, binsY, lowY, highY);
            requireNumeric(typeX, "hist2D x");
            requireNumeric(typeY, "hist2D y");
            const RecordKey key = keyOf(basis);
            if (hists2D_.count(key))
                throw std::runtime_error("[Record::Writer] duplicate hist2D " + keyString(key));
            outFile_->cd();
            hists2D_.emplace(key, Hist2DRecord{
                new TH2D(histName.c_str(), title.c_str(), binsX, lowX, highX, binsY, lowY, highY),
                typeX,
                typeY
            });
        }

        template <typename Basis>
        void declareGraph(Basis basis,
                          std::string graphName,
                          std::string title,
                          DataType typeX = DataType::Double,
                          DataType typeY = DataType::Double) {
            requireEnumBasis<Basis>();
            requireOpenForDeclaration("graph");
            requireNotStarted("graph");
            validateObjectName(graphName, "graph");
            requireNumeric(typeX, "graph x");
            requireNumeric(typeY, "graph y");
            const RecordKey key = keyOf(basis);
            if (graphs_.count(key))
                throw std::runtime_error("[Record::Writer] duplicate graph " + keyString(key));
            outFile_->cd();
            auto* graph = new TGraph();
            graph->SetName(graphName.c_str());
            graph->SetTitle(title.c_str());
            graphs_.emplace(key, GraphRecord{graph, typeX, typeY, 0});
        }

        template <typename Basis>
        void declareProfile(Basis basis,
                            std::string profileName,
                            std::string title,
                            int binsX,
                            double lowX,
                            double highX,
                            DataType typeX = DataType::Double,
                            DataType typeY = DataType::Double) {
            requireEnumBasis<Basis>();
            requireOpenForDeclaration("profile");
            requireNotStarted("profile");
            validateHistogramShape(profileName, binsX, lowX, highX);
            requireNumeric(typeX, "profile x");
            requireNumeric(typeY, "profile y");
            const RecordKey key = keyOf(basis);
            if (profiles_.count(key))
                throw std::runtime_error("[Record::Writer] duplicate profile " + keyString(key));
            outFile_->cd();
            profiles_.emplace(key, ProfileRecord{
                new TProfile(profileName.c_str(), title.c_str(), binsX, lowX, highX),
                typeX,
                typeY
            });
        }

        template <typename TreeBasis, typename BranchBasis>
        void declareTree(TreeBasis treeBasis,
                         std::string treeName,
                         std::string title,
                         std::vector<std::tuple<BranchBasis, std::string, DataType>> branches) {
            requireEnumBasis<TreeBasis>();
            requireEnumBasis<BranchBasis>();
            requireOpenForDeclaration("tree");
            requireNotStarted("tree");
            validateObjectName(treeName, "tree");
            if (branches.empty())
                throw std::runtime_error("[Record::Writer] tree '" + treeName + "' must have at least one branch");

            const RecordKey treeKey = keyOf(treeBasis);
            if (trees_.count(treeKey))
                throw std::runtime_error("[Record::Writer] duplicate tree " + keyString(treeKey));

            outFile_->cd();
            ExplicitTreeRecord treeRecord{};
            treeRecord.tree = new TTree(treeName.c_str(), title.c_str());

            for (const auto& [branchBasis, branchName, branchType] : branches) {
                validateObjectName(branchName, "tree branch");
                if (branchType == DataType::Other)
                    throw std::runtime_error("[Record::Writer] unsupported branch type for '" + branchName + "'");

                const RecordKey branchKey = keyOf(branchBasis);
                if (treeRecord.branches.count(branchKey))
                    throw std::runtime_error("[Record::Writer] duplicate branch key " + keyString(branchKey));

                BranchRecord branch{};
                branch.name = branchName;
                branch.type = branchType;
                branch.buffer = makeBranchBuffer(branch.type);
                declareBranch(*treeRecord.tree, branch);
                treeRecord.branchOrder.push_back(branchKey);
                treeRecord.branches.emplace(branchKey, std::move(branch));
            }

            trees_.emplace(treeKey, std::move(treeRecord));
        }

        template <typename Basis>
        void fillParticleEvent(std::initializer_list<ParticleFillView<Basis>> fills) {
            requireEnumBasis<Basis>();
            ParticleRequest request;
            request.groups.reserve(fills.size());
            for (const auto& fill : fills) {
                ParticleGroupFillRequest group;
                group.basis = keyOf(fill.basis);
                group.particles = fill.particles;
                request.groups.push_back(std::move(group));
            }
            pushParticle(std::move(request));
        }

        template <typename Basis>
        void fillHist1D(Basis basis, Value value) {
            requireEnumBasis<Basis>();
            pushHist1D(Hist1DRequest{keyOf(basis), std::move(value)});
        }

        template <typename Basis>
        void fillHist2D(Basis basis, Value x, Value y) {
            requireEnumBasis<Basis>();
            pushHist2D(Hist2DRequest{keyOf(basis), std::move(x), std::move(y)});
        }

        template <typename Basis>
        void fillGraph(Basis basis, Value x, Value y) {
            requireEnumBasis<Basis>();
            pushGraph(GraphRequest{keyOf(basis), std::move(x), std::move(y)});
        }

        template <typename Basis>
        void fillProfile(Basis basis, Value x, Value y) {
            requireEnumBasis<Basis>();
            pushProfile(ProfileRequest{keyOf(basis), std::move(x), std::move(y)});
        }

        template <typename TreeBasis, typename BranchBasis>
        void fillTree(TreeBasis tree,
                      std::initializer_list<std::pair<BranchBasis, Value>> values) {
            requireEnumBasis<TreeBasis>();
            requireEnumBasis<BranchBasis>();
            TreeRowRequest request;
            request.tree = keyOf(tree);
            request.values.reserve(values.size());
            for (const auto& [branch, value] : values)
                request.values.push_back({keyOf(branch), value});
            pushTree(std::move(request));
        }

        TFile*              file()       const { return outFile_; }
        const Paths&        paths()      const { return paths_; }
        const HistConfig&   histConfig() const { return hist_; }
        Meta::Record&       meta()             { return meta_; }
        const Meta::Record& meta()       const { return meta_; }

      private:
        void fatalShutdown(const Monitor::RunSnapshot& snapshot);

        template <typename Basis>
        static void requireEnumBasis() {
            static_assert(std::is_enum_v<Basis>, "Record::Writer basis parameters must be enum types");
        }

        void requireOpenForDeclaration(const std::string& kind) const {
            if (outFile_ == nullptr)
                throw std::runtime_error("[Record::Writer] open() must be called before declaring " + kind);
        }

        void requireNotStarted(const std::string& kind) const {
            if (started_.load(std::memory_order_acquire))
                throw std::runtime_error("[Record::Writer] cannot declare " + kind + " after start()");
        }

        template <typename Basis>
        ParticleObjects& requireParticleGroupForDeclaration(Basis basis, const std::string& kind) {
            requireEnumBasis<Basis>();
            requireOpenForDeclaration(kind);
            requireNotStarted(kind);
            const RecordKey key = keyOf(basis);
            auto it = particleObjects_.find(key);
            if (it == particleObjects_.end())
                throw std::runtime_error("[Record::Writer] missing particle group for " + kind +
                                         " " + keyString(key));
            return it->second;
        }

        static void validateObjectName(const std::string& name, const std::string& kind) {
            if (name.empty())
                throw std::runtime_error("[Record::Writer] " + kind + " name must not be empty");
        }

        static void validateHistogramShape(const std::string& name, int bins, double low, double high) {
            validateObjectName(name, "histogram");
            if (bins <= 0 || !(high > low))
                throw std::runtime_error("[Record::Writer] invalid histogram shape for '" + name + "'");
        }

        static void requireNumeric(DataType type, const std::string& context) {
            if (type == DataType::String || type == DataType::Other)
                throw std::runtime_error("[Record::Writer] " + context + " requires numeric type, got " +
                                         RootUtil::typeName(type));
        }

        static void ensureUniqueParticleName(const ParticleObjects& object, const std::string& name) {
            if (object.count && name == object.count->GetName())
                throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
            for (const auto& record : object.hists1D)
                if (record.hist && name == record.hist->GetName())
                    throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
            for (const auto& record : object.hists2D)
                if (record.hist && name == record.hist->GetName())
                    throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
            for (const auto& record : object.graphs)
                if (record.graph && name == record.graph->GetName())
                    throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
            for (const auto& record : object.profiles)
                if (record.profile && name == record.profile->GetName())
                    throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
            if (object.tree.tree && name == object.tree.tree->GetName())
                throw std::runtime_error("[Record::Writer] duplicate particle object '" + name + "'");
        }

        static void waitBarrier(const std::shared_ptr<BarrierState>& barrier) {
            std::unique_lock<std::mutex> lock(barrier->mutex);
            barrier->cv.wait(lock, [&] { return barrier->done; });
            if (barrier->exception) std::rethrow_exception(barrier->exception);
        }

        static void enableRootThreadSafety() {
            // Required: see Probe::BranchControl::enableRootThreadSafety
            // for the rationale and the Phase A experiment that
            // confirmed it. The scribe is single-threaded for ROOT
            // mutation, but ROOT's internal shared state (TClass DB,
            // gROOT, allocators) still races between scribe and
            // concurrent producers if this is not enabled.
            static std::once_flag flag;
            std::call_once(flag, [] { ROOT::EnableThreadSafety(); });
        }

        static void completeBarrier(const std::shared_ptr<BarrierState>& barrier,
                                    std::exception_ptr exception = nullptr,
                                    bool completed = true) {
            if (!barrier) return;
            {
                std::lock_guard<std::mutex> lock(barrier->mutex);
                barrier->exception = std::move(exception);
                barrier->completed = completed;
                barrier->done = true;
            }
            barrier->cv.notify_all();
        }

        void throwIfCannotAcceptLocked() const {
            if (!started_.load(std::memory_order_acquire))
                throw std::runtime_error("[Record::Writer] fill/checkpoint called before start()");
            if (!accepting_.load(std::memory_order_acquire))
                throw std::runtime_error("[Record::Writer] writer is no longer accepting requests");
            if (scribeException_) std::rethrow_exception(scribeException_);
        }

        template <typename Queue, typename Payload>
        void pushNormal(Queue& queue, Payload&& payload, QueueLane lane) {
            std::unique_lock<std::mutex> lock(queueMutex_);
            throwIfCannotAcceptLocked();
            queueNotFull_.wait(lock, [&] {
                return !accepting_.load(std::memory_order_acquire)
                    || scribeException_
                    || grandQueue_.size() < queueCapacity_;
            });
            throwIfCannotAcceptLocked();
            queue.push_back(std::forward<Payload>(payload));
            grandQueue_.push_back(QueueTicket{lane});
            ++produced_;
            if (grandQueue_.size() > maxBacklog_) maxBacklog_ = grandQueue_.size();
            lock.unlock();
            queueNotEmpty_.notify_one();
        }

        void pushParticle(ParticleRequest request) { pushNormal(particleQueue_, std::move(request), QueueLane::Particle); }
        void pushHist1D(Hist1DRequest request) { pushNormal(hist1DQueue_, std::move(request), QueueLane::Hist1D); }
        void pushHist2D(Hist2DRequest request) { pushNormal(hist2DQueue_, std::move(request), QueueLane::Hist2D); }
        void pushGraph(GraphRequest request) { pushNormal(graphQueue_, std::move(request), QueueLane::Graph); }
        void pushProfile(ProfileRequest request) { pushNormal(profileQueue_, std::move(request), QueueLane::Profile); }
        void pushTree(TreeRowRequest request) { pushNormal(treeQueue_, std::move(request), QueueLane::Tree); }
        void pushCheckpoint(CheckpointRequest request) { pushNormal(checkpointQueue_, std::move(request), QueueLane::Checkpoint); }

        void pushFinish(FinishRequest request) {
            accepting_.store(false, std::memory_order_release);
            queueNotFull_.notify_all();
            std::unique_lock<std::mutex> lock(queueMutex_);
            if (!started_.load(std::memory_order_acquire))
                throw std::runtime_error("[Record::Writer] finish() called before start()");
            if (scribeException_) std::rethrow_exception(scribeException_);
            finishQueue_.push_back(std::move(request));
            grandQueue_.push_back(QueueTicket{QueueLane::Finish});
            ++produced_;
            if (grandQueue_.size() > maxBacklog_) maxBacklog_ = grandQueue_.size();
            lock.unlock();
            queueNotEmpty_.notify_one();
        }

        void pushFatal(FatalWriteRequest request) {
            std::unique_lock<std::mutex> lock(queueMutex_);
            fatalQueue_.push_back(std::move(request));
            grandQueue_.push_back(QueueTicket{QueueLane::FatalWrite});
            ++produced_;
            if (grandQueue_.size() > maxBacklog_) maxBacklog_ = grandQueue_.size();
            lock.unlock();
            queueNotEmpty_.notify_one();
        }

        void scribeLoop() {
            bool finishSeen = false;
            while (!finishSeen) {
                QueueTicket ticket{};
                ParticleRequest particle;
                Hist1DRequest hist1D;
                Hist2DRequest hist2D;
                GraphRequest graph;
                ProfileRequest profile;
                TreeRowRequest tree;
                CheckpointRequest checkpoint;
                FinishRequest finish;
                FatalWriteRequest fatal;

                {
                    std::unique_lock<std::mutex> lock(queueMutex_);
                    queueNotEmpty_.wait(lock, [&] {
                        return stopRequested_.load(std::memory_order_acquire) || !grandQueue_.empty();
                    });

                    if (grandQueue_.empty()) break;

                    ticket = grandQueue_.front();
                    grandQueue_.pop_front();
                    ++consumed_;
                    switch (ticket.lane) {
                        case QueueLane::Particle:
                            particle = std::move(particleQueue_.front());
                            particleQueue_.pop_front();
                            break;
                        case QueueLane::Hist1D:
                            hist1D = std::move(hist1DQueue_.front());
                            hist1DQueue_.pop_front();
                            break;
                        case QueueLane::Hist2D:
                            hist2D = std::move(hist2DQueue_.front());
                            hist2DQueue_.pop_front();
                            break;
                        case QueueLane::Graph:
                            graph = std::move(graphQueue_.front());
                            graphQueue_.pop_front();
                            break;
                        case QueueLane::Profile:
                            profile = std::move(profileQueue_.front());
                            profileQueue_.pop_front();
                            break;
                        case QueueLane::Tree:
                            tree = std::move(treeQueue_.front());
                            treeQueue_.pop_front();
                            break;
                        case QueueLane::Checkpoint:
                            checkpoint = std::move(checkpointQueue_.front());
                            checkpointQueue_.pop_front();
                            break;
                        case QueueLane::Finish:
                            finish = std::move(finishQueue_.front());
                            finishQueue_.pop_front();
                            break;
                        case QueueLane::FatalWrite:
                            fatal = std::move(fatalQueue_.front());
                            fatalQueue_.pop_front();
                            break;
                        case QueueLane::Stop:
                            finishSeen = true;
                            break;
                    }
                }
                queueNotFull_.notify_all();

                try {
                    switch (ticket.lane) {
                        case QueueLane::Particle:   applyParticleRequest(particle); break;
                        case QueueLane::Hist1D:     applyHist1DRequest(hist1D); break;
                        case QueueLane::Hist2D:     applyHist2DRequest(hist2D); break;
                        case QueueLane::Graph:      applyGraphRequest(graph); break;
                        case QueueLane::Profile:    applyProfileRequest(profile); break;
                        case QueueLane::Tree:       applyTreeRowRequest(tree); break;
                        case QueueLane::Checkpoint:
                            writeCheckpointFile(checkpoint.eventIndex);
                            completeBarrier(checkpoint.barrier);
                            break;
                        case QueueLane::Finish:
                            writeAllToCurrentFile(finish.eventCount, false);
                            completeBarrier(finish.barrier);
                            finishSeen = true;
                            break;
                        case QueueLane::FatalWrite:
                            writeAllToCurrentFile(fatal.eventCount, false);
                            completeBarrier(fatal.barrier);
                            finishSeen = true;
                            break;
                        case QueueLane::Stop:
                            finishSeen = true;
                            break;
                    }
                } catch (...) {
                    const std::exception_ptr error = std::current_exception();
                    if (ticket.lane == QueueLane::Checkpoint) completeBarrier(checkpoint.barrier, error, false);
                    if (ticket.lane == QueueLane::Finish)     completeBarrier(finish.barrier, error, false);
                    if (ticket.lane == QueueLane::FatalWrite) completeBarrier(fatal.barrier, error, false);
                    setScribeException(error);
                    failPendingBarriers(error);
                    finishSeen = true;
                }
            }
            accepting_.store(false, std::memory_order_release);
            queueNotFull_.notify_all();
        }

        void setScribeException(std::exception_ptr error) {
            std::lock_guard<std::mutex> lock(queueMutex_);
            if (!scribeException_) scribeException_ = std::move(error);
        }

        void failPendingBarriers(std::exception_ptr error) {
            std::vector<std::shared_ptr<BarrierState>> barriers;
            {
                std::lock_guard<std::mutex> lock(queueMutex_);
                accepting_.store(false, std::memory_order_release);
                for (auto& request : checkpointQueue_)
                    if (request.barrier) barriers.push_back(request.barrier);
                for (auto& request : finishQueue_)
                    if (request.barrier) barriers.push_back(request.barrier);
                for (auto& request : fatalQueue_)
                    if (request.barrier) barriers.push_back(request.barrier);
                checkpointQueue_.clear();
                finishQueue_.clear();
                fatalQueue_.clear();
                grandQueue_.clear();
            }
            for (const auto& barrier : barriers)
                completeBarrier(barrier, error, false);
            queueNotFull_.notify_all();
        }

        void applyParticleRequest(const ParticleRequest& request) {
            for (const auto& group : request.groups) {
                auto it = particleObjects_.find(group.basis);
                if (it == particleObjects_.end())
                    throw std::runtime_error("[Record::Writer] missing particle group " + keyString(group.basis));

                ParticleObjects& object = it->second;
                object.candidateCount = 0;
                for (const Physics::Lorentz& particle : group.particles) {
                    ++object.candidateCount;
                    for (auto& hist : object.hists1D)
                        hist.hist->Fill(Physics::valueOf(particle, hist.property));
                    for (auto& hist : object.hists2D)
                        hist.hist->Fill(Physics::valueOf(particle, hist.propertyX),
                                        Physics::valueOf(particle, hist.propertyY));
                    for (auto& graph : object.graphs)
                        graph.graph->SetPoint(graph.nextPoint++,
                                              Physics::valueOf(particle, graph.propertyX),
                                              Physics::valueOf(particle, graph.propertyY));
                    for (auto& profile : object.profiles)
                        profile.profile->Fill(Physics::valueOf(particle, profile.propertyX),
                                              Physics::valueOf(particle, profile.propertyY));
                    if (object.tree.tree != nullptr)
                        fillParticleTree(object.tree, particle);
                }
                if (object.count != nullptr)
                    object.count->Fill(object.candidateCount);
            }
        }

        static void fillParticleTree(ParticleTree& tree, const Physics::Lorentz& particle) {
            if (tree.tree == nullptr) return;
            if (tree.properties.size() != tree.branches.size())
                throw std::runtime_error("[Record::Writer] particle tree branch/property size mismatch");
            for (std::size_t i = 0; i < tree.properties.size(); ++i)
                setBranchBuffer(tree.branches[i], Value{Physics::valueOf(particle, tree.properties[i])});
            tree.tree->Fill();
        }

        void applyHist1DRequest(const Hist1DRequest& request) {
            auto it = hists1D_.find(request.basis);
            if (it == hists1D_.end())
                throw std::runtime_error("[Record::Writer] missing hist1D " + keyString(request.basis));
            it->second.hist->Fill(RootUtil::toDouble(request.value));
        }

        void applyHist2DRequest(const Hist2DRequest& request) {
            auto it = hists2D_.find(request.basis);
            if (it == hists2D_.end())
                throw std::runtime_error("[Record::Writer] missing hist2D " + keyString(request.basis));
            it->second.hist->Fill(RootUtil::toDouble(request.x), RootUtil::toDouble(request.y));
        }

        void applyGraphRequest(const GraphRequest& request) {
            auto it = graphs_.find(request.basis);
            if (it == graphs_.end())
                throw std::runtime_error("[Record::Writer] missing graph " + keyString(request.basis));
            GraphRecord& record = it->second;
            record.graph->SetPoint(record.nextPoint++,
                                   RootUtil::toDouble(request.x),
                                   RootUtil::toDouble(request.y));
        }

        void applyProfileRequest(const ProfileRequest& request) {
            auto it = profiles_.find(request.basis);
            if (it == profiles_.end())
                throw std::runtime_error("[Record::Writer] missing profile " + keyString(request.basis));
            it->second.profile->Fill(RootUtil::toDouble(request.x), RootUtil::toDouble(request.y));
        }

        void applyTreeRowRequest(const TreeRowRequest& request) {
            auto treeIt = trees_.find(request.tree);
            if (treeIt == trees_.end())
                throw std::runtime_error("[Record::Writer] missing tree " + keyString(request.tree));

            ExplicitTreeRecord& tree = treeIt->second;
            if (request.values.size() != tree.branchOrder.size())
                throw std::runtime_error("[Record::Writer] tree row for " + keyString(request.tree) +
                                         " does not supply exactly all branches");

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

        void writeCheckpointFile(std::size_t eventIndex) {
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

        void writeAllToCurrentFile(std::size_t eventCount, bool checkpoint) {
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

        void writeParticleObjects(ParticleObjects& object,
                                  std::size_t eventCount,
                                  bool checkpoint) {
            writeParticleObjectsToDir(object, object.dir, eventCount, checkpoint);
        }

        void writeParticleObjectsToDir(ParticleObjects& object,
                                       TDirectory* dir,
                                       std::size_t eventCount,
                                       bool checkpoint) {
            if (dir == nullptr) return;
            scaleAndWriteToDir(dir, object.count, hist_.histScale, eventCount, false);
            for (auto& hist : object.hists1D) scaleAndWriteToDir(dir, hist.hist, hist_.histScale, eventCount, true);
            for (auto& hist : object.hists2D) scaleAndWriteToDir(dir, hist.hist, hist_.histScale, eventCount, false);
            for (auto& graph : object.graphs) scaleAndWriteToDir(dir, graph.graph, hist_.histScale, eventCount, false);
            for (auto& profile : object.profiles) scaleAndWriteToDir(dir, profile.profile, hist_.histScale, eventCount, false);
            if (!checkpoint && object.tree.tree != nullptr)
                scaleAndWriteToDir(dir, object.tree.tree, hist_.histScale, eventCount, false);
        }

        void writeIndependentObjects(std::size_t eventCount, bool checkpoint) {
            writeIndependentObjectsToDir(outFile_, eventCount, checkpoint);
        }

        void writeIndependentObjectsToDir(TDirectory* dir,
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

        static bool hasBranchNamed(const ExplicitTreeRecord& record, const std::string& name) {
            for (const auto& [key, branch] : record.branches) {
                (void)key;
                if (branch.name == name) return true;
            }
            return false;
        }

        void clearRecords() {
            particleObjects_.clear();
            hists1D_.clear();
            hists2D_.clear();
            graphs_.clear();
            profiles_.clear();
            trees_.clear();
        }

        void clearQueues() {
            std::lock_guard<std::mutex> lock(queueMutex_);
            grandQueue_.clear();
            particleQueue_.clear();
            hist1DQueue_.clear();
            hist2DQueue_.clear();
            graphQueue_.clear();
            profileQueue_.clear();
            treeQueue_.clear();
            checkpointQueue_.clear();
            finishQueue_.clear();
            fatalQueue_.clear();
            produced_ = 0;
            consumed_ = 0;
            maxBacklog_ = 0;
            scribeException_ = nullptr;
        }

        void closeFile() {
            if (outFile_ != nullptr) {
                outFile_->Close();
                delete outFile_;
                outFile_ = nullptr;
            }
        }

        void cleanup() {
            accepting_.store(false, std::memory_order_release);
            stopRequested_.store(true, std::memory_order_release);
            queueNotEmpty_.notify_all();
            queueNotFull_.notify_all();
            if (scribe_.joinable()) scribe_.join();
            started_.store(false, std::memory_order_release);
            closeFile();
        }

        Paths        paths_;
        HistConfig   hist_;
        Meta::Record meta_;
        TFile*       outFile_ = nullptr;

        Config::Watch*               logging_       = nullptr;
        Monitor::AsyncLogger*        logger_        = nullptr;
        std::function<std::string()> programLog_;
        std::function<void()>        printStats_;
        std::function<void()>        listChanged_;
        std::function<void()>        preCloseHook_;
        std::atomic<bool>            fatalShutdownStarted_{false};

        std::unordered_map<RecordKey, ParticleObjects,   RecordKeyHash> particleObjects_;
        std::unordered_map<RecordKey, Hist1DRecord,      RecordKeyHash> hists1D_;
        std::unordered_map<RecordKey, Hist2DRecord,      RecordKeyHash> hists2D_;
        std::unordered_map<RecordKey, GraphRecord,       RecordKeyHash> graphs_;
        std::unordered_map<RecordKey, ProfileRecord,     RecordKeyHash> profiles_;
        std::unordered_map<RecordKey, ExplicitTreeRecord,RecordKeyHash> trees_;

        std::deque<QueueTicket>      grandQueue_;
        std::deque<ParticleRequest>  particleQueue_;
        std::deque<Hist1DRequest>    hist1DQueue_;
        std::deque<Hist2DRequest>    hist2DQueue_;
        std::deque<GraphRequest>     graphQueue_;
        std::deque<ProfileRequest>   profileQueue_;
        std::deque<TreeRowRequest>   treeQueue_;
        std::deque<CheckpointRequest> checkpointQueue_;
        std::deque<FinishRequest>     finishQueue_;
        std::deque<FatalWriteRequest> fatalQueue_;

        mutable std::mutex queueMutex_;
        std::condition_variable queueNotEmpty_;
        std::condition_variable queueNotFull_;
        std::size_t queueCapacity_ = 1024;
        std::thread scribe_;
        std::atomic<bool> started_{false};
        std::atomic<bool> accepting_{false};
        std::atomic<bool> stopRequested_{false};
        std::exception_ptr scribeException_;
        std::size_t produced_ = 0;
        std::size_t consumed_ = 0;
        std::size_t maxBacklog_ = 0;

        // WriterMT.md Phase 0: stored from [record].thread_count.  Used by
        // Phase 2's worker pool; not consulted in Phase 0 except for stats.
        std::size_t recordThreadCount_ = 0;
    };

    inline void configureWriter(Writer&                 writer,
                                const std::string&      project,
                                const std::string&      configPath,
                                Config::Watch&          watch,
                                Config::Register&       reg,
                                const std::string&      probeInputFile = "")
    {
        Paths paths;
        paths.rootDirectory       = reg.rootDirectory;
        paths.logDirectory        = reg.logDirectory;
        paths.checkpointDirectory = reg.checkpointDirectory;
        paths.outName             = reg.outName;
        paths.logName             = reg.logName;
        paths.runStatName         = reg.runStatName;
        paths.threadStatDirectory = reg.threadStatDirectory;
        paths.checkpointOutName   = reg.checkpointOutName;
        paths.checkpointLogName   = reg.checkpointLogName;
        paths.fileTitle           = reg.fileTitle;
        paths.beamEnergy          = reg.beamEnergy;
        paths.serial              = reg.serial;

        HistConfig hist;
        hist.binCount       = reg.binCount;
        hist.histScale      = reg.histScale;
        hist.histLimitsFile = reg.histLimitsFile;
        hist.particleLimits = reg.particleLimits;
        hist.eventLimits    = reg.eventLimits;

        Meta::Record meta;
        Meta::mergeFromToml(meta, configPath);
        if (!probeInputFile.empty())
            Meta::mergeFromProbe(meta, probeInputFile);
        Meta::fillDerived(meta, project, configPath, watch, reg);

        writer.open(std::move(paths), std::move(hist), std::move(meta));
    }

} // namespace Record
