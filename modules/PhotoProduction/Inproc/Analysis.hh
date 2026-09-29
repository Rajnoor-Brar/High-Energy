#pragma once
// modules/PhotoProduction/Inproc/Analysis.hh — Rivet on its own thread, fed by the Pythia threads.
//
// One AnalysisHandler on one thread. Rivet is not thread-safe, and FastJet's SISCone (photo_eic)
// keeps process-wide statics, so Rivets on several threads would change the jets (L16). What
// changes is that Rivet no longer runs inside Pythia's callback: generation goes on while it
// analyses, and waits only when the feed is full. For more than one Rivet's rate, run the chain with
// `shards` (V31): separate processes share nothing.
//
// At the end Rivet is given the σ the chain's Rivet would read (L28) as a user σ, so the order the
// events reached it in does not matter; then it finalises and writes.

#include "Module.hh"
#include "Inproc/Feed.hh"

#include "HepMC3/GenEvent.h"
#include "Rivet/AnalysisHandler.hh"
#include "Rivet/Tools/RivetPaths.hh"

#include <atomic>
#include <exception>
#include <memory>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace Inproc {

    class Analysis {
      public:
        // `table` is [standard.rivet_analyses]: the analyses, options included, and the plugin path.
        Analysis(Module::Job& job, const Module::Values& table, size_t depth = 128) : job_(job), feed_(depth) {
            Rivet::addAnalysisLibPath(table.get("plugin_path", ""));
            rivet_.addAnalyses(table.list("analyses"));
        }
        ~Analysis() { halt(); }
        Analysis(const Analysis&) = delete;
        Analysis& operator=(const Analysis&) = delete;

        // Once the generator is initialised: nothing may exit the program while this thread runs.
        void start() { thread_ = std::thread([this] { loop(); }); }

        // From any Pythia thread. False when Rivet has stopped taking events.
        bool push(std::shared_ptr<HepMC3::GenEvent> event) { return feed_.push(std::move(event)); }

        bool failed() const { return failed_; }
        long analysed() const { return analysed_; }

        // No more events: Rivet analyses what is queued, and its thread ends.
        void halt() {
            feed_.close();
            if (thread_.joinable()) thread_.join();
        }

        // After the generator is done: halt, then σ, finalise and write. An error message, or "".
        std::string finish(const std::vector<std::pair<double, double>>& sigma, const std::string& output) {
            halt();
            if (failed_) return error_;
            try {
                if (!sigma.empty()) rivet_.setCrossSection(sigma, true);   // L28
                rivet_.finalize();
                rivet_.writeData(output);
            } catch (const std::exception& error) {
                return std::string("Rivet: ") + error.what();
            }
            return "";
        }

      private:
        void loop() {
            try {
                while (std::shared_ptr<HepMC3::GenEvent> event = feed_.pop()) {
                    rivet_.analyze(*event);
                    job_.countEvent(event->weights().empty() ? 1.0 : event->weights().front());   // this thread only
                    ++analysed_;
                }
            } catch (const std::exception& error) {
                error_ = std::string("Rivet: ") + error.what();
                failed_ = true;
            } catch (...) {
                error_ = "Rivet: unknown exception";
                failed_ = true;
            }
            if (failed_) feed_.close();                                 // the producers stop waiting
        }

        Module::Job& job_;
        Rivet::AnalysisHandler rivet_;
        Feed feed_;
        std::thread thread_;
        std::atomic<bool> failed_{false};
        std::atomic<long> analysed_{0};
        std::string error_;                                             // set before failed_
    };

}  // namespace Inproc
