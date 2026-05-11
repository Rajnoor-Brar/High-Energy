#include <chrono>
#include <string>

#include "Probe.hh"
#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"
#include "Config/Configure.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Reconstruction";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Probe::ProbeIMT probe;
    Record::Writer       writer;
    Monitor::AsyncLogger asyncLogger;

    Config::configure(configPath, project, probe, writer, asyncLogger);

    Lambda::Parameters physParams;
    Lambda::configure(physParams, writer, configPath);

    writer.bind(asyncLogger, [&physParams]() { return Lambda::logString(physParams); });

    asyncLogger.initialise(writer);
    writer.start();

    Lambda::AnalysisContext ctx{physParams, asyncLogger.watch(), asyncLogger, writer};
    probe.run([&](const Probe::Event& ev, int threadId) {
        Lambda::rootAnalysis(ev, threadId, ctx);
    });

    {
        writer.meta().dataset.parent_files = {probe.inputFile()};
        Record::Meta::fillDerived(writer.meta(), project, configPath, asyncLogger.watch(), Config::Register{});
        Record::Meta::integrityAddFileSha(writer.meta(), configPath);
        Record::Meta::integrityAddFileSha(writer.meta(), writer.histConfig().histLimitsFile.Data());
    }
    writer.finish(asyncLogger.watch().nEvents);

    return 0;
}
