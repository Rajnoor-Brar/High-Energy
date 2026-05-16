#pragma once

#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <exception>
#include <mutex>
#include <string>
#include <vector>

#include "Probe/BranchControl.hh"
#include "Probe/Types.hh"

namespace Probe {

    class ProbeParallel {
      public:
        ProbeParallel();
        ~ProbeParallel();

        void configureProbe(std::string inputFile,
                            std::vector<CollectionSpec> particleSpecs,
                            std::size_t threadCount,
                            std::size_t requestedEvents,
                            bool userRequestedEvents);
        void setCallbackMode(CallbackMode mode);
        void setQueueCapacity(std::size_t capacity);
        void setAnalysisThreadCount(std::size_t n);

        const std::string& inputFile() const;
        std::size_t threadCount() const;
        std::size_t analysisThreadCount() const;
        std::size_t eventCount() const;
        StreamType streamType() const;
        std::string stats() const;

        template<typename Callback>
        void run(Callback&& callback);

      private:
        static const char* streamTypeName(StreamType type);
        static const char* callbackModeName(CallbackMode mode);
        void determineStreamType();
        std::vector<Long64_t> scanFlatEventKeys() const;
        std::size_t vectorEntryCount() const;
        static std::vector<BranchControl::Partition>
        partitionDenseRange(Long64_t first, Long64_t last, std::size_t n);
        void prepareEventPartitions(const std::vector<Long64_t>& bruteKeys);
        static Long64_t indexValue(BranchType type, Long64_t longValue, Int_t intValue);
        void prepareEntryBounds();
        std::size_t eventsInPartition(const BranchControl::Partition& part) const;
        void resetRuntimeState();
        void requestStop();
        bool pushQueuedEvent(QueuedEvent event);
        bool popQueuedEvent(QueuedEvent& event);
        void markWorkerFinished();

        template<typename Callback>
        void runWorkerThread(Callback& callback);

        template<typename Callback>
        void runCollectorThread(Callback& callback);

        bool configured_ = false;

        std::string inputFile_;
        std::vector<CollectionSpec> particleSpecs_;

        StreamType streamType_ = StreamType::Unset;
        CallbackMode callbackMode_ = CallbackMode::CollectorThread;

        std::size_t threadCount_         = 0;
        std::size_t analysisThreadCount_ = 0;
        std::size_t eventCount_          = 0;
        Bounds eventRange_;
        std::vector<BranchControl::Partition> eventPartitions_;
        std::vector<std::vector<Bounds>> entryBoundsByWorker_;

        std::size_t queueCapacity_ = 0;

        mutable std::mutex queueMutex_;
        std::condition_variable queueNotEmpty_;
        std::condition_variable queueNotFull_;
        std::deque<QueuedEvent> queue_;
        std::atomic<bool> stopRequested_{false};
        std::size_t workersFinished_ = 0;
        std::size_t produced_ = 0;
        std::size_t consumed_ = 0;
        std::vector<std::atomic<std::size_t>> progress_;
    };

} // namespace Probe
