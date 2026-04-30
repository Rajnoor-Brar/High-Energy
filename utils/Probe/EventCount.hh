#pragma once

#include <cstddef>
#include <memory>
#include <string>

#include "TFile.h"
#include "TParameter.h"

namespace Probe {

    // ── resolveEventCount ─────────────────────────────────────────────────────
    // Reads About/events/n_events_total from a ROOT file written by
    // _Lambda_Data (via Record::Meta::writeAbout). Returns 0 when the file cannot be
    // opened, the directory is missing, the parameter is absent, or the stored
    // value is non-positive.
    //
    // Callers (reconstruction drivers) use this as the second tier in a
    // three-tier resolver:
    //   1. [events].event_count / [run].event_count from the TOML config
    //   2. About/events/n_events_total from the input ROOT file  ← this function
    //   3. Full key scan via Probe::EventStream::nEvents()
    inline std::size_t resolveEventCount(const std::string& filepath) {
        std::unique_ptr<TFile> f(TFile::Open(filepath.c_str(), "READ"));
        if (!f || f->IsZombie()) return 0;

        if (auto* dir = f->GetDirectory("About/events")) {
            if (auto* par =
                    dynamic_cast<TParameter<Long64_t>*>(dir->Get("n_events_total")))
                if (par->GetVal() > 0)
                    return static_cast<std::size_t>(par->GetVal());
        }
        return 0;
    }

} // namespace Probe
