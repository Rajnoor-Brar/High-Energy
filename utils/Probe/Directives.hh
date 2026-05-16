#pragma once

#include <chrono>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <thread>
#include <utility>
#include <vector>

#include "TROOT.h"

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

    if (streamType_ == StreamType::Vectors)
        throw std::runtime_error(
            "[Probe] ProbeParallel: CollectorThread mode for vector streams is not implemented");

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
                while (stream.next()) {
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
                while (popQueuedEvent(queued)) {
                    callback(queued.event, static_cast<int>(c));
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
                while (!stopRequested_.load(std::memory_order_acquire)
                       && stream.next())
                {
                    QueuedEvent queued{
                        t,
                        stream.event().index,
                        stream.takeEvent()
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

    using clk = std::chrono::steady_clock;
    const auto t0 = clk::now();

    BufferT buffer(eventCount_,
                   std::vector<std::vector<Lorentz>>(specs_.size()));

    const auto t1 = clk::now();

    for (std::size_t p = 0; p < specs_.size(); ++p)
        readSpecInto(specs_[p], p, buffer);

    const auto t2 = clk::now();

    flushParallel(buffer, std::forward<Callback>(callback));

    const auto t3 = clk::now();

    auto ms = [](auto a, auto b) {
        return std::chrono::duration_cast<std::chrono::milliseconds>(b - a).count();
    };
    std::cerr << "[Probe::IMT] timing (ms): allocate=" << ms(t0, t1)
              << " read=" << ms(t1, t2)
              << " flush=" << ms(t2, t3)
              << " total=" << ms(t0, t3)
              << " (eventCount=" << eventCount_
              << ", threads=" << threadCount_ << ")\n";
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
