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

    Probe::ProbeParallel probe;
    Record::Writer       writer;
    Monitor::AsyncLogger asyncLogger;

    Config::configure(configPath, project, probe, writer, asyncLogger);

    Lambda::Parameters physParams;
    Lambda::RootArray  histogramSets;
    Lambda::configure(physParams, histogramSets, writer, configPath);

    writer.bind(asyncLogger, asyncLogger.watch(),
                [&physParams]() { return Lambda::logString(physParams); });
    writer.installFatalStallHandler(histogramSets);

    asyncLogger.initialise(writer);

    Lambda::AnalysisContext ctx{histogramSets, physParams, asyncLogger.watch(), asyncLogger, writer};
    probe.run([&](const Probe::Event& ev, int threadId) {
        Lambda::rootAnalysis(ev, threadId, ctx);
    });

    {
        writer.meta().dataset.parent_files = {probe.inputFile()};
        Record::Meta::fillDerived(writer.meta(), project, configPath, asyncLogger.watch(), Config::Register{});
        Record::Meta::integrityAddFileSha(writer.meta(), configPath);
        Record::Meta::integrityAddFileSha(writer.meta(), writer.histConfig().histLimitsFile.Data());
    }
    writer.shutdown(histogramSets);

    return 0;
}
