#pragma once

#include <condition_variable>
#include <cstddef>
#include <exception>
#include <memory>
#include <mutex>
#include <utility>
#include <variant>
#include <vector>

#include "Physics.hh"
#include "Record/Types.hh"

namespace Record {

    // WriterMT.md Phase 2: ParticleRequest is now a single basis + particles.
    // The legacy `ParticleGroupFillRequest` / `groups` aggregation was
    // dropped — `fillParticleEvent` fans out into N separate requests so
    // each one drives one ParticleObjects' fill independently.
    struct ParticleRequest {
        RecordKey basis{};
        std::vector<Physics::Lorentz> particles;
    };

    struct Hist1DRequest  { RecordKey basis{}; Value value; };
    struct Hist2DRequest  { RecordKey basis{}; Value x; Value y; };
    struct GraphRequest   { RecordKey basis{}; Value x; Value y; };
    struct ProfileRequest { RecordKey basis{}; Value x; Value y; };

    struct TreeRowRequest {
        RecordKey tree{};
        std::vector<std::pair<RecordKey, Value>> values;
    };

    using FillRequest = std::variant<
        ParticleRequest,
        Hist1DRequest,
        Hist2DRequest,
        GraphRequest,
        ProfileRequest,
        TreeRowRequest
    >;

    struct BarrierState {
        std::mutex mutex;
        std::condition_variable cv;
        bool done = false;
        std::exception_ptr exception;
        bool completed = false;
    };

    // ── WatchRequest ──────────────────────────────────────────────────────────
    // docs/WriterMT.md Phase 1.  Pushed by AsyncLogger into the Writer's
    // watchdog control queue when configured thresholds are crossed
    // ([monitor.logs].save_heartbeat / save_checkpoints / save_log_threads) or
    // when the run reaches Finalize/Fatal.  In Phase 1 only the Logger
    // emits these; in Phase 2 the Writer's watchdog thread consumes them.
    struct WatchRequest {
        enum class Kind {
            Heartbeat,    // logger sample, no file write needed in v1
            Checkpoint,   // quiesce workers, write checkpoint TFile
            Finalize,     // drain workers, merge, write final TFile, exit
            Fatal,        // best-effort drain + write, exit
        };

        Kind                          kind        = Kind::Heartbeat;
        std::size_t                   eventIndex  = 0;
        std::shared_ptr<BarrierState> barrier;   // present for Checkpoint, Finalize, Fatal
    };

    template <typename Basis>
    struct ParticleFillView {
        Basis basis;
        const std::vector<Physics::Lorentz>& particles;
    };

} // namespace Record
