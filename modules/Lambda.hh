#pragma once

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
                          RootArray&         histogramSets,
                          Record::Writer&    writer,
                          const std::string& configPath) {
        extractPhysics(configPath, parameters, writer.histConfig());
        declareObjects(histogramSets, parameters, writer);
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
        const std::size_t eventIndex = ++ctx.logging.iEvent;
        const int workerIndex = pythia.mode("Parallelism:index");

        if (eventIndex == 1) {
            std::lock_guard<std::mutex> terminalLock(Monitor::terminalMutex());
            pythia.info.list();
            std::cout << "\n\n\n" << std::endl;
        }

        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        const auto [protons, pions] = harvestParticles(pythia);
        fillCandidates(ctx.histograms, reconstructCandidates(protons, pions, ctx.parameters));

        ctx.logging.recordEvent(std::chrono::system_clock::now());

        ctx.asyncLogger.publish(ctx.logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);
        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);

        if (ctx.asyncLogger.checkInterval() > 0 && eventIndex % ctx.asyncLogger.checkInterval() == 0)
            ctx.writer.checkpoint(ctx.histograms, eventIndex);
    }

    // ── rootAnalysis ──────────────────────────────────────────────────────────
    // Called once per Probe::Event from runParallel (multi-threaded).
    // ctx.writer.recordingScope() serialises TH1D::Fill calls.
    inline void rootAnalysis(const Probe::Event& ev,
                             int threadId,
                             AnalysisContext& ctx)
    {
        BlockTimer timer("Whole Analysis");
        const std::size_t eventIndex = ++ctx.logging.iEvent;

        ctx.asyncLogger.publishThreadStats(threadId, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        const std::vector<Lorentz> protonList = ev[ctx.parameters.protonLabel];
        const std::vector<Lorentz> pionList   = ev[ctx.parameters.pionLabel];

        {
            // BlockTimer timer("Core Analysis");
            auto lock = ctx.writer.recordingScope();
            fillCandidates(ctx.histograms, reconstructCandidates(protonList, pionList, ctx.parameters));
        }
        {
            // BlockTimer timer("Root Recording");
        ctx.logging.recordEvent(std::chrono::system_clock::now());
        }

        ctx.asyncLogger.publish(ctx.logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);
        ctx.asyncLogger.publishThreadStats(threadId, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);
    }

    // ── dataGenerator ─────────────────────────────────────────────────────────
    // Called once per Pythia8 event (parallel).  Writes raw proton/pion
    // branches; treeMutex and the output trees live inside GenerationContext.
    inline void dataGenerator(Pythia8::Pythia& pythia, GenerationContext& ctx)
    {
        const std::size_t eventIndex = ++ctx.logging.iEvent;
        const int workerIndex = pythia.mode("Parallelism:index");

        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        const auto [protons, pions] = harvestParticles(pythia);

        const Int_t eventIdx = static_cast<Int_t>(eventIndex);
        {
            std::lock_guard<std::mutex> lock(ctx.treeMutex);
            auto& protonBranches = *ctx.data.protonBranches;
            *ctx.data.protonEventIndex = eventIdx;
            for (const auto& proton : protons) {
                protonBranches = {proton.E(), proton.Px(), proton.Py(), proton.Pz()};
                ctx.data.protons->Fill();
            }

            auto& pionBranches = *ctx.data.pionBranches;
            *ctx.data.pionEventIndex = eventIdx;
            for (const auto& pion : pions) {
                pionBranches = {pion.E(), pion.Px(), pion.Py(), pion.Pz()};
                ctx.data.pions->Fill();
            }
        }

        ctx.logging.recordEvent(std::chrono::system_clock::now());

        ctx.asyncLogger.publish(ctx.logging, Monitor::RunPhase::Analysis, Monitor::DontWriteRunStat);
        ctx.asyncLogger.publishThreadStats(workerIndex, Monitor::ThreadPhase::Simulation, eventIndex, Monitor::CallbackCompleted);
    }
}
