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
        Writer();
        ~Writer();

        Writer(const Writer&)            = delete;
        Writer& operator=(const Writer&) = delete;
        Writer(Writer&&)                 = delete;
        Writer& operator=(Writer&&)      = delete;

        // Administration
        void open(Paths paths, HistConfig hist, Meta::Record initialMeta);
        void setProjectInfo(std::string project, std::string configPath);
        void bind(Monitor::AsyncLogger&        logger,
                  std::function<std::string()> programLog,
                  std::function<void()>         printStats   = {},
                  std::function<void()>         listChanged  = {},
                  std::function<void()>         preCloseHook = {});
        void start();
        void checkpoint(std::size_t eventIndex);
        void signalWatch(WatchRequest req);
        void finish(std::size_t eventCount);
        bool fatalWrite(std::size_t eventCount, std::chrono::milliseconds timeout);
        void setQueueCapacity(std::size_t capacity);
        std::size_t queueCapacity() const;
        void setRecordThreadCount(std::size_t n);
        std::size_t recordThreadCount() const;
        std::string stats() const;

        TFile*              file()       const;
        const Paths&        paths()      const;
        const HistConfig&   histConfig() const;
        Meta::Record&       meta();
        const Meta::Record& meta()       const;

        // Declaration
        template <typename Basis>
        void declareParticleGroup(Basis basis,
                                  std::string directoryName,
                                  std::string displayName);

        template <typename Basis>
        void declareParticleCount(Basis basis,
                                  std::string histName,
                                  std::string title,
                                  int bins,
                                  double low,
                                  double high);

        template <typename Basis>
        void declareParticleHist1D(Basis basis,
                                   Physics::ParticleProperty property,
                                   std::string histName,
                                   std::string title,
                                   int bins,
                                   double low,
                                   double high);

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
                                   double highY);

        template <typename Basis>
        void declareParticleGraph(Basis basis,
                                  Physics::ParticleProperty propertyX,
                                  Physics::ParticleProperty propertyY,
                                  std::string graphName,
                                  std::string title);

        template <typename Basis>
        void declareParticleProfile(Basis basis,
                                    Physics::ParticleProperty propertyX,
                                    Physics::ParticleProperty propertyY,
                                    std::string profileName,
                                    std::string title,
                                    int binsX,
                                    double lowX,
                                    double highX);

        template <typename Basis>
        void declareParticleTree(Basis basis,
                                 std::string treeName,
                                 std::string title,
                                 std::vector<Physics::ParticleProperty> properties);

        template <typename Basis>
        void declareHist1D(Basis basis,
                           std::string histName,
                           std::string title,
                           int bins,
                           double low,
                           double high,
                           DataType type = DataType::Double);

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
                           DataType typeY = DataType::Double);

        template <typename Basis>
        void declareGraph(Basis basis,
                          std::string graphName,
                          std::string title,
                          DataType typeX = DataType::Double,
                          DataType typeY = DataType::Double);

        template <typename Basis>
        void declareProfile(Basis basis,
                            std::string profileName,
                            std::string title,
                            int binsX,
                            double lowX,
                            double highX,
                            DataType typeX = DataType::Double,
                            DataType typeY = DataType::Double);

        template <typename TreeBasis, typename BranchBasis>
        void declareTree(TreeBasis treeBasis,
                         std::string treeName,
                         std::string title,
                         std::vector<std::tuple<BranchBasis, std::string, DataType>> branches);

        // Recording requests
        template <typename Basis>
        void fillParticleEvent(std::vector<std::pair<Basis, std::vector<Physics::Lorentz>>> fills);

        template <typename Basis>
        void fillHist1D(Basis basis, Value value);

        template <typename Basis>
        void fillHist2D(Basis basis, Value x, Value y);

        template <typename Basis>
        void fillGraph(Basis basis, Value x, Value y);

        template <typename Basis>
        void fillProfile(Basis basis, Value x, Value y);

        template <typename TreeBasis, typename BranchBasis>
        void fillTree(TreeBasis tree,
                      std::initializer_list<std::pair<BranchBasis, Value>> values);

      private:
        void fatalShutdown(const Monitor::RunSnapshot& snapshot);

        // Declaration helpers
        template <typename Basis>
        static void requireEnumBasis();

        void requireOpenForDeclaration(const std::string& kind) const;
        void requireNotStarted(const std::string& kind) const;

        template <typename Basis>
        ParticleObjects& requireParticleGroupForDeclaration(Basis basis, const std::string& kind);

        static void validateObjectName(const std::string& name, const std::string& kind);
        static void validateHistogramShape(const std::string& name, int bins, double low, double high);
        static void requireNumeric(DataType type, const std::string& context);
        static void ensureUniqueParticleName(const ParticleObjects& object, const std::string& name);

        // Request and worker directives
        static void waitBarrier(const std::shared_ptr<BarrierState>& barrier);
        static void enableRootThreadSafety();
        static void completeBarrier(const std::shared_ptr<BarrierState>& barrier,
                                    std::exception_ptr exception = nullptr,
                                    bool completed = true);

        void throwIfCannotAcceptLocked() const;

        template <typename Payload>
        void pushFill(Payload&& payload);

        void signalWatchInternal(WatchRequest req);
        void workerLoop(int workerIdx);
        void arriveAtQuiesce();
        void quiesceWorkers();
        void releaseWorkers();
        void watchdogLoop();
        void drainAndStopWorkers();
        void joinWorkers();
        void setWriterException(std::exception_ptr error);
        void failPendingWatchBarriers(std::exception_ptr error);

        // Recording and writing
        void applyParticleRequest(const ParticleRequest& request, int workerIdx);
        static void fillParticleTreeLocked(ParticleTree& tree, const Physics::Lorentz& particle);
        void applyHist1DRequest(const Hist1DRequest& request, int workerIdx);
        void applyHist2DRequest(const Hist2DRequest& request, int workerIdx);
        void applyGraphRequest(const GraphRequest& request, int workerIdx);
        void applyProfileRequest(const ProfileRequest& request, int workerIdx);
        void applyTreeRowRequest(const TreeRowRequest& request, int workerIdx);
        void writeCheckpointFile(std::size_t eventIndex);
        void writeAllToCurrentFile(std::size_t eventCount, bool checkpoint);
        void writeParticleObjects(ParticleObjects& object,
                                  std::size_t eventCount,
                                  bool checkpoint);
        void writeParticleObjectsToDir(ParticleObjects& object,
                                       TDirectory* dir,
                                       std::size_t eventCount,
                                       bool checkpoint);
        void writeIndependentObjects(std::size_t eventCount, bool checkpoint);
        void writeIndependentObjectsToDir(TDirectory* dir,
                                          std::size_t eventCount,
                                          bool checkpoint);
        static bool hasBranchNamed(const ExplicitTreeRecord& record, const std::string& name);

        // Administration cleanup
        void clearRecords();
        void clearQueues();
        void closeFile();
        void cleanup();

        // Cloning
        void allocateAllClones();

        template <typename Rec>
        void cloneTH1Impl(Rec& r);

        template <typename Rec>
        void cloneTH2Impl(Rec& r);

        template <typename Rec>
        void cloneGraphImpl(Rec& r);

        template <typename Rec>
        void cloneProfileImpl(Rec& r);

        void mergeAllClones();

        template <typename Rec>
        static void mergeTH1Impl(Rec& r);

        template <typename Rec>
        static void mergeTH2Impl(Rec& r);

        template <typename Rec>
        static void mergeProfileImpl(Rec& r);

        template <typename Rec>
        static void mergeGraphImpl(Rec& r);

        Paths        paths_;
        HistConfig   hist_;
        Meta::Record meta_;
        TFile*       outFile_ = nullptr;
        std::string  project_;
        std::string  configPath_;

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

        std::deque<FillRequest> fillQueue_;
        mutable std::mutex      fillMutex_;
        std::condition_variable fillNotEmpty_;
        std::condition_variable fillNotFull_;
        std::size_t             queueCapacity_ = 1024;

        std::deque<WatchRequest> watchQueue_;
        mutable std::mutex       watchMutex_;
        std::condition_variable  watchCv_;

        std::vector<std::thread> workers_;
        std::thread              watchdog_;

        std::atomic<bool>        quiesceRequested_{false};
        std::size_t              quiesceArrived_{0};
        mutable std::mutex       quiesceMutex_;
        std::condition_variable  quiesceHold_;
        std::condition_variable  quiesceCv_;

        std::atomic<bool>  started_{false};
        std::atomic<bool>  accepting_{false};
        std::atomic<bool>  stopRequested_{false};
        std::exception_ptr writerException_;
        std::size_t        produced_   = 0;
        std::size_t        consumed_   = 0;
        std::size_t        maxBacklog_ = 0;

        std::size_t nRecordThreads_    = 0;
        std::atomic<std::size_t> activeWorkers_{0};

        // Per-request-kind fill counters (incremented by workers).
        std::atomic<std::size_t> countParticle_{0};
        std::atomic<std::size_t> countHist1D_{0};
        std::atomic<std::size_t> countHist2D_{0};
        std::atomic<std::size_t> countGraph_{0};
        std::atomic<std::size_t> countProfile_{0};
        std::atomic<std::size_t> countTree_{0};
    };

    inline void configureWriter(Writer&                 writer,
                                const std::string&      project,
                                const std::string&      configPath,
                                Config::Watch&          watch,
                                Config::Register&       reg,
                                const std::string&      probeInputFile = "");

} // namespace Record

#include "Record/Declaration.hh"
#include "Record/Recording.hh"
#include "Record/Directives.hh"
#include "Record/Cloning.hh"
#include "Record/Administration.hh"
