#pragma once

#include "Config.hh"
#include "Monitor.hh"
#include "Record/Writer.hh"
#include "Types.hh"

namespace Lambda {

    struct AnalysisContext {
        const Parameters&     parameters;
        Config::Watch&        logging;
        Monitor::AsyncLogger& asyncLogger;
        Record::Writer&       writer;
    };

    struct GenerationContext {
        Config::Watch&        logging;
        Monitor::AsyncLogger& asyncLogger;
        Record::Writer&       writer;
    };

} // namespace Lambda
