#pragma once

// ── Record/Configs.hh ────────────────────────────────────────────────────────
// Configuration-input types owned by Record::Writer (see docs/plans/Record_Writer
// Step 1). Distinct from Record/Types.hh, which holds the runtime
// histogram/tree record structures.
//
// `Paths` aggregates every output-path TString that drivers, the AsyncLogger,
// and Monitor::Render use. `HistConfig` aggregates the histogram-shape
// configuration (binCount, histScale) plus the resolved per-property/
// per-level limits maps.
//
// Both are populated by Config::configureWriter and stored inside
// Record::Writer thereafter. They will replace the corresponding fields in
// Config::Register when W7 lands fully (see docs/Architecture.md).

#include "TString.h"
#include "RtypesCore.h"

#include "Config/Types.hh"      // Config::ParticleLimits / EventLimits
namespace Record {

    struct Paths {
        TString rootDirectory;
        TString logDirectory;
        TString checkpointDirectory;
        TString outName;
        TString logName;
        TString runStatName;
        TString threadStatDirectory;
        TString checkpointOutName;
        TString checkpointLogName;
        TString fileTitle;
        TString beamEnergy;          // string form (e.g. "13000"), used in file naming
        Int_t   serial = 0;          // raw serial integer; padded form derived on demand
    };

    struct HistConfig {
        Int_t                  binCount  = 100;
        Double_t               histScale = 100;
        TString                histLimitsFile;
        Config::ParticleLimits particleLimits;
        Config::EventLimits    eventLimits;
    };
} // namespace Record
