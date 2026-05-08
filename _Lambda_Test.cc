#include <chrono>
#include <thread>
#include "Pythia8/Pythia.h"

#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"
#include "Config/Configure.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Test";
    const std::string configPath = argc > 1 ? argv[1] : "configs/Lambda_Reconstruction.toml";

    Pythia8::Pythia pythia;

    Record::Writer       writer;
    Monitor::AsyncLogger asyncLogger;

    Config::configure(configPath, project, pythia, writer, asyncLogger);

    Lambda::Parameters  analysisParams;
    Lambda::RootArray   histogramSets;
    Lambda::configure(analysisParams, histogramSets, writer, configPath);

    writer.bind(asyncLogger, asyncLogger.watch(),
                [&analysisParams]() { return Lambda::logString(analysisParams); },
                [&pythia]() { pythia.stat(); },
                [&pythia]() { pythia.settings.listChanged(); });
    writer.installFatalStallHandler(histogramSets);

    pythia.init();

    asyncLogger.initialise(writer);
    pythia.next();

    Lambda::AnalysisContext ctx{histogramSets, analysisParams, asyncLogger.watch(), asyncLogger, writer};
    for (std::size_t iEvent = 0; iEvent < asyncLogger.watch().nEvents; ++iEvent) {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
        Lambda::pythiaAnalysis(pythia, ctx);
    }

    writer.shutdown(histogramSets);

    return 0;
}
