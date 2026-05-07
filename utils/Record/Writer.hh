#pragma once

// ── Record/Writer.hh ─────────────────────────────────────────────────────────
// Owns Paths, HistConfig, Meta::Record, the open TFile*, and the finalizer
// responsibilities (bind/installFatalStallHandler/shutdown/checkpoint).
//
// Lifecycle:
//   Record::Writer writer;
//   Config::configureWriter(writer, ...) — populates state, opens TFile
//   writer.bind(logger, logParams, programLog, ...) — wire callbacks
//   writer.installFatalStallHandler(histogramSets) — arm emergency path
//   // histogram declarations, event loop ...
//   writer.meta().dataset.parent_files = ...; fillDerived(...) — update meta
//   writer.shutdown(histogramSets) — write, close, report
//
// Method bodies for bind/shutdown/checkpoint/installFatalStallHandler/
// fatalShutdown live in Record/Finalizer.hh to avoid a circular dependency:
//   Monitor/Logger.hh → Record/Writer.hh  (Logger::start takes const Writer&)
//   Record/Writer.hh  ↛ Monitor.hh        (would create a cycle)
// Drivers include Record.hh (umbrella) which picks up both headers.

#include <atomic>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <string>
#include <utility>

#include "TFile.h"

#include "Config.hh"
#include "Record/Configs.hh"
#include "Record/Meta.hh"

// Forward declarations — full types provided by Monitor.hh (via Finalizer.hh).
namespace Monitor {
    class AsyncLogger;
    struct RunSnapshot;
}

namespace Record {

    class Writer {
      public:
        Writer() = default;
        ~Writer() {
            if (outFile_ != nullptr) {
                outFile_->Close();
                delete outFile_;
                outFile_ = nullptr;
            }
        }

        Writer(const Writer&)            = delete;
        Writer& operator=(const Writer&) = delete;
        Writer(Writer&&)                 = delete;
        Writer& operator=(Writer&&)      = delete;

        // ── lifecycle ────────────────────────────────────────────────────────
        // Populate state and open the output ROOT file. Throws on failure.
        void open(Paths        paths,
                  HistConfig   hist,
                  Meta::Record initialMeta)
        {
            paths_ = std::move(paths);
            hist_  = std::move(hist);
            meta_  = std::move(initialMeta);

            if (outFile_ != nullptr) {
                outFile_->Close();
                delete outFile_;
                outFile_ = nullptr;
            }
            outFile_ = new TFile(paths_.outName, "RECREATE");
            if (outFile_ == nullptr || outFile_->IsZombie())
                throw std::runtime_error("[Record::Writer] Failed to create ROOT output file: " + std::string(paths_.outName.Data()));
        }

        // ── binding ──────────────────────────────────────────────────────────
        // Wire the logger, watch, and shutdown callbacks. Call before
        // installFatalStallHandler() and before the event loop starts.
        // Body in Record/Finalizer.hh.
        void bind(Monitor::AsyncLogger&        logger,
                  Config::Watch&               logging,
                  std::function<std::string()> programLog,
                  std::function<void()>         printStats   = {},
                  std::function<void()>         listChanged  = {},
                  std::function<void()>         preCloseHook = {});

        // ── shutdown methods (bodies in Record/Finalizer.hh) ─────────────────
        // Arms the fatal-stall emergency write path on the logger. Pass the
        // same histogramSets that will be passed to shutdown().
        template <typename RootArrayT>
        void installFatalStallHandler(RootArrayT& sets);

        // Write histograms, write About/ metadata tree, close the ROOT file,
        // finish the logger, print terminal report, write the run log.
        template <typename RootArrayT>
        void shutdown(RootArrayT& sets);

        // Snapshot checkpoint: write sets to the checkpoint ROOT file and write
        // a checkpoint log. Called from within per-event handlers.
        template <typename RootArrayT>
        void checkpoint(RootArrayT& sets, std::size_t eventIndex);

        // ── recording mutex ───────────────────────────────────────────────────
        // Returns an RAII lock guard on the internal fill mutex.
        // Hold it for the duration of multi-threaded TH1D::Fill calls.
        std::lock_guard<std::mutex> recordingScope() {
            return std::lock_guard<std::mutex>(histMutex_);
        }

        // ── accessors ────────────────────────────────────────────────────────
        TFile*              file()       const { return outFile_; }
        const Paths&        paths()      const { return paths_; }
        const HistConfig&   histConfig() const { return hist_; }
        Meta::Record&       meta()             { return meta_; }
        const Meta::Record& meta()       const { return meta_; }

      private:
        // Called by the AsyncLogger fatal-stall handler (non-template; uses
        // emergencyWriteFn_ type-erased by installFatalStallHandler).
        void fatalShutdown(const Monitor::RunSnapshot& snapshot);

        Paths        paths_;
        HistConfig   hist_;
        Meta::Record meta_;
        TFile*       outFile_ = nullptr;

        std::mutex                       histMutex_;
        Config::Watch*                   logging_       = nullptr;
        Monitor::AsyncLogger*            logger_        = nullptr;
        std::function<std::string()>     programLog_;
        std::function<void()>            printStats_;
        std::function<void()>            listChanged_;
        std::function<void()>            preCloseHook_;
        std::atomic<bool>                fatalShutdownStarted_{false};
        // Type-erased write-and-close captured from installFatalStallHandler so
        // fatalShutdown() itself stays non-templated.
        std::function<void(std::size_t)> emergencyWriteFn_;
    };

    // ── configureWriter ──────────────────────────────────────────────────────
    // Mirror an already-populated Config::Register into Writer-owned Paths /
    // HistConfig, build the initial Meta::Record, and open the output ROOT file.
    inline void configureWriter(Writer&                 writer,
                                const std::string&      project,
                                const std::string&      configPath,
                                Config::Watch&          watch,
                                Config::Register&       reg,
                                const std::string&      probeInputFile = "")
    {
        Paths paths;
        paths.rootDirectory       = reg.rootDirectory;
        paths.logDirectory        = reg.logDirectory;
        paths.checkpointDirectory = reg.checkpointDirectory;
        paths.outName             = reg.outName;
        paths.logName             = reg.logName;
        paths.runStatName         = reg.runStatName;
        paths.threadStatDirectory = reg.threadStatDirectory;
        paths.checkpointOutName   = reg.checkpointOutName;
        paths.checkpointLogName   = reg.checkpointLogName;
        paths.fileTitle           = reg.fileTitle;
        paths.beamEnergy          = reg.beamEnergy;
        paths.serial              = reg.serial;

        HistConfig hist;
        hist.binCount       = reg.binCount;
        hist.histScale      = reg.histScale;
        hist.histLimitsFile = reg.histLimitsFile;
        hist.particleLimits = reg.particleLimits;
        hist.eventLimits    = reg.eventLimits;

        Meta::Record meta;
        Meta::mergeFromToml(meta, configPath);
        if (!probeInputFile.empty())
            Meta::mergeFromProbe(meta, probeInputFile);
        Meta::fillDerived(meta, project, configPath, watch, reg);

        writer.open(std::move(paths), std::move(hist), std::move(meta));
    }

} // namespace Record
