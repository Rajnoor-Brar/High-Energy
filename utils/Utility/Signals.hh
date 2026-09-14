#pragma once

// ── Utility/Signals.hh ────────────────────────────────────────────────────────
// Graceful-stop signal handling for SIGINT/SIGTERM.
//
// Without this, Ctrl-C or a batch-system kill (SLURM/HTCondor send SIGTERM,
// then SIGKILL after a grace period) leaves a truncated, unclosed ROOT file —
// the Writer's Fatal/checkpoint machinery never runs. With it, the event loop
// polls stopRequested() and exits cleanly through writer.finish()/fatalWrite().
//
//   Utility::Signals::installGracefulStop();   // once, at the top of main()
//   ...
//   if (Utility::Signals::stopRequested()) break;   // in the event loop
//
// First signal: sets the flag (graceful path). Second signal: restores the
// default handler, so a third actually kills a hung process.
// ─────────────────────────────────────────────────────────────────────────────

#include <atomic>
#include <csignal>

namespace Utility::Signals {

    // Sentinel thrown by event callbacks to unwind out of generator/reader
    // loops that have no native early-exit (e.g. PythiaParallel::run).
    // Drivers catch it and finalize with the actual processed-event count.
    struct StopRequested {};

    namespace detail {
        inline std::atomic<bool>& flag() {
            static std::atomic<bool> requested{false};
            return requested;
        }
        // Async-signal-safe: only touches the atomic and sigaction-free APIs.
        inline void handler(int signum) {
            if (flag().exchange(true, std::memory_order_relaxed)) {
                // Second signal: give up on graceful — restore default so the
                // next one terminates the process.
                std::signal(signum, SIG_DFL);
            }
        }
    } // namespace detail

    inline void installGracefulStop() {
        std::signal(SIGINT,  detail::handler);
        std::signal(SIGTERM, detail::handler);
    }

    inline bool stopRequested() {
        return detail::flag().load(std::memory_order_relaxed);
    }

    // For tests / multi-run drivers.
    inline void resetStopFlag() {
        detail::flag().store(false, std::memory_order_relaxed);
    }

} // namespace Utility::Signals
