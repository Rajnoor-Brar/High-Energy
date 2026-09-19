#pragma once

// ── Source/Pythia.hh ─────────────────────────────────────────────────────────
// Pythia as an event source (04 §3, 05 §4), with the behaviours the legacy `generator.cc` got right
// and the ones P0-S04/P2-S02 found it got wrong.
//
// Kept from `generator.cc`:
//   1. cards are read in the spec's order, later values win, and a rejected line stops the run (exit 1);
//   2. nothing is opened before `init()` succeeds;
//   3. quiet by default, but a card may turn output back on.
//
// Corrected here:
//   * **attempts are not successes.** `PythiaParallel::run` returns the number of `next()` calls, and
//     the callback only runs for the ones that worked; at 5x41 GeV about 2 % fail (P0-S04). The counts
//     are kept apart, and a completeness check compares *written* events, never attempts.
//   * **the seed list is validated before `init()`.** Pythia indexes `Parallelism:seeds` without a
//     bounds check, so a short list is undefined behaviour (P2-S02, D-SEEDS). `Core::checkSpec` has
//     already checked it; this asserts it again at the point of use, where it is cheap.
//   * **σ carries an error.** `PythiaParallel` exposes none, so it is combined from the instances
//     (D-Q1).
//   * **chunking.** `run()` is called repeatedly after one `init()`, with a chunk that is a multiple of
//     the thread count so the event set matches an unchunked run (D-Q2). That is what makes Ctrl-C
//     bounded: `PythiaParallel::run` cannot be interrupted from inside.

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <exception>
#include <functional>
#include <mutex>
#include <set>
#include <string>
#include <utility>
#include <vector>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include "Core.hh"
#include "Events.hh"
#include "Source/Base.hh"
#include "Source/Types.hh"
#include "Status.hh"

namespace Source {

    class Pythia : public Base {
      public:
        Pythia(const Core::Spec& spec, Status::Writer& status) : spec_(spec), status_(status) {}

        std::string kind() const override { return "pythia"; }

        // Read the cards and force the run control the spec owns. Throws `Exit::Config` on a rejected
        // card or line, which is behaviour 1 of `generator.cc`.
        void configure() override {
            parallel_.readString("Print:quiet = on");        // a card may turn this back on
            for (const std::string& card : spec_.cards) {
                if (!Core::isRegularFile(card))
                    throw Core::Error{Core::Exit::Config, "card not found: " + card};
                if (!parallel_.readFile(card))
                    throw Core::Error{Core::Exit::Config, "Pythia rejected the card: " + card,
                                      "a missing file, an unknown key or a value out of range; the "
                                      "message above names the line"};
            }
            // The spec's run control beats the cards (behaviour 4 of generator.cc).
            if (spec_.events > 0) parallel_.readString("Main:numberOfEvents = " + std::to_string(spec_.events));
            if (spec_.threads > 0)
                parallel_.readString("Parallelism:numThreads = " + std::to_string(spec_.threads));
            parallel_.readString("Next:numberCount = 0");    // progress comes from the status stream
            parallel_.readString(std::string("Parallelism:processAsync = ") +
                                 (async_ ? "on" : "off"));
            if (!spec_.instance_seeds.empty()) {
                if (spec_.threads > 0 &&
                    spec_.instance_seeds.size() != static_cast<std::size_t>(spec_.threads))
                    throw Core::Error{Core::Exit::Config,
                                      "the seed list does not match the thread count",
                                      "Pythia reads it without a bounds check (D-SEEDS)"};
                parallel_.readString("Random:setSeed = on");
                parallel_.readString("Random:seed = " + std::to_string(spec_.seed));
                std::string seeds;
                for (const std::int64_t seed : spec_.instance_seeds)
                    seeds += (seeds.empty() ? "" : ",") + std::to_string(seed);
                parallel_.readString("Parallelism:seeds = " + seeds);
            }
        }

        // With `processAsync = off` Pythia still calls the callback from the worker threads, but
        // holds one mutex while it does (`PythiaParallel.cc:201-208`); with it on, k callbacks run at
        // once. Either way the callback is on a foreign thread, which is why `run()` catches.
        void async(bool on) override {
            async_ = on;
            parallel_.readString(std::string("Parallelism:processAsync = ") + (on ? "on" : "off"));
        }

        int slots() const override { return async_ ? std::max(1, threads_) : 1; }

        // `init()` failing is its own exit code, because "the cards were fine but the physics is not"
        // is a different problem from a typo (06 §3.3).
        void initialise() override {
            if (!parallel_.init())
                throw Core::Error{Core::Exit::Init, "Pythia failed to initialise",
                                  "the log above says why; a vanishing cross section and impossible "
                                  "beams are the usual causes"};
            threads_ = parallel_.settings.mode("Parallelism:numThreads");
            // One counter per worker, cumulative for the whole run: 06 §3 shows `workers` adding up to
            // `done`, so a reader can draw the load balance. Sized here, where the count is known.
            workers_.assign(static_cast<std::size_t>(std::max(1, threads_)), 0);
            beams_ = readBeams();
        }

        const Core::Beams& beams() const override { return beams_; }
        int threads() const override { return threads_; }

        // The seeds each instance actually got, read back rather than assumed (05 §3).
        std::vector<std::int64_t> instanceSeeds() override {
            std::vector<std::int64_t> seeds;
            parallel_.foreach([&](Pythia8::Pythia* instance) {
                seeds.push_back(instance->settings.mode("Random:seed"));
            });
            return seeds;
        }

        // The chunk size that keeps a chunked run's events identical to an unchunked one (D-Q2).
        std::int64_t chunkSize(std::int64_t wanted) const override {
            return chunkFor(wanted, threads_);
        }

        // Generate `target` events in chunks, calling `consume` for every event that succeeded and
        // asking `stop` between chunks. Returns attempts and accepted counts.
        Core::Counts run(std::int64_t target, std::int64_t chunk,
                         const std::function<void(Events::View&)>& consume,
                         const std::function<bool()>& stop,
                         const std::function<void(std::int64_t)>& checkpoint = {}) override {
            Core::Counts counts;
            const std::int64_t step = chunkSize(chunk);
            // The callback runs on a Pythia worker thread whether or not `processAsync` is on, so an
            // exception escaping it would unwind through `std::thread` and call `std::terminate` —
            // a sink error would kill the process instead of producing an exit code and a message.
            // It is caught here, at the boundary where our code enters a foreign thread, and rethrown
            // on the main thread once the chunk has joined.
            std::exception_ptr failure;
            std::mutex failure_mutex;
            std::atomic<std::int64_t> accepted{0};

            while (counts.attempted < target) {
                const std::int64_t remaining = target - counts.attempted;
                const std::int64_t size = std::min(step, remaining);
                const std::vector<long> per_thread =
                    parallel_.run(size, [&](Pythia8::Pythia* instance) {
                        if (failure) return;              // a sibling already failed; drain quietly
                        try {
                            const int worker = currentWorker(instance);
                            // One instance per thread, so the worker index is also the consumer
                            // slot; `fetch_add` because with processAsync on, k of these race.
                            Events::View view(instance, accepted.fetch_add(1), worker, worker);
                            view.weights().values.assign(1, instance->info.weight());
                            if (worker >= 0 && static_cast<std::size_t>(worker) < workers_.size())
                                workers_[static_cast<std::size_t>(worker)] += 1;
                            consume(view);
                        } catch (...) {
                            const std::lock_guard<std::mutex> guard(failure_mutex);
                            if (!failure) failure = std::current_exception();
                        }
                    });
                // What `run` returns is `next()` calls per thread — attempts, not successes (00/B21).
                for (const long attempts : per_thread) counts.attempted += attempts;
                counts.accepted = accepted.load();
                if (failure) std::rethrow_exception(failure);
                if (checkpoint) checkpoint(counts.accepted);
                if (stop && stop()) break;
            }
            counts.accepted = accepted.load();
            return counts;
        }

        // D-Q1: combine the instances, because PythiaParallel exposes σ but no error.
        Xsec xsec() override {
            Combine combine;
            parallel_.foreach([&](Pythia8::Pythia* instance) {
                combine.add(instance->info.weightSum(), instance->info.sigmaGen(),
                            instance->info.sigmaErr());
            });
            return combine.result();
        }

        // Pythia aggregates its warnings in a Logger; report the counts rather than every message
        // (06 §3.2). Called at checkpoints and at the end.
        void reportWarnings(Status::Writer& status) override {
            for (const auto& [message, count] : warningCounts()) {
                if (reported_.count(message) != 0) continue;
                reported_.insert(message);
                status.log(Status::Level::Warn, "pythia",
                           message + " (x" + std::to_string(count) + ")");
            }
        }

        // The same counts as a number, for the run summary: a run that produced 10⁵ warnings is not
        // the same result as one that produced none, even though neither is an error (07 §2).
        std::vector<std::pair<std::string, long long>> warningCounts() override {
            std::vector<std::pair<std::string, long long>> found;
            parallel_.foreach([&](Pythia8::Pythia* instance) {
                // Logger is iterable over its message → count map.
                for (const auto& entry : instance->logger) {
                    const auto existing =
                        std::find_if(found.begin(), found.end(),
                                     [&](const auto& item) { return item.first == entry.first; });
                    if (existing == found.end())
                        found.emplace_back(entry.first, entry.second);
                    else
                        existing->second += entry.second;
                }
            });
            return found;
        }

        const std::vector<long long>& workers() const override { return workers_; }
        Pythia8::PythiaParallel& parallel() { return parallel_; }

      private:
        // Which worker a callback is running on. `Parallelism:index` is set per instance by
        // PythiaParallel::init, so this is exact rather than a guess from thread ids.
        static int currentWorker(Pythia8::Pythia* instance) {
            return instance->settings.mode("Parallelism:index");
        }

        Core::Beams readBeams() {
            Core::Beams beams;
            Pythia8::Settings& settings = parallel_.settings;
            beams.ids = {settings.mode("Beams:idA"), settings.mode("Beams:idB")};
            const int frame = settings.mode("Beams:frameType");
            if (frame == 1) {
                beams.energies = {settings.parm("Beams:eCM")};
                beams.sqrtS = settings.parm("Beams:eCM");
            } else {
                const double energy_a = settings.parm("Beams:eA");
                const double energy_b = settings.parm("Beams:eB");
                beams.energies = {energy_a, energy_b};
                // √s for two massless-ish beams in the lab frame; the exact value comes from the
                // instances once they are initialised, but this is what the terminal shows first.
                beams.sqrtS = 2.0 * std::sqrt(energy_a * energy_b);
            }
            return beams;
        }

        const Core::Spec& spec_;
        Status::Writer& status_;
        Pythia8::PythiaParallel parallel_;
        Core::Beams beams_;
        int threads_ = 1;
        bool async_ = false;
        std::vector<long long> workers_;
        std::set<std::string> reported_;
    };

}  // namespace Source
