#include <chrono>
#include <iostream>
#include <string>

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"

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

    const std::string project    = "Lambda_Generation";
    const std::string configPath = argc > 1 ? argv[1] : "configs/" + project + ".toml";

    Pythia8::PythiaParallel pythia;

    Record::Writer       writer;
    Monitor::AsyncLogger asyncLogger;

    Config::configure(configPath, project, pythia, writer, asyncLogger);

    Lambda::Parameters analysisParams;
    Lambda::configure(analysisParams, writer, configPath);

    Record::WriterHooks hooks;
    hooks.programLog          = [&analysisParams]() { return Lambda::logString(analysisParams); };
    hooks.printStats          = [&pythia]() { pythia.stat(); };
    hooks.listChangedSettings = [&pythia]() { pythia.settings.listChanged(); };
    writer.bind(asyncLogger, std::move(hooks));

    asyncLogger.initialise(writer);
    pythia.init();
    writer.start();

    Lambda::AnalysisContext ctx{analysisParams, asyncLogger.watch(), asyncLogger, writer};
    // PythiaParallel invokes the callback on its worker threads and has no
    // abort API, so throwing here would std::terminate. Cooperative skip
    // instead: after the first SIGINT/SIGTERM remaining events generate but
    // are not processed; a second signal kills immediately (default handler).
    pythia.run(static_cast<long>(asyncLogger.watch().nEvents), [&](Pythia8::Pythia* worker) {
        if (Utility::Signals::stopRequested()) return;
        Lambda::pythiaAnalysis(*worker, ctx);
    });
    const bool interrupted = Utility::Signals::stopRequested();
    if (interrupted)
        std::cerr << "\n[Signal] Stop requested — finalizing partial output\n";

    Record::Meta::integrityAddFileSha(writer.meta(), configPath);
    Record::Meta::integrityAddFileSha(writer.meta(), writer.histConfig().histLimitsFile.Data());
    writer.finish(interrupted ? asyncLogger.watch().iEvent.load()
                              : asyncLogger.watch().nEvents);

    Monitor::TimerRegistry::instance().dump(std::cout);

    return 0;
}
