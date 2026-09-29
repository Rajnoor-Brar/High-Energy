#pragma once
// modules/PhotoProduction/Inproc/Feed.hh — the events from the Pythia threads to the Rivet thread.
//
// Bounded, so a slow Rivet holds generation back instead of filling memory: a producer waits while it
// is full. After close() nothing more goes in, and pop() still hands out what is left, then nullptr.

#include "HepMC3/GenEvent.h"

#include <algorithm>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <memory>
#include <mutex>

namespace Inproc {

    class Feed {
      public:
        explicit Feed(size_t depth) : depth_(std::max<size_t>(depth, 1)) {}

        // False once closed: the event was not taken.
        bool push(std::shared_ptr<HepMC3::GenEvent> event) {
            std::unique_lock<std::mutex> lock(lock_);
            notFull_.wait(lock, [&] { return closed_ || queue_.size() < depth_; });
            if (closed_) return false;
            queue_.push_back(std::move(event));
            notEmpty_.notify_one();
            return true;
        }

        // The next event; nullptr when closed and empty.
        std::shared_ptr<HepMC3::GenEvent> pop() {
            std::unique_lock<std::mutex> lock(lock_);
            notEmpty_.wait(lock, [&] { return closed_ || !queue_.empty(); });
            if (queue_.empty()) return nullptr;
            std::shared_ptr<HepMC3::GenEvent> event = std::move(queue_.front());
            queue_.pop_front();
            notFull_.notify_one();
            return event;
        }

        void close() {
            {
                std::lock_guard<std::mutex> guard(lock_);
                closed_ = true;
            }
            notFull_.notify_all();
            notEmpty_.notify_all();
        }

      private:
        const size_t depth_;
        std::mutex lock_;
        std::condition_variable notFull_, notEmpty_;
        std::deque<std::shared_ptr<HepMC3::GenEvent>> queue_;
        bool closed_ = false;
    };

}  // namespace Inproc
