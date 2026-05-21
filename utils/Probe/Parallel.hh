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

    // ProbeParallel — multi-threaded ROOT reader; Event/Feed/Mixed streaming.
    // See docs/ProbeStream.md for the full bucket-split design and TOML format.
    class ProbeParallel {
      public:
        ProbeParallel();
        ~ProbeParallel();

        // ProbeConfig-based configure (Phase 7+).
        void configureProbe(std::string inputFile,
                            ProbeConfig config,
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
        ActiveMode  activeMode() const;
        std::string stats() const;

        // streamEvents — Event-only; callback signature: void(const Event&, int tid)
        template<typename EventCallback>
        void streamEvents(EventCallback&& ce);

        // streamFeed — Feed-only; callback signature: void(const Feed&, int tid)
        template<typename FeedCallback>
        void streamFeed(FeedCallback&& cf);

        // stream — Mixed mode; both callbacks fired per frame.
        template<typename EventCallback, typename FeedCallback>
        void stream(EventCallback&& ce, FeedCallback&& cf);

      private:
        static const char* callbackModeName(CallbackMode mode);
        void determineStreamType();   // internal: used by legacy configureProbe path
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
        bool pushQueuedFrame(QueuedFrame frame);
        bool popQueuedFrame(QueuedFrame& frame);
        void markWorkerFinished();

        template<typename EventCallback, typename FeedCallback>
        void runWorkerThread(EventCallback& ce, FeedCallback& cf);

        template<typename EventCallback, typename FeedCallback>
        void runCollectorThread(EventCallback& ce, FeedCallback& cf);

        bool configured_ = false;

        std::string inputFile_;
        ProbeConfig config_;

        StreamType   streamType_   = StreamType::Unset;  // used by determineStreamType; not public
        ActiveMode   activeMode_   = ActiveMode::Events;
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
        std::deque<QueuedFrame> queue_;
        std::atomic<bool> stopRequested_{false};
        std::size_t workersFinished_ = 0;
        std::size_t produced_ = 0;
        std::size_t consumed_ = 0;
        std::vector<std::atomic<std::size_t>> progress_;
    };

} // namespace Probe
