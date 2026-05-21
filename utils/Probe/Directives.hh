#pragma once

#include <chrono>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

#include "TROOT.h"

#include "Monitor/Timer.hh"
#include "Probe/Administration.hh"
#include "Probe/Methods.hh"
#include "Probe/Parallel.hh"
#include "Probe/ParallelIMT.hh"
#include "Probe/Readers.hh"

namespace Probe {

namespace detail {

    struct StreamPair {
        std::unique_ptr<EventStream> evStream;
        std::unique_ptr<FeedStream>  fdStream;
    };

    // Constructs the event/feed streams for one worker partition.
    inline StreamPair buildStreams(
        const std::string&              inputFile,
        const ProbeConfig&              config,
        const BranchControl::Partition& part,
        std::size_t                     nEvents,
        const std::vector<Bounds>&      bounds,
        bool hasEventData,
        bool hasFeedData)
    {
        StreamPair sp;
        if (hasEventData)
            sp.evStream = std::make_unique<EventStream>(inputFile, config,
                              part.firstEvent, part.lastEvent, nEvents, bounds);
        if (hasFeedData)
            sp.fdStream = std::make_unique<FeedStream>(inputFile, config,
                              part.firstEvent, part.lastEvent);
        return sp;
    }

} // namespace detail

// ── Streaming methods ─────────────────────────────────────────────────────────

template<typename EventCallback>
inline void ProbeParallel::streamEvents(EventCallback&& ce) {
    auto noopFeed = [](const Feed&, int){};
    if (!configured_)
        throw std::runtime_error("[Probe] ProbeParallel::streamEvents called before configureProbe");
    if (activeMode_ == ActiveMode::Feed)
        throw std::runtime_error(
            "[Probe] streamEvents called on a Feed-only config; use streamFeed or stream");
    if (eventPartitions_.empty()) return;
    BranchControl::enableRootThreadSafety();
    resetRuntimeState();
    if (callbackMode_ == CallbackMode::WorkerThread) { runWorkerThread(ce, noopFeed); return; }
    runCollectorThread(ce, noopFeed);
}

template<typename FeedCallback>
inline void ProbeParallel::streamFeed(FeedCallback&& cf) {
    auto noopEvent = [](const Event&, int){};
    if (!configured_)
        throw std::runtime_error("[Probe] ProbeParallel::streamFeed called before configureProbe");
    if (activeMode_ == ActiveMode::Events)
        throw std::runtime_error(
            "[Probe] streamFeed called on an Events-only config; use streamEvents or stream");
    if (eventPartitions_.empty()) return;
    BranchControl::enableRootThreadSafety();
    resetRuntimeState();
    if (callbackMode_ == CallbackMode::WorkerThread) { runWorkerThread(noopEvent, cf); return; }
    runCollectorThread(noopEvent, cf);
}

template<typename EventCallback, typename FeedCallback>
inline void ProbeParallel::stream(EventCallback&& ce, FeedCallback&& cf) {
    if (!configured_)
        throw std::runtime_error("[Probe] ProbeParallel::stream called before configureProbe");
    if (eventPartitions_.empty()) return;
    BranchControl::enableRootThreadSafety();
    resetRuntimeState();
    if (callbackMode_ == CallbackMode::WorkerThread) { runWorkerThread(ce, cf); return; }
    runCollectorThread(ce, cf);
}

// ── Two-callback worker/collector implementations ────────────────────────────

template<typename EventCallback, typename FeedCallback>
inline void ProbeParallel::runWorkerThread(EventCallback& ce, FeedCallback& cf) {
    std::vector<std::thread> workers;
    std::vector<std::exception_ptr> errors(eventPartitions_.size());
    workers.reserve(eventPartitions_.size());

    const bool hasEventData = (activeMode_ == ActiveMode::Events || activeMode_ == ActiveMode::Mixed);
    const bool hasFeedData  = (activeMode_ == ActiveMode::Feed   || activeMode_ == ActiveMode::Mixed);

    for (std::size_t t = 0; t < eventPartitions_.size(); ++t) {
        workers.emplace_back([&, t] {
            try {
                const auto& part = eventPartitions_[t];
                static const std::vector<Bounds> kNoBounds;
                const auto& bounds = entryBoundsByWorker_.empty()
                                   ? kNoBounds : entryBoundsByWorker_[t];
                auto [evStream, fdStream] = detail::buildStreams(
                    inputFile_, config_,
                    part, eventsInPartition(part), bounds,
                    hasEventData, hasFeedData);

                for (;;) {
                    bool contE = false;
                    bool contF = false;
                    if (hasEventData && evStream) {
                        MONITOR_SCOPE_TIMER("ProbeParallel.EventStream.next");
                        contE = evStream->next();
                    }
                    if (hasFeedData && fdStream) {
                        contF = fdStream->next();
                    }
                    if (!contE && !contF) break;
                    if (!contE && hasEventData) break;   // streams exhausted together

                    if (t < progress_.size()) ++progress_[t];
                    if (hasEventData && evStream) ce(evStream->event(), static_cast<int>(t));
                    if (hasFeedData  && fdStream) cf(fdStream->current(), static_cast<int>(t));
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

template<typename EventCallback, typename FeedCallback>
inline void ProbeParallel::runCollectorThread(EventCallback& ce, FeedCallback& cf) {
    std::vector<std::thread> workers;
    std::vector<std::exception_ptr> workerErrors(eventPartitions_.size());
    workers.reserve(eventPartitions_.size());

    const std::size_t nCollectors = analysisThreadCount();
    std::vector<std::thread> collectors;
    std::vector<std::exception_ptr> collectorErrors(nCollectors);
    collectors.reserve(nCollectors);

    const bool hasEventData = (activeMode_ == ActiveMode::Events || activeMode_ == ActiveMode::Mixed);
    const bool hasFeedData  = (activeMode_ == ActiveMode::Feed   || activeMode_ == ActiveMode::Mixed);

    for (std::size_t c = 0; c < nCollectors; ++c) {
        collectors.emplace_back([&, c] {
            try {
                QueuedFrame frame;
                for (;;) {
                    bool got;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.queue.pop_wait"); got = popQueuedFrame(frame); }
                    if (!got) break;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.collector.callback");
                      if (hasEventData) ce(frame.event, static_cast<int>(c));
                      if (hasFeedData)  cf(frame.feed,  static_cast<int>(c)); }
                    frame = QueuedFrame{};
                }
            } catch (...) {
                collectorErrors[c] = std::current_exception();
                requestStop();
            }
        });
    }

    for (std::size_t t = 0; t < eventPartitions_.size(); ++t) {
        workers.emplace_back([&, t] {
            try {
                const auto& part = eventPartitions_[t];
                static const std::vector<Bounds> kNoBounds;
                const auto& bounds = entryBoundsByWorker_.empty()
                                   ? kNoBounds : entryBoundsByWorker_[t];
                auto [evStream, fdStream] = detail::buildStreams(
                    inputFile_, config_,
                    part, eventsInPartition(part), bounds,
                    hasEventData, hasFeedData);

                for (;;) {
                    if (stopRequested_.load(std::memory_order_acquire)) break;

                    // Default true: a missing stream is treated as "still running"
                    // so the active stream drives iteration. runWorkerThread uses
                    // false instead because it drives both streams directly.
                    bool contE = true, contF = true;
                    if (hasEventData && evStream) {
                        MONITOR_SCOPE_TIMER("ProbeParallel.EventStream.next");
                        contE = evStream->next();
                    }
                    if (hasFeedData && fdStream) contF = fdStream->next();
                    if (!contE && !contF) break;
                    if (!contE && hasEventData) break;

                    QueuedFrame frame;
                    frame.workerIndex = t;
                    if (hasEventData && evStream) {
                        frame.eventIndex = evStream->event().index;
                        frame.event      = evStream->takeEvent();
                    }
                    if (hasFeedData && fdStream)
                        frame.feed = fdStream->takeCurrent();

                    bool pushed;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.queue.push_wait"); pushed = pushQueuedFrame(std::move(frame)); }
                    if (!pushed) break;
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
    for (auto& collector : collectors)
        if (collector.joinable()) collector.join();

    for (const auto& error : collectorErrors)
        if (error) std::rethrow_exception(error);
    for (const auto& error : workerErrors)
        if (error) std::rethrow_exception(error);
}

template<typename Callback>
inline void ProbeIMT::run(Callback&& callback) {
    if (!configured_)
        throw std::runtime_error("[Probe::IMT] run() before configureProbe");
    if (eventCount_ == 0) return;

    ROOT::EnableImplicitMT(static_cast<UInt_t>(threadCount_));
    consumed_ = 0;

    BufferT buffer;
    { MONITOR_SCOPE_TIMER("ProbeIMT.allocate"); buffer.assign(eventCount_, std::vector<std::vector<Lorentz>>(specs_.size())); }
    { MONITOR_SCOPE_TIMER("ProbeIMT.read");     for (std::size_t p = 0; p < specs_.size(); ++p) readSpecInto(specs_[p], p, buffer); }
    { MONITOR_SCOPE_TIMER("ProbeIMT.flush");    flushParallel(buffer, std::forward<Callback>(callback)); }
}

template<typename Callback>
inline void ProbeIMT::flushParallel(BufferT& buffer, Callback&& callback) {
    const std::size_t T = threadCount_;
    std::vector<std::thread> workers;
    std::vector<std::exception_ptr> errors(T);
    workers.reserve(T);

    for (std::size_t t = 0; t < T; ++t) {
        workers.emplace_back([&, t] {
            try {
                const std::size_t start = (t * eventCount_) / T;
                const std::size_t end = ((t + 1) * eventCount_) / T;
                for (std::size_t i = start; i < end; ++i) {
                    Event ev;
                    ev.index = firstEventKey_ + Long64_t(i);
                    for (std::size_t p = 0; p < specs_.size(); ++p)
                        ev.particle[specs_[p].label] = std::move(buffer[i][p]);
                    callback(ev, static_cast<int>(t));
                    consumed_.fetch_add(1, std::memory_order_relaxed);
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

} // namespace Probe
