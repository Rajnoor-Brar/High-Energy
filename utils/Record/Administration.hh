#pragma once

#include "Record/Writer.hh"
#include "Monitor/Administration.hh"
#include "Monitor/Directive.hh"

namespace Record {


inline Writer::Writer() = default;

inline Writer::~Writer() { cleanup(); }

inline void Writer::setProjectInfo(std::string project, std::string configPath) {
    project_    = std::move(project);
    configPath_ = std::move(configPath);
}

inline void Writer::open(Paths paths, HistConfig hist, Meta::Record initialMeta) {
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

inline void Writer::start() {
        if (outFile_ == nullptr)
            throw std::runtime_error("[Record::Writer] start() called before open()");
        enableRootThreadSafety();
        bool expected = false;
        if (!started_.compare_exchange_strong(expected, true))
            throw std::runtime_error("[Record::Writer] start() called more than once");

        if (nRecordThreads_ == 0) nRecordThreads_ = 1;
        // Default queue capacity scales with worker count per WriterMT.md.
        if (queueCapacity_ < 10 * nRecordThreads_)
            queueCapacity_ = 10 * nRecordThreads_;

        allocateAllClones();

        accepting_.store(true, std::memory_order_release);
        stopRequested_.store(false, std::memory_order_release);
        writerException_ = nullptr;

        workers_.reserve(nRecordThreads_);
        for (std::size_t i = 0; i < nRecordThreads_; ++i)
            workers_.emplace_back(&Writer::workerLoop, this, static_cast<int>(i));
        watchdog_ = std::thread(&Writer::watchdogLoop, this);
    }

inline void Writer::checkpoint(std::size_t eventIndex) {
        auto barrier = std::make_shared<BarrierState>();
        WatchRequest req;
        req.kind       = WatchRequest::Kind::Checkpoint;
        req.eventIndex = eventIndex;
        req.barrier    = barrier;
        signalWatch(std::move(req));
        waitBarrier(barrier);
    }

// Public entry for the AsyncLogger's WatchSink and any external trigger.
inline         void Writer::signalWatch(WatchRequest req) { signalWatchInternal(std::move(req)); }

inline bool Writer::fatalWrite(std::size_t eventCount, std::chrono::milliseconds timeout) {
        if (!started_.load(std::memory_order_acquire))
            throw std::runtime_error("[Record::Writer] fatalWrite() called before start()");

        accepting_.store(false, std::memory_order_release);
        fillNotFull_.notify_all();

        auto barrier = std::make_shared<BarrierState>();
        WatchRequest req;
        req.kind       = WatchRequest::Kind::Fatal;
        req.eventIndex = eventCount;
        req.barrier    = barrier;
        signalWatchInternal(std::move(req));

        std::unique_lock<std::mutex> lock(barrier->mutex);
        const bool done = barrier->cv.wait_for(lock, timeout, [&] { return barrier->done; });
        if (!done) return false;
        if (barrier->exception) std::rethrow_exception(barrier->exception);
        return barrier->completed;
    }

inline void Writer::setQueueCapacity(std::size_t capacity) {
        if (capacity == 0)
            throw std::runtime_error("[Record::Writer] queue capacity must be positive");
        std::lock_guard<std::mutex> lock(fillMutex_);
        queueCapacity_ = capacity;
        fillNotFull_.notify_all();
    }

inline std::size_t Writer::queueCapacity() const {
        std::lock_guard<std::mutex> lock(fillMutex_);
        return queueCapacity_;
    }

// docs/WriterMT.md Phase 2: configure the worker pool size.  Must
    // be called before start().  The same value sizes both per-record
    // clone vectors and the worker thread count.
inline         void Writer::setRecordThreadCount(std::size_t n) {
        if (started_.load(std::memory_order_acquire))
            throw std::runtime_error(
                "[Record::Writer] setRecordThreadCount() called after start()");
        nRecordThreads_ = n;
    }

inline std::size_t Writer::recordThreadCount() const { return nRecordThreads_; }

inline std::string Writer::stats() const {
        std::lock_guard<std::mutex> lock(fillMutex_);
        std::ostringstream out;
        out << "Record::Writer{"
            << "started=" << started_.load(std::memory_order_relaxed)
            << ", accepting=" << accepting_.load(std::memory_order_relaxed)
            << ", recordThreadCount=" << nRecordThreads_
            << ", queueCapacity=" << queueCapacity_
            << ", backlog=" << fillQueue_.size()
            << ", produced=" << produced_
            << ", consumed=" << consumed_
            << ", maxBacklog=" << maxBacklog_
            << "}";
        return out.str();
    }

inline TFile*              Writer::file()       const { return outFile_; }

inline const Paths&        Writer::paths()      const { return paths_; }

inline const HistConfig&   Writer::histConfig() const { return hist_; }

inline Meta::Record&       Writer::meta() { return meta_; }

inline const Meta::Record& Writer::meta()       const { return meta_; }

inline void Writer::requireOpenForDeclaration(const std::string& kind) const {
        if (outFile_ == nullptr)
            throw std::runtime_error("[Record::Writer] open() must be called before declaring " + kind);
    }

inline void Writer::requireNotStarted(const std::string& kind) const {
        if (started_.load(std::memory_order_acquire))
            throw std::runtime_error("[Record::Writer] cannot declare " + kind + " after start()");
    }

inline void Writer::waitBarrier(const std::shared_ptr<BarrierState>& barrier) {
        std::unique_lock<std::mutex> lock(barrier->mutex);
        barrier->cv.wait(lock, [&] { return barrier->done; });
        if (barrier->exception) std::rethrow_exception(barrier->exception);
    }

inline void Writer::enableRootThreadSafety() {
        // Required: see Probe::BranchControl::enableRootThreadSafety
        // for the rationale and the Phase A experiment that
        // confirmed it. The scribe is single-threaded for ROOT
        // mutation, but ROOT's internal shared state (TClass DB,
        // gROOT, allocators) still races between scribe and
        // concurrent producers if this is not enabled.
        static std::once_flag flag;
        std::call_once(flag, [] { ROOT::EnableThreadSafety(); });
    }

inline void Writer::completeBarrier(const std::shared_ptr<BarrierState>& barrier,
                                std::exception_ptr exception,
                                bool completed) {
        if (!barrier) return;
        {
            std::lock_guard<std::mutex> lock(barrier->mutex);
            barrier->exception = std::move(exception);
            barrier->completed = completed;
            barrier->done = true;
        }
        barrier->cv.notify_all();
    }

inline void Writer::clearRecords() {
        particleObjects_.clear();
        hists1D_.clear();
        hists2D_.clear();
        graphs_.clear();
        profiles_.clear();
        trees_.clear();
    }

inline void Writer::clearQueues() {
        {
            std::lock_guard<std::mutex> lock(fillMutex_);
            fillQueue_.clear();
            produced_ = 0;
            consumed_ = 0;
            maxBacklog_ = 0;
            writerException_ = nullptr;
        }
        {
            std::lock_guard<std::mutex> lock(watchMutex_);
            watchQueue_.clear();
        }
    }

inline void Writer::closeFile() {
        if (outFile_ != nullptr) {
            outFile_->Close();
            delete outFile_;
            outFile_ = nullptr;
        }
    }

inline void Writer::cleanup() {
        accepting_.store(false, std::memory_order_release);
        stopRequested_.store(true, std::memory_order_release);
        fillNotEmpty_.notify_all();
        fillNotFull_.notify_all();
        watchCv_.notify_all();
        quiesceHold_.notify_all();
        quiesceCv_.notify_all();
        for (auto& t : workers_) if (t.joinable()) t.join();
        workers_.clear();
        if (watchdog_.joinable()) watchdog_.join();
        started_.store(false, std::memory_order_release);
        closeFile();
    }

namespace {
    constexpr auto kFatalGracePeriod = std::chrono::seconds(10);
    }

inline void Writer::bind(Monitor::AsyncLogger&        logger,
                         std::function<std::string()> programLog,
                         std::function<void()>         printStats,
                         std::function<void()>         listChanged,
                         std::function<void()>         preCloseHook)
    {
    logger_       = &logger;
    logging_      = &(logger.watch());
    programLog_   = std::move(programLog);
    printStats_   = std::move(printStats);
    listChanged_  = std::move(listChanged);
    preCloseHook_ = std::move(preCloseHook);

    logger_->setFatalStallHandler([this](const Monitor::RunSnapshot& snapshot) {
        fatalShutdown(snapshot);
    });

    // docs/WriterMT.md Phase 2: route the logger's WatchRequest emission
    // (driven by [monitor].save_heartbeat / save_checkpoints) into the
    // Writer's watchdog control queue.
    logger.bindWatchSink([this](Record::WatchRequest req) {
        signalWatch(std::move(req));
    });
    }

inline void Writer::finish(std::size_t eventCount) {
    // Refresh derived meta (event counts, timing) with final values before writing.
    if (logging_ != nullptr && !project_.empty())
        Meta::fillDerived(meta_, project_, configPath_, *logging_, Config::Register{});

    accepting_.store(false, std::memory_order_release);
    fillNotFull_.notify_all();

    auto barrier = std::make_shared<BarrierState>();
    std::exception_ptr error;

    try {
        WatchRequest req;
        req.kind       = WatchRequest::Kind::Finalize;
        req.eventIndex = eventCount;
        req.barrier    = barrier;
        signalWatch(std::move(req));
        waitBarrier(barrier);
    } catch (...) {
        error = std::current_exception();
    }

    // Watchdog has merged + written + closed the file.  Join everyone.
    for (auto& t : workers_) if (t.joinable()) t.join();
    workers_.clear();
    if (watchdog_.joinable()) watchdog_.join();
    started_.store(false, std::memory_order_release);

    if (error) std::rethrow_exception(error);

    if (logging_ != nullptr && logger_ != nullptr) {
        logging_->elapsed = std::chrono::duration_cast<Config::uSeconds>(
            std::chrono::system_clock::now() - logging_->start);
        logger_->finish(*logging_, logging_->iEvent.load(std::memory_order_relaxed));
        Monitor::terminalReport(*this, *logging_, printStats_);
        // docs/WriterMT.md: [monitor].save_final_log gates the on-disk
        // final summary log.  Terminal report still prints regardless;
        // skipping the file output keeps the logs/ directory clean for
        // smoke runs that don't need a persistent record.
        if (logger_->saveFinalLog()) {
            Monitor::outputLog(*this, *logging_, programLog_ ? programLog_() : std::string{},
                               {}, printStats_, listChanged_, &logger_->pacingInfo());
        }
    }
    }

inline void Writer::fatalShutdown(const Monitor::RunSnapshot& snapshot) {
    if (fatalShutdownStarted_.exchange(true)) return;

    auto frozenLog = std::shared_ptr<Config::Watch>(logging_->freeze());
    frozenLog->elapsed.store(
        std::chrono::duration_cast<Config::uSeconds>(
            std::chrono::system_clock::now() - logging_->start),
        std::memory_order_relaxed);
    Monitor::RunSnapshot frozenSnapshot = snapshot;
    frozenSnapshot.elapsed = frozenLog->elapsed.load(std::memory_order_relaxed);

    const std::string programLog = programLog_ ? programLog_() : std::string{};
    Monitor::writeEmergencyLog(*this, *frozenLog, frozenSnapshot, programLog,
                               "fatal-stall detected");

    bool completed = false;
    try {
        completed = fatalWrite(frozenLog->nEvents,
                               std::chrono::duration_cast<std::chrono::milliseconds>(kFatalGracePeriod));
        if (completed) {
            for (auto& t : workers_) if (t.joinable()) t.join();
            workers_.clear();
            if (watchdog_.joinable()) watchdog_.join();
        }
    } catch (...) {
        completed = false;
    }

    if (completed) {
        Monitor::outputLog(*this, *frozenLog, programLog, {}, printStats_, listChanged_,
                           &logger_->pacingInfo());
        std::_Exit(EXIT_FAILURE);
    }

    Monitor::writeEmergencyLog(*this, *frozenLog, frozenSnapshot, programLog,
                               "fatal-stall fallback after timed-out write/log attempt");
    std::_Exit(EXIT_FAILURE);
    }

inline void configureWriter(Writer&                 writer,
                        const std::string&      project,
                        const std::string&      configPath,
                        Config::Watch&          watch,
                        Config::Register&       reg,
                        const std::string&      probeInputFile)
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
    writer.setProjectInfo(project, configPath);
}

} // namespace Record
