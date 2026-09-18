#pragma once

// ── Core/Signals.hh ──────────────────────────────────────────────────────────
// A cooperative stop on SIGINT/SIGTERM. Adapted from `legacy/utils/Utility/Signals.hh:22-57`, with two
// changes:
//
//   * `sigaction` instead of `std::signal`, so the disposition is defined (no re-arming races) and
//     `SA_RESTART` keeps a blocked read from failing with EINTR halfway through an event;
//   * the second signal restores the default handler, so an impatient Ctrl-C still kills the process.
//
// The handler does nothing but set an atomic flag: everything else (writing a partial result, joining
// threads) happens on the main thread, which is the only way this can be both safe and useful.
// `PythiaParallel::run` cannot be interrupted, so `Run::loop` checks `stopRequested()` between chunks
// (P2-S02, D-Q2).

#include <atomic>
#include <csignal>

namespace Core::Signals {

    namespace detail {
        inline std::atomic<bool>& flag() {
            static std::atomic<bool> requested{false};
            return requested;
        }

        // Async-signal-safe: an atomic store and, at most, one sigaction call.
        inline void handler(int number) {
            if (detail::flag().exchange(true, std::memory_order_relaxed)) {
                struct sigaction action {};
                action.sa_handler = SIG_DFL;
                sigemptyset(&action.sa_mask);
                ::sigaction(number, &action, nullptr);
            }
        }
    }  // namespace detail

    // Ask for a graceful stop on the next chunk boundary.
    inline void installGracefulStop() {
        struct sigaction action {};
        action.sa_handler = detail::handler;
        sigemptyset(&action.sa_mask);
        action.sa_flags = SA_RESTART;
        ::sigaction(SIGINT, &action, nullptr);
        ::sigaction(SIGTERM, &action, nullptr);
    }

    inline bool stopRequested() { return detail::flag().load(std::memory_order_relaxed); }

    // For tests and for a process that runs several specs in sequence.
    inline void resetStopFlag() { detail::flag().store(false, std::memory_order_relaxed); }

    inline void requestStop() { detail::flag().store(true, std::memory_order_relaxed); }

}  // namespace Core::Signals
