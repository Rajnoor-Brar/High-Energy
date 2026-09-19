#pragma once

// ── Store/Compression.hh ─────────────────────────────────────────────────────
// Which codec a store is written with, and what a build can actually do (11 §1, D-Q9).
//
// HepMC3's compression is header-only (`WriterGZ.h` / `ReaderGZ.h`) with the codec as a **template
// parameter**, so the choice has to be turned from a runtime string into a type. That is all this
// file does, plus the part that matters operationally: a build without zstd must say so plainly
// rather than fail at the first event, and a store written by a build with zstd must be readable by
// one without — which is why the codec is recorded in the index and checked when it is opened.

#include <memory>
#include <string>
#include <vector>

#include "Core/Errors.hh"

#if defined(HEKIT_WITH_HEPMC)
#include "HepMC3/ReaderAscii.h"
#include "HepMC3/WriterAscii.h"
#if defined(HEPMC3_USE_COMPRESSION)
#include "HepMC3/CompressedIO.h"
#include "HepMC3/ReaderGZ.h"
#include "HepMC3/WriterGZ.h"
#endif
#endif

namespace Store {

    //: The codecs this build was compiled with. `none` is always available.
    inline std::vector<std::string> codecs() {
        std::vector<std::string> found{"none"};
#if defined(HEPMC3_Z_SUPPORT)
        found.push_back("gz");
#endif
#if defined(HEPMC3_ZSTD_SUPPORT)
        found.push_back("zst");
#endif
        return found;
    }

    inline bool supports(const std::string& codec) {
        for (const std::string& entry : codecs())
            if (entry == codec) return true;
        return false;
    }

    /// `events.0` + `gz` → `events.0.hepmc.gz`.
    inline std::string shardName(int worker, const std::string& codec) {
        const std::string suffix = codec == "none" || codec.empty() ? "" : "." + codec;
        return "events." + std::to_string(worker) + ".hepmc" + suffix;
    }

    inline void requireCodec(const std::string& codec) {
        if (supports(codec)) return;
        std::string available;
        for (const std::string& entry : codecs()) available += (available.empty() ? "" : ", ") + entry;
        throw Core::Error{Core::Exit::Config,
                          "this build cannot write '" + codec + "' event stores",
                          "it has: " + available + " (see `hep-run --capabilities`)"};
    }

#if defined(HEKIT_WITH_HEPMC)

    /// A writer for one shard. The codec is a template parameter in HepMC3, so it is resolved here.
    inline std::unique_ptr<HepMC3::Writer> makeWriter(const std::string& path,
                                                      const std::string& codec) {
        requireCodec(codec);
#if defined(HEPMC3_Z_SUPPORT)
        if (codec == "gz")
            return std::make_unique<HepMC3::WriterGZ<HepMC3::WriterAscii, HepMC3::Compression::z>>(path);
#endif
#if defined(HEPMC3_ZSTD_SUPPORT)
        if (codec == "zst")
            return std::make_unique<HepMC3::WriterGZ<HepMC3::WriterAscii, HepMC3::Compression::zstd>>(path);
#endif
        return std::make_unique<HepMC3::WriterAscii>(path);
    }

    /// A reader for one shard. `ReaderGZ` detects the codec from the stream, so one type reads all
    /// of them — but the build still has to have been compiled with it.
    inline std::unique_ptr<HepMC3::Reader> makeReader(const std::string& path,
                                                      const std::string& codec) {
        requireCodec(codec);
#if defined(HEPMC3_USE_COMPRESSION)
        if (codec != "none" && !codec.empty())
            return std::make_unique<HepMC3::ReaderGZ<HepMC3::ReaderAscii>>(path);
#endif
        return std::make_unique<HepMC3::ReaderAscii>(path);
    }

#endif  // HEKIT_WITH_HEPMC

}  // namespace Store
