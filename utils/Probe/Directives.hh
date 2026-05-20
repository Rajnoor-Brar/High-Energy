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

template<typename Callback>
inline void ProbeParallel::run(Callback&& callback) {
    if (!configured_)
        throw std::runtime_error("[Probe] ProbeParallel::run called before configureProbe");
    if (eventPartitions_.empty()) return;

    BranchControl::enableRootThreadSafety();
    resetRuntimeState();

    if (callbackMode_ == CallbackMode::WorkerThread) {
        runWorkerThread(callback);
        return;
    }

    runCollectorThread(callback);
}

template<typename Callback>
inline void ProbeParallel::runWorkerThread(Callback& callback) {
    std::vector<std::thread> workers;
    std::vector<std::exception_ptr> errors(eventPartitions_.size());
    workers.reserve(eventPartitions_.size());

    for (std::size_t t = 0; t < eventPartitions_.size(); ++t) {
        workers.emplace_back([&, t] {
            try {
                const auto& part = eventPartitions_[t];
                static const std::vector<Bounds> kNoBounds;
                const auto& bounds = entryBoundsByWorker_.empty()
                                   ? kNoBounds
                                   : entryBoundsByWorker_[t];
                EventStream stream(inputFile_, particleSpecs_,
                                   part.firstEvent, part.lastEvent,
                                   eventsInPartition(part), bounds);
                for (;;) {
                    bool _cont;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.EventStream.next"); _cont = stream.next(); }
                    if (!_cont) break;
                    if (t < progress_.size()) ++progress_[t];
                    callback(stream.event(), static_cast<int>(t));
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
inline void ProbeParallel::runCollectorThread(Callback& callback) {
    std::vector<std::thread> workers;
    std::vector<std::exception_ptr> workerErrors(eventPartitions_.size());
    workers.reserve(eventPartitions_.size());

    // docs/WriterMT.md Phase 5+: N collector threads drain the shared queue.
    const std::size_t nCollectors = analysisThreadCount();
    std::vector<std::thread> collectors;
    std::vector<std::exception_ptr> collectorErrors(nCollectors);
    collectors.reserve(nCollectors);

    for (std::size_t c = 0; c < nCollectors; ++c) {
        collectors.emplace_back([&, c] {
            try {
                QueuedEvent queued;
                for (;;) {
                    bool _got;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.queue.pop_wait"); _got = popQueuedEvent(queued); }
                    if (!_got) break;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.collector.callback"); callback(queued.event, static_cast<int>(c)); }
                    queued = QueuedEvent{};
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
                                   ? kNoBounds
                                   : entryBoundsByWorker_[t];
                EventStream stream(inputFile_, particleSpecs_,
                                   part.firstEvent, part.lastEvent,
                                   eventsInPartition(part), bounds);
                for (;;) {
                    if (stopRequested_.load(std::memory_order_acquire)) break;
                    bool _cont;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.EventStream.next"); _cont = stream.next(); }
                    if (!_cont) break;
                    QueuedEvent queued{t, stream.event().index, stream.takeEvent()};
                    bool _pushed;
                    { MONITOR_SCOPE_TIMER("ProbeParallel.queue.push_wait"); _pushed = pushQueuedEvent(std::move(queued)); }
                    if (!_pushed) break;
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
                        ev.particles[specs_[p].label] = std::move(buffer[i][p]);
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
