#pragma once

#include <cstdint>
#include <mutex>
#include <sstream>
#include <string>

#include "Lambda/Types.hh"
#include "Lambda/TypeAid.hh"
#include "Lambda/Parameters.hh"
#include "Lambda/Loaders.hh"
#include "Lambda/Declare.hh"
#include "Lambda/Reconstruction.hh"
#include "Lambda/Recording.hh"
#include "Lambda/Context.hh"
#include "Monitor/Timer.hh"

namespace Lambda{

    inline std::string dataLogString() {
        std::ostringstream stream;
        stream << "Proton PDG ID                 : 2212\n";
        stream << "Pion PDG ID                   : -211 (pi-)\n";
        stream << "Selection                     : isFinal() only\n";
        return stream.str();
    }

    // ── configure ─────────────────────────────────────────────────────────────
    // Convenience wrapper: populate Parameters from TOML then declare histograms.
    // Equivalent to calling extractPhysics + declareObjects in sequence.
    inline void configure(Parameters&        parameters,
                          Record::Writer&    writer,
                          const std::string& configPath) {
        extractPhysics(configPath, parameters, writer.histConfig());
        declareObjects(parameters, writer);
    }

    inline std::string logString(const Parameters& parameters) {
        std::ostringstream stream;
        stream << "Lambda Mass                   : " << kLambdaMass << '\n';
        stream << "Proton Mass                   : " << kProtonMass << '\n';
        stream << "Pion Mass                     : " << kPionMass << '\n';
        stream << "Mass Difference               : " << kMassDiff << '\n';
        stream << "Mass Tolerance                : " << parameters.massTolerance << '\n';
        stream << "Theta Tolerance               : " << parameters.thetaTolerance << '\n';
        stream << "Reserved Protons              : " << parameters.reservedProtons << '\n';
        return stream.str();
    }

    // ── pythiaAnalysis ────────────────────────────────────────────────────────
    // Called once per Pythia8 event (serial or parallel).
    inline void pythiaAnalysis(Pythia8::Pythia& pythia, AnalysisContext& ctx)
    {
        // docs/WriterMT.md Phase 1: countEvent atomically increments
        // watch.iEvent and emits WatchRequest (heartbeat/checkpoint) via
        // the sink configured in Monitor::ConfigAid.  Phase 1 the sink is
        // unbound; in Phase 2 it routes into the Writer's watchdog.
        const std::size_t eventIndex = ctx.asyncLogger.countEvent();
        const int workerIndex = pythia.mode("Parallelism:index");

        if (eventIndex == 1) {
            std::lock_guard<std::mutex> terminalLock(Monitor::terminalMutex());
            pythia.info.list();
            std::cout << "\n\n\n" << std::endl;
        }

        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        const auto [protons, pions] = harvestParticles(pythia);
        fillCandidates(ctx.writer, reconstructCandidates(protons, pions, ctx.parameters));

        ctx.logging.recordEvent(std::chrono::system_clock::now());

        ctx.asyncLogger.publish(ctx.logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);
        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);

        if (ctx.asyncLogger.checkInterval() > 0 && eventIndex % ctx.asyncLogger.checkInterval() == 0)
            ctx.writer.checkpoint(eventIndex);
    }

    // ── rootAnalysis ──────────────────────────────────────────────────────────
    // Called once per Probe::Event from runParallel (multi-threaded).
    inline void rootAnalysis(const Probe::Event& ev,
                             int threadId,
                             AnalysisContext& ctx)
    {
        // BlockTimer timer("Whole Analysis");
        // docs/WriterMT.md Phase 1: countEvent atomically increments
        // watch.iEvent and emits WatchRequest (heartbeat/checkpoint) via
        // the sink configured in Monitor::ConfigAid.  Phase 1 the sink is
        // unbound; in Phase 2 it routes into the Writer's watchdog.
        const std::size_t eventIndex = ctx.asyncLogger.countEvent();

        ctx.asyncLogger.publishThreadStats(threadId, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        const std::vector<Lorentz> protonList = ev[ctx.parameters.protonLabel];
        const std::vector<Lorentz> pionList   = ev[ctx.parameters.pionLabel];

        fillCandidates(ctx.writer, reconstructCandidates(protonList, pionList, ctx.parameters));
        ctx.logging.recordEvent(std::chrono::system_clock::now());

        ctx.asyncLogger.publish(ctx.logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);
        ctx.asyncLogger.publishThreadStats(threadId, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);
    }

    // ── dataGenerator ─────────────────────────────────────────────────────────
    // Called once per Pythia8 event (parallel). Writes raw proton/pion rows
    // through the Writer queue.
    inline void dataGenerator(Pythia8::Pythia& pythia, GenerationContext& ctx)
    {
        // docs/WriterMT.md Phase 1: countEvent atomically increments
        // watch.iEvent and emits WatchRequest (heartbeat/checkpoint) via
        // the sink configured in Monitor::ConfigAid.  Phase 1 the sink is
        // unbound; in Phase 2 it routes into the Writer's watchdog.
        const std::size_t eventIndex = ctx.asyncLogger.countEvent();
        const int workerIndex = pythia.mode("Parallelism:index");

        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        const auto [protons, pions] = harvestParticles(pythia);

        const auto eventIdx = static_cast<std::int32_t>(eventIndex);
        for (const auto& proton : protons) {
            ctx.writer.fillTree<DataTree, DataBranch>(DataTree::Protons, {
                {DataBranch::EventIndex, eventIdx},
                {DataBranch::Energy,     proton.E()},
                {DataBranch::Px,         proton.Px()},
                {DataBranch::Py,         proton.Py()},
                {DataBranch::Pz,         proton.Pz()},
            });
        }

        for (const auto& pion : pions) {
            ctx.writer.fillTree<DataTree, DataBranch>(DataTree::Pions, {
                {DataBranch::EventIndex, eventIdx},
                {DataBranch::Energy,     pion.E()},
                {DataBranch::Px,         pion.Px()},
                {DataBranch::Py,         pion.Py()},
                {DataBranch::Pz,         pion.Pz()},
            });
        }

        ctx.logging.recordEvent(std::chrono::system_clock::now());

        ctx.asyncLogger.publish(ctx.logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);
        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);
    }
}
