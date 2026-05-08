#include <chrono>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

#include "Record.hh"
#include "Config.hh"
#include "Lambda.hh"
#include "Monitor.hh"
#include "Config/Configure.hh"

int main(int argc, char* argv[]) {
    Monitor::disable_input_echo();
    std::atexit(Monitor::restore_terminal);

    const std::string project    = "Lambda_Generation";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Pythia8::PythiaParallel pythia;

    Record::Writer       writer;
    Monitor::AsyncLogger logger;

    Config::configure(configPath, project, pythia, writer, logger);

    Lambda::Parameters analysisParams;
    Lambda::RootArray  histogramSets;
    Lambda::configure(analysisParams, histogramSets, writer, configPath);

    writer.bind(logger, logger.watch(),
                [&analysisParams]() { return Lambda::logString(analysisParams); },
                [&pythia]() { pythia.stat(); },
                [&pythia]() { pythia.settings.listChanged(); });
    writer.installFatalStallHandler(histogramSets);

    logger.initialise(writer);
    pythia.init();

    Lambda::AnalysisContext ctx{histogramSets, analysisParams, logger.watch(), logger, writer};
    pythia.run(static_cast<long>(logger.watch().nEvents), [&](Pythia8::Pythia* worker) {
        Lambda::pythiaAnalysis(*worker, ctx);
    });

    writer.shutdown(histogramSets);

    return 0;
}
