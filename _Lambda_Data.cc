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

    const std::string project    = "Lambda_Data";
    const std::string configPath = argc > 1 ? argv[1] : "configs/Lambda_Generation.toml";

    Pythia8::PythiaParallel pythia;

    Record::Writer       writer;
    Monitor::AsyncLogger logger;

    Config::configure(configPath, project, pythia, writer, logger);

    if (logger.watch().n_threads > 0) {
        const std::size_t nThreads = Config::resolveThreadCount(logger.watch().n_threads);
        pythia.readString("Parallelism:numThreads = " + std::to_string(nThreads));
    }

    Lambda::declareDataObjects(writer);

    writer.bind(logger, logger.watch(),
                []() { return Lambda::dataLogString(); },
                [&pythia]() { pythia.stat(); },
                [&pythia]() { pythia.settings.listChanged(); });

    logger.initialise(writer);
    pythia.init();
    writer.start();

    Lambda::GenerationContext ctx{logger.watch(), logger, writer};
    pythia.run(static_cast<long>(logger.watch().nEvents), [&](Pythia8::Pythia* worker) {
        Lambda::dataGenerator(*worker, ctx);
    });

    writer.finish(logger.watch().nEvents);

    return 0;
}
