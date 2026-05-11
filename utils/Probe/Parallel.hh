#pragma once

#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <exception>
#include <limits>
#include <memory>
#include <mutex>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "Config.hh"
#include "Probe/BranchControl.hh"
#include "Probe/Event.hh"
#include "Probe/EventCount.hh"
#include "Probe/Splitter.hh"
#include "Probe/Types.hh"

namespace Probe {

    class ProbeParallel {
      public:
        ProbeParallel() = default;

        ~ProbeParallel() { cleanupShards(); }

        // configureProbe — primary configuration entry point.
        //
        // splitInput:      master switch for Phase 1 input-file sharding.
        //                  Default false because measurement showed no CPU-floor
        //                  improvement on our access pattern (global ROOT mutex
        //                  is the real bottleneck, not per-TFile contention).
        //                  Enable via [probe].split_input = true for A/B testing
        //                  or future composition with TTreeProcessorMT.
        // tempSpace:       base directory for shard files (e.g. "temp/").
        //                  Empty → resolved from shardKeyPrefix ("temp/<prefix>/")
        //                  or "temp/probe_shards/" as a last fallback.
        // keepShards:      if true, shard directory is NOT removed on destruction.
        //                  Use for cached reuse across repeated runs over the same
        //                  input file.  Ignored when splitInput is false.
        // shardKeyPrefix:  [record.file].prefix string; used to build the default
        //                  temp sub-directory.  Ignored when tempSpace is explicit.
        //
        // Sharding only activates when splitInput=true AND threadCount_ > 1.
        void configureProbe(std::string inputFile,
                            std::vector<ParticleSpec> particleSpecs,
                            std::size_t threadCount,
                            std::size_t requestedEvents,
                            bool userRequestedEvents,
                            bool        splitInput     = false,
                            std::string tempSpace      = "",
                            bool        keepShards     = false,
                            std::string shardKeyPrefix = "")
        {
            BranchControl::enableRootThreadSafety();

            inputFile_      = std::move(inputFile);
            particleSpecs_  = std::move(particleSpecs);
            threadCount_    = Config::resolveThreadCount(threadCount);
            keepShards_     = keepShards;
            configured_     = false;
            eventCount_     = 0;
            eventRange_     = {};
            eventPartitions_.clear();
            indexSpecs_.clear();
            entryBoundsByWorker_.clear();
            inputShards_.clear();
            ownsShards_    = false;
            shardTempDir_.clear();

            if (inputFile_.empty())
                throw std::runtime_error("[Probe] ProbeParallel: input file is empty");
            if (particleSpecs_.empty())
                throw std::runtime_error("[Probe] ProbeParallel: no particle specs configured");
            if (threadCount_ == 0)
                throw std::runtime_error("[Probe] ProbeParallel: resolved thread count is zero");

            determineStreamType();
            buildIndexSpecs();

            std::vector<Long64_t> bruteKeys;
            if (userRequestedEvents) {
                eventCount_ = requestedEvents;
            } else {
                eventCount_ = Probe::resolveEventCount(inputFile_);
                if (eventCount_ == 0) {
                    if (streamType_ == StreamType::Events) {
                        bruteKeys = scanFlatEventKeys();
                        eventCount_ = bruteKeys.size();
                    } else if (streamType_ == StreamType::Vectors) {
                        eventCount_ = vectorEntryCount();
                    }
                }
            }

            if (eventCount_ == 0) {
                configured_ = true;
                return;
            }

            prepareEventPartitions(bruteKeys);
            prepareEntryBounds();

            // ── Phase 1 sharding: one TFile per worker ────────────────────────
            // Opt-in: gated on splitInput=true.  Skipped when single-threaded
            // (no contention to eliminate) or when no partitions were produced.
            if (splitInput && threadCount_ > 1 && !eventPartitions_.empty()) {
                std::string baseDir;
                if (!tempSpace.empty()) {
                    baseDir = tempSpace;
                    if (baseDir.back() != '/') baseDir += '/';
                } else if (!shardKeyPrefix.empty()) {
                    baseDir = "temp/" + shardKeyPrefix + "/";
                } else {
                    baseDir = "temp/probe_shards/";
                }
                inputShards_ = Splitter::ensureShards(
                    inputFile_, particleSpecs_,
                    eventPartitions_, entryBoundsByWorker_,
                    baseDir, shardTempDir_);
                ownsShards_ = true;
            }

            if (!queueCapacityUser_)
                queueCapacity_ = std::max<std::size_t>(threadCount_, 10 * threadCount_);

            configured_ = true;
        }

        void setCallbackMode(CallbackMode mode) { callbackMode_ = mode; }

        void setQueueCapacity(std::size_t capacity) {
            queueCapacity_     = capacity;
            queueCapacityUser_ = capacity > 0;
        }

        const std::string& inputFile()    const { return inputFile_; }
        std::size_t threadCount()         const { return threadCount_; }
        std::size_t eventCount()          const { return eventCount_; }
        StreamType  streamType()          const { return streamType_; }
        const std::vector<std::string>& inputShards() const { return inputShards_; }
        const std::string& shardTempDir() const { return shardTempDir_; }

        std::string stats() const {
            std::lock_guard<std::mutex> lock(queueMutex_);

            std::ostringstream out;
            out << "ProbeParallel{"
                << "streamType=" << streamTypeName(streamType_)
                << ", callbackMode=" << callbackModeName(callbackMode_)
                << ", threadCount=" << threadCount_
                << ", activeWorkers=" << eventPartitions_.size()
                << ", eventCount=" << eventCount_
                << ", queueCapacity=" << queueCapacity_
                << ", produced=" << produced_
                << ", consumed=" << consumed_
                << ", progress=[";
            for (std::size_t i = 0; i < progress_.size(); ++i) {
                if (i) out << ',';
                out << progress_[i];
            }
            out << "]}";
            return out.str();
        }

        template<typename Callback>
        void run(Callback&& callback) {
            if (!configured_)
                throw std::runtime_error("[Probe] ProbeParallel::run called before configureProbe");
            if (eventPartitions_.empty()) return;

            BranchControl::enableRootThreadSafety();
            resetRuntimeState();

            if (callbackMode_ == CallbackMode::WorkerThread) {
                runWorkerThread(callback);
                return;
            }

            if (streamType_ == StreamType::Vectors)
                throw std::runtime_error(
                    "[Probe] ProbeParallel: CollectorThread mode for vector streams is not implemented");

            runCollectorThread(callback);
        }

      private:
        static const char* streamTypeName(StreamType type) {
            switch (type) {
                case StreamType::Unset:   return "Unset";
                case StreamType::Events:  return "Events";
                case StreamType::Vectors: return "Vectors";
            }
            return "Unknown";
        }

        static const char* callbackModeName(CallbackMode mode) {
            switch (mode) {
                case CallbackMode::WorkerThread:     return "WorkerThread";
                case CallbackMode::CollectorThread:  return "CollectorThread";
            }
            return "Unknown";
        }

        void determineStreamType() {
            bool anyFlat = false;
            bool anyVec  = false;
            for (const auto& spec : particleSpecs_) {
                if (spec.indexBranches.empty()) anyVec  = true;
                else                            anyFlat = true;
            }

            if (anyFlat && anyVec)
                throw std::runtime_error("[Probe] ProbeParallel: cannot mix indexed and vector particle specs");

            streamType_ = anyVec ? StreamType::Vectors : StreamType::Events;
        }

        void buildIndexSpecs() {
            indexSpecs_.clear();
            indexSpecs_.reserve(particleSpecs_.size());
            for (const auto& spec : particleSpecs_) {
                if (spec.indexBranches.empty()) continue;
                indexSpecs_.push_back(IndexSpec{
                    spec.indexBranches[0],
                    IndexOrdering::Ascending,
                    true,
                    true
                });
            }
        }

        std::vector<Long64_t> scanFlatEventKeys() const {
            std::unique_ptr<TFile> file(TFile::Open(inputFile_.c_str(), "READ"));
            if (!file || file->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + inputFile_ + "'");

            std::set<Long64_t> keySet;
            for (const auto& spec : particleSpecs_) {
                if (!spec.indexBranches.empty())
                    BranchControl::scanIndexBranch(
                        file.get(), spec.tree, spec.indexBranches[0].name, keySet, inputFile_);
            }
            return {keySet.begin(), keySet.end()};
        }

        std::size_t vectorEntryCount() const {
            std::unique_ptr<TFile> file(TFile::Open(inputFile_.c_str(), "READ"));
            if (!file || file->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + inputFile_ + "'");

            TTree* tree = dynamic_cast<TTree*>(file->Get(particleSpecs_[0].tree.c_str()));
            if (!tree) return 0;
            return static_cast<std::size_t>(std::max<Long64_t>(0, tree->GetEntries()));
        }

        static std::vector<BranchControl::Partition>
        partitionDenseRange(Long64_t first, Long64_t last, std::size_t n) {
            std::vector<BranchControl::Partition> parts;
            if (n == 0 || first > last) return parts;

            const Long64_t total = last - first + 1;
            const Long64_t chunk = (total + static_cast<Long64_t>(n) - 1)
                                 / static_cast<Long64_t>(n);
            for (Long64_t start = first; start <= last; start += chunk)
                parts.push_back({start, std::min(last, start + chunk - 1)});
            return parts;
        }

        void prepareEventPartitions(const std::vector<Long64_t>& bruteKeys) {
            if (streamType_ == StreamType::Vectors) {
                eventRange_ = {0, static_cast<Long64_t>(eventCount_) - 1};
                eventPartitions_ = partitionDenseRange(eventRange_.first, eventRange_.last, threadCount_);
                return;
            }

            if (!bruteKeys.empty()) {
                eventRange_ = {bruteKeys.front(), bruteKeys.back()};
                eventPartitions_ = BranchControl::partitionEvents(bruteKeys, threadCount_);
                return;
            }

            const Long64_t first = BranchControl::probeFirstKey(inputFile_, particleSpecs_);
            const Long64_t last  = first + static_cast<Long64_t>(eventCount_) - 1;
            eventRange_ = {first, last};
            eventPartitions_ = partitionDenseRange(first, last, threadCount_);
        }

        static Long64_t indexValue(BranchType type, Long64_t longValue, Int_t intValue) {
            return type == BranchType::Int64 ? longValue : static_cast<Long64_t>(intValue);
        }

        void prepareEntryBounds() {
            entryBoundsByWorker_.clear();
            if (streamType_ != StreamType::Events || eventPartitions_.empty()) return;

            entryBoundsByWorker_.assign(
                eventPartitions_.size(), std::vector<Bounds>(particleSpecs_.size()));

            std::unique_ptr<TFile> file(TFile::Open(inputFile_.c_str(), "READ"));
            if (!file || file->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + inputFile_ + "'");

            for (std::size_t p = 0; p < particleSpecs_.size(); ++p) {
                const auto& spec = particleSpecs_[p];
                if (spec.indexBranches.empty()) continue;

                TTree* tree = dynamic_cast<TTree*>(file->Get(spec.tree.c_str()));
                if (!tree)
                    throw std::runtime_error(
                        "[Probe] Missing tree '" + spec.tree + "' in file '" + inputFile_ + "'");

                const std::string& idxName = spec.indexBranches[0].name;
                TBranch* branch = BranchControl::requireBranch(tree, idxName, inputFile_);
                const BranchType type = BranchControl::detectType(branch);
                if (type != BranchType::Int32 && type != BranchType::Int64 && type != BranchType::UInt32)
                    throw std::runtime_error(
                        "[Probe] Index branch '" + idxName + "' in tree '" + spec.tree +
                        "' of file '" + inputFile_ + "': must be Int_t, UInt_t, or Long64_t");

                tree->SetBranchStatus("*", 0);
                tree->SetBranchStatus(idxName.c_str(), 1);

                Long64_t longValue = 0;
                Int_t    intValue  = 0;
                if (type == BranchType::Int64) tree->SetBranchAddress(idxName.c_str(), &longValue);
                else                           tree->SetBranchAddress(idxName.c_str(), &intValue);

                const Long64_t entries = tree->GetEntries();
                std::size_t part = 0;
                bool havePrevious = false;
                Long64_t previous = 0;

                for (Long64_t row = 0; row < entries && part < eventPartitions_.size(); ++row) {
                    tree->GetEntry(row);
                    const Long64_t value = indexValue(type, longValue, intValue);

                    if (havePrevious && value < previous) {
                        tree->ResetBranchAddresses();
                        throw std::runtime_error(
                            "[Probe] Index branch '" + idxName + "' in tree '" + spec.tree +
                            "' is not ascending; CollectorThread event bounds require grouped ascending data");
                    }
                    havePrevious = true;
                    previous = value;

                    while (part < eventPartitions_.size()
                        && value > eventPartitions_[part].lastEvent)
                        ++part;

                    if (part >= eventPartitions_.size()) break;
                    if (value < eventPartitions_[part].firstEvent) continue;

                    Bounds& bounds = entryBoundsByWorker_[part][p];
                    if (!bounds.valid()) bounds.first = row;
                    bounds.last = row;
                }

                tree->ResetBranchAddresses();
            }
        }

        std::size_t eventsInPartition(const BranchControl::Partition& part) const {
            if (part.lastEvent < part.firstEvent) return 0;
            return static_cast<std::size_t>(part.lastEvent - part.firstEvent + 1);
        }

        void resetRuntimeState() {
            stopRequested_.store(false, std::memory_order_release);
            workersFinished_ = 0;
            produced_ = 0;
            consumed_ = 0;
            progress_.assign(eventPartitions_.size(), 0);
            queue_.clear();
        }

        void requestStop() {
            stopRequested_.store(true, std::memory_order_release);
            queueNotEmpty_.notify_all();
            queueNotFull_.notify_all();
        }

        bool pushQueuedEvent(QueuedEvent event) {
            std::unique_lock<std::mutex> lock(queueMutex_);
            queueNotFull_.wait(lock, [&] {
                return stopRequested_.load(std::memory_order_acquire)
                    || queue_.size() < queueCapacity_;
            });

            if (stopRequested_.load(std::memory_order_acquire)) return false;

            const std::size_t worker = event.workerIndex;
            queue_.push_back(std::move(event));
            ++produced_;
            if (worker < progress_.size()) ++progress_[worker];

            lock.unlock();
            queueNotEmpty_.notify_one();
            return true;
        }

        bool popQueuedEvent(QueuedEvent& event) {
            std::unique_lock<std::mutex> lock(queueMutex_);
            queueNotEmpty_.wait(lock, [&] {
                return stopRequested_.load(std::memory_order_acquire)
                    || !queue_.empty()
                    || workersFinished_ >= eventPartitions_.size();
            });

            if (queue_.empty()) return false;

            event = std::move(queue_.front());
            queue_.pop_front();
            ++consumed_;

            lock.unlock();
            queueNotFull_.notify_one();
            return true;
        }

        void markWorkerFinished() {
            {
                std::lock_guard<std::mutex> lock(queueMutex_);
                ++workersFinished_;
            }
            queueNotEmpty_.notify_all();
        }

        template<typename Callback>
        void runWorkerThread(Callback& callback) {
            std::vector<std::thread> workers;
            std::vector<std::exception_ptr> errors(eventPartitions_.size());
            workers.reserve(eventPartitions_.size());

            const bool useShards = !inputShards_.empty();

            for (std::size_t t = 0; t < eventPartitions_.size(); ++t) {
                workers.emplace_back([&, t] {
                    try {
                        const auto& part = eventPartitions_[t];
                        if (useShards) {
                            // Each shard contains exactly this worker's key range
                            // starting at entry 0 — no pre-computed bounds needed.
                            EventStream stream(inputShards_[t], particleSpecs_,
                                               part.firstEvent, part.lastEvent,
                                               eventsInPartition(part));
                            while (stream.next()) {
                                if (t < progress_.size()) ++progress_[t];
                                callback(stream.event(), static_cast<int>(t));
                            }
                        } else {
                            const auto& bounds = entryBoundsByWorker_.empty()
                                               ? emptyBounds_
                                               : entryBoundsByWorker_[t];
                            EventStream stream(inputFile_, particleSpecs_,
                                               part.firstEvent, part.lastEvent,
                                               eventsInPartition(part), bounds);
                            while (stream.next()) {
                                if (t < progress_.size()) ++progress_[t];
                                callback(stream.event(), static_cast<int>(t));
                            }
                        }
                    } catch (...) {
                        errors[t] = std::current_exception();
                    }
                });
            }

            for (auto& worker : workers) worker.join();
            for (const auto& error : errors)
                if (error) std::rethrow_exception(error);
        }

        template<typename Callback>
        void runCollectorThread(Callback& callback) {
            std::vector<std::thread> workers;
            std::vector<std::exception_ptr> workerErrors(eventPartitions_.size());
            std::exception_ptr collectorError;

            workers.reserve(eventPartitions_.size());

            std::thread collector([&] {
                try {
                    QueuedEvent queued;
                    while (popQueuedEvent(queued)) {
                        callback(queued.event, static_cast<int>(queued.workerIndex));
                        queued = QueuedEvent{};
                    }
                } catch (...) {
                    collectorError = std::current_exception();
                    requestStop();
                }
            });

            const bool useShards = !inputShards_.empty();

            for (std::size_t t = 0; t < eventPartitions_.size(); ++t) {
                workers.emplace_back([&, t] {
                    try {
                        const auto& part = eventPartitions_[t];

                        // Construct the right EventStream depending on whether
                        // shards are available.  Shard path → no pre-computed
                        // entry bounds (shard contains exactly this range from
                        // entry 0).  Original file → use pre-computed bounds.
                        std::unique_ptr<EventStream> stream;
                        if (useShards) {
                            stream = std::make_unique<EventStream>(
                                inputShards_[t], particleSpecs_,
                                part.firstEvent, part.lastEvent,
                                eventsInPartition(part));
                        } else {
                            const auto& bounds = entryBoundsByWorker_.empty()
                                               ? emptyBounds_
                                               : entryBoundsByWorker_[t];
                            stream = std::make_unique<EventStream>(
                                inputFile_, particleSpecs_,
                                part.firstEvent, part.lastEvent,
                                eventsInPartition(part), bounds);
                        }

                        while (!stopRequested_.load(std::memory_order_acquire)
                               && stream->next())
                        {
                            QueuedEvent queued{
                                t,
                                stream->event().index,
                                stream->takeEvent()
                            };
                            if (!pushQueuedEvent(std::move(queued))) break;
                        }
                    } catch (...) {
                        workerErrors[t] = std::current_exception();
                        requestStop();
                    }
                    markWorkerFinished();
                });
            }

            for (auto& worker : workers) worker.join();
            queueNotEmpty_.notify_all();
            if (collector.joinable()) collector.join();

            if (collectorError) std::rethrow_exception(collectorError);
            for (const auto& error : workerErrors)
                if (error) std::rethrow_exception(error);
        }

        // ── cleanup ───────────────────────────────────────────────────────────
        // Called by the destructor.  Removes shardTempDir_ if we own the shards
        // and the user did not request persistence (keep_shards = false).
        void cleanupShards() {
            if (ownsShards_ && !keepShards_ && !shardTempDir_.empty())
                Splitter::removeShardDir(shardTempDir_);
        }

        bool configured_ = false;

        std::string inputFile_;
        std::vector<ParticleSpec> particleSpecs_;
        std::vector<IndexSpec> indexSpecs_;

        // ── Phase 1 shard state ───────────────────────────────────────────────
        std::vector<std::string> inputShards_;   // one path per partition
        bool        ownsShards_   = false;       // true when shards were created/adopted
        std::string shardTempDir_;               // directory containing the shards
        bool        keepShards_   = false;       // mirrors [probe].keep_shards

        StreamType streamType_ = StreamType::Unset;
        CallbackMode callbackMode_ = CallbackMode::CollectorThread;

        std::size_t threadCount_ = 0;
        std::size_t eventCount_ = 0;
        Bounds eventRange_;
        std::vector<BranchControl::Partition> eventPartitions_;
        std::vector<std::vector<Bounds>> entryBoundsByWorker_;

        std::size_t queueCapacity_ = 0;
        bool queueCapacityUser_ = false;

        mutable std::mutex queueMutex_;
        std::condition_variable queueNotEmpty_;
        std::condition_variable queueNotFull_;
        std::deque<QueuedEvent> queue_;
        std::atomic<bool> stopRequested_{false};
        std::size_t workersFinished_ = 0;
        std::size_t produced_ = 0;
        std::size_t consumed_ = 0;
        std::vector<std::size_t> progress_;
        const std::vector<Bounds> emptyBounds_{};
    };

        // Compatibility shim for older call sites. New code should configure and run
    // ProbeParallel directly so callback mode and execution stats are explicit.
    template<typename Callback>
    inline void runParallel(const std::string& filepath,
                            const std::vector<CollectionSpec>& collections,
                            Callback&& callback,
                            std::size_t nThreads = 0,
                            std::size_t nEventsHint = 0)
    {
        ProbeParallel probe;
        probe.setCallbackMode(CallbackMode::WorkerThread);
        probe.configureProbe(filepath, collections, nThreads, nEventsHint, nEventsHint > 0);
        probe.run(std::forward<Callback>(callback));
    }

} // namespace Probe
