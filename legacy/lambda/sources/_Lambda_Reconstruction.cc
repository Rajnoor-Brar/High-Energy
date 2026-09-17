#include <chrono>
#include <iostream>
#include <string>

#include "Probe.hh"
#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"
#include "Config/Configure.hh"
#include "Utility/Signals.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);
    Utility::Signals::installGracefulStop();

    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Probe::ProbeParallel probe;
    Record::Writer       writer;
    Monitor::AsyncLogger asyncLogger;

    Config::configure(configPath, project, probe, writer, asyncLogger);

    Lambda::Parameters physParams;
    Lambda::configure(physParams, writer, configPath);

    Record::WriterHooks hooks;
    hooks.programLog = [&physParams]() { return Lambda::logString(physParams); };
    writer.bind(asyncLogger, std::move(hooks));

    asyncLogger.initialise(writer);
    writer.start();

    Lambda::AnalysisContext ctx{physParams, asyncLogger.watch(), asyncLogger, writer};
    bool interrupted = false;
    try {
        // On SIGINT/SIGTERM the callback throws; ProbeParallel stops all
        // partitions (requestStop) and rethrows after joining.
        probe.streamEvents([&](const Probe::Event& ev, int threadId) {
            if (Utility::Signals::stopRequested()) throw Utility::Signals::StopRequested{};
            Lambda::rootAnalysis(ev, threadId, ctx);
        });
    } catch (const Utility::Signals::StopRequested&) {
        interrupted = true;
        std::cerr << "\n[Signal] Stop requested — finalizing partial output\n";
    }

    writer.meta().dataset.parent_files = {probe.inputFile()};
    Record::Meta::integrityAddFileSha(writer.meta(), configPath);
    Record::Meta::integrityAddFileSha(writer.meta(), writer.histConfig().histLimitsFile.Data());
    writer.finish(interrupted ? asyncLogger.watch().iEvent.load()
                              : asyncLogger.watch().nEvents);

    Monitor::TimerRegistry::instance().dump(std::cout);

    return 0;
}
