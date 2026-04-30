#pragma once

#include <sstream>
#include <string>

#include "Lambda/Types.hh"
#include "Lambda/TypeAid.hh"
#include "Lambda/ParamAid.hh"
#include "Lambda/Parameters.hh"
#include "Lambda/Loaders.hh"
#include "Lambda/Declare.hh"
#include "Lambda/Reconstruction.hh"
#include "Lambda/Recording.hh"
#include "Lambda/Context.hh"

namespace Lambda{

    inline std::string dataLogString() {
        std::ostringstream stream;
        stream << "Proton PDG ID                 : 2212\n";
        stream << "Pion PDG ID                   : -211 (pi-)\n";
        stream << "Selection                     : isFinal() only\n";
        return stream.str();
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
    // root is kept as a separate parameter because it holds the checkpoint
    // output paths, which are specific to this handler.
    inline void pythiaAnalysis(Pythia8::Pythia& pythia,
                               Config::Register& root,
                               AnalysisContext& ctx)
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

        if (ctx.logging.check_interval > 0 && eventIndex % ctx.logging.check_interval == 0) {
            Record::checkpointWrite(ctx.histograms, root.checkpointOutName, root.histScale, eventIndex);
            Monitor::outputLog(root, ctx.logging, logString(ctx.parameters), root.checkpointLogName,
                               [&pythia]() { pythia.stat(); },
                               [&pythia]() { pythia.settings.listChanged(); });
        }
    }

    // ── rootAnalysis ──────────────────────────────────────────────────────────
    // Called once per Probe::Event from runParallel (multi-threaded).
    // histMutex serialises TH1D::Fill calls and is kept as a separate
    // parameter because it belongs to the driver, not to the shared context.
    inline void rootAnalysis(const Probe::Event& ev,
                             int threadId,
                             std::mutex& histMutex,
                             AnalysisContext& ctx)
    {
        const std::size_t eventIndex = ++ctx.logging.iEvent;
        const auto [protonLabel, pionLabel] = resolveCandidateLabels(ctx.parameters);

        ctx.asyncLogger.publishThreadStats(threadId, Monitor::ThreadPhase::Analysis, eventIndex, Monitor::NoCallbackCompleted);

        const std::vector<Lorentz> protonList = ev[protonLabel];
        const std::vector<Lorentz> pionList   = ev[pionLabel];

        {
            std::lock_guard<std::mutex> lock(histMutex);
            fillCandidates(ctx.histograms, reconstructCandidates(protonList, pionList, ctx.parameters));
        }

        ctx.logging.recordEvent(std::chrono::system_clock::now());

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
