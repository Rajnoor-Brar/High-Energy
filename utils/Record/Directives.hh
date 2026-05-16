#pragma once

#include "Record/Writer.hh"

namespace Record {

inline void Writer::throwIfCannotAcceptLocked() const {
        if (!started_.load(std::memory_order_acquire))
            throw std::runtime_error("[Record::Writer] fill/checkpoint called before start()");
        if (!accepting_.load(std::memory_order_acquire))
            throw std::runtime_error("[Record::Writer] writer is no longer accepting requests");
        if (writerException_) std::rethrow_exception(writerException_);
    }

template <typename Payload>
inline void Writer::pushFill(Payload&& payload) {
        std::unique_lock<std::mutex> lock(fillMutex_);
        throwIfCannotAcceptLocked();
        fillNotFull_.wait(lock, [&] {
            return !accepting_.load(std::memory_order_acquire)
                || writerException_
                || fillQueue_.size() < queueCapacity_;
        });
        throwIfCannotAcceptLocked();
        fillQueue_.emplace_back(std::forward<Payload>(payload));
        ++produced_;
        if (fillQueue_.size() > maxBacklog_) maxBacklog_ = fillQueue_.size();
        lock.unlock();
        fillNotEmpty_.notify_one();
    }

// Watch sink — invoked by AsyncLogger and by finish()/fatalWrite()/
// checkpoint() public methods. Pushes onto watchQueue_; the watchdog
// thread drains it.
inline void Writer::signalWatchInternal(WatchRequest req) {
        {
            std::lock_guard<std::mutex> lock(watchMutex_);
            watchQueue_.push_back(std::move(req));
        }
        watchCv_.notify_one();
    }

// Each worker has a stable workerIdx in [0, nRecordThreads_). Pops
// FillRequest from the shared queue; visits the variant to dispatch
// into apply*(). Honors the quiesce protocol between requests.
inline void Writer::workerLoop(int workerIdx) {
        while (true) {
            if (quiesceRequested_.load(std::memory_order_acquire)) {
                arriveAtQuiesce();
                continue;
            }

            FillRequest req;
            bool gotOne = false;

            {
                std::unique_lock<std::mutex> lock(fillMutex_);
                fillNotEmpty_.wait(lock, [&] {
                    return stopRequested_.load(std::memory_order_acquire)
                        || quiesceRequested_.load(std::memory_order_acquire)
                        || !fillQueue_.empty();
                });

                if (!fillQueue_.empty()) {
                    req = std::move(fillQueue_.front());
                    fillQueue_.pop_front();
                    ++consumed_;
                    gotOne = true;
                }
            }

            if (gotOne) fillNotFull_.notify_one();

            if (!gotOne) {
                if (stopRequested_.load(std::memory_order_acquire)) return;
                continue;  // woke for quiesce; re-check top of loop
            }

            try {
                std::visit([&](auto& r) {
                    using T = std::decay_t<decltype(r)>;
                    if      constexpr (std::is_same_v<T, ParticleRequest>) applyParticleRequest(r, workerIdx);
                    else if constexpr (std::is_same_v<T, Hist1DRequest>)   applyHist1DRequest(r, workerIdx);
                    else if constexpr (std::is_same_v<T, Hist2DRequest>)   applyHist2DRequest(r, workerIdx);
                    else if constexpr (std::is_same_v<T, GraphRequest>)    applyGraphRequest(r, workerIdx);
                    else if constexpr (std::is_same_v<T, ProfileRequest>)  applyProfileRequest(r, workerIdx);
                    else if constexpr (std::is_same_v<T, TreeRowRequest>)  applyTreeRowRequest(r, workerIdx);
                }, req);
            } catch (...) {
                setWriterException(std::current_exception());
                accepting_.store(false, std::memory_order_release);
                fillNotFull_.notify_all();
                return;
            }
        }
    }

// ── quiesce protocol ─────────────────────────────────────────────────
    // Watchdog sets quiesceRequested_ + notifies fillNotEmpty_.
    // Workers arrive, wait on quiesceHold_.
    // Watchdog waits until quiesceArrived_ == nRecordThreads_, runs
    // checkpoint snapshot, then clears the flag + notifies quiesceResume_.
inline         void Writer::arriveAtQuiesce() {
        {
            std::lock_guard<std::mutex> lock(quiesceMutex_);
            ++quiesceArrived_;
        }
        quiesceCv_.notify_all();   // notify watchdog
        {
            std::unique_lock<std::mutex> lock(quiesceMutex_);
            quiesceHold_.wait(lock, [&] { return !quiesceRequested_.load(); });
            if (quiesceArrived_ > 0) --quiesceArrived_;
        }
        quiesceCv_.notify_all();   // notify watchdog waiting for arrived==0
    }

inline void Writer::quiesceWorkers() {
        quiesceRequested_.store(true, std::memory_order_release);
        fillNotEmpty_.notify_all();
        std::unique_lock<std::mutex> lock(quiesceMutex_);
        quiesceCv_.wait(lock, [&] { return quiesceArrived_ >= nRecordThreads_; });
    }

inline void Writer::releaseWorkers() {
        quiesceRequested_.store(false, std::memory_order_release);
        quiesceHold_.notify_all();
        std::unique_lock<std::mutex> lock(quiesceMutex_);
        quiesceCv_.wait(lock, [&] { return quiesceArrived_ == 0; });
    }

// ── watchdog loop ────────────────────────────────────────────────────
    // Drains watchQueue_.  Handles Heartbeat (fire-and-forget) and the
    // Checkpoint / Finalize / Fatal lifecycle events.
inline         void Writer::watchdogLoop() {
        while (true) {
            WatchRequest req;
            {
                std::unique_lock<std::mutex> lock(watchMutex_);
                watchCv_.wait(lock, [&] {
                    return stopRequested_.load(std::memory_order_acquire)
                        || !watchQueue_.empty();
                });
                if (watchQueue_.empty()) return;
                req = std::move(watchQueue_.front());
                watchQueue_.pop_front();
            }

            try {
                switch (req.kind) {
                    case WatchRequest::Kind::Heartbeat:
                        // v1: fire-and-forget; logger's own thread handles
                        // periodic status output.  Reserved for future
                        // per-event heartbeat artifacts.
                        break;

                    case WatchRequest::Kind::Checkpoint:
                        quiesceWorkers();
                        try {
                            writeCheckpointFile(req.eventIndex);
                        } catch (...) {
                            releaseWorkers();
                            throw;
                        }
                        releaseWorkers();
                        completeBarrier(req.barrier);
                        break;

                    case WatchRequest::Kind::Finalize:
                        drainAndStopWorkers();
                        // If any worker stored an exception during fills,
                        // surface it through the Finalize barrier rather
                        // than silently merging partial state.
                        if (writerException_) {
                            completeBarrier(req.barrier, writerException_, false);
                            return;
                        }
                        mergeAllClones();
                        writeAllToCurrentFile(req.eventIndex, false);
                        completeBarrier(req.barrier);
                        return;

                    case WatchRequest::Kind::Fatal:
                        accepting_.store(false, std::memory_order_release);
                        stopRequested_.store(true, std::memory_order_release);
                        fillNotEmpty_.notify_all();
                        fillNotFull_.notify_all();
                        joinWorkers();
                        try {
                            mergeAllClones();
                            writeAllToCurrentFile(req.eventIndex, false);
                        } catch (...) {
                            completeBarrier(req.barrier, std::current_exception(), false);
                            return;
                        }
                        completeBarrier(req.barrier);
                        return;
                }
            } catch (...) {
                setWriterException(std::current_exception());
                completeBarrier(req.barrier, std::current_exception(), false);
                failPendingWatchBarriers(std::current_exception());
                return;
            }
        }
    }

inline void Writer::drainAndStopWorkers() {
        // Wait until fill queue is empty AND all workers idle.
    // Producers have already had accepting_ cleared by the finish flow.
        for (;;) {
            {
                std::lock_guard<std::mutex> lock(fillMutex_);
                if (fillQueue_.empty()) break;
            }
            std::this_thread::sleep_for(std::chrono::microseconds(200));
        }
        stopRequested_.store(true, std::memory_order_release);
        fillNotEmpty_.notify_all();
        joinWorkers();
    }

inline void Writer::joinWorkers() {
        for (auto& t : workers_) if (t.joinable()) t.join();
        workers_.clear();
    }

inline void Writer::setWriterException(std::exception_ptr error) {
        std::lock_guard<std::mutex> lock(fillMutex_);
        if (!writerException_) writerException_ = std::move(error);
    }

inline void Writer::failPendingWatchBarriers(std::exception_ptr error) {
        std::vector<std::shared_ptr<BarrierState>> barriers;
        {
            std::lock_guard<std::mutex> lock(watchMutex_);
            for (auto& req : watchQueue_)
                if (req.barrier) barriers.push_back(req.barrier);
            watchQueue_.clear();
        }
        for (auto& b : barriers) completeBarrier(b, error, false);
    }

} // namespace Record
