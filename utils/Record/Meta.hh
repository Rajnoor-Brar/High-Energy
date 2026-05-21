#pragma once

#include <chrono>
#include <cstddef>
#include <fstream>
#include <pwd.h>
#include <sstream>
#include <string>
#include <sys/utsname.h>
#include <unistd.h>
#include <vector>

#include "Config.hh"
#include "TDirectory.h"
#include "TFile.h"
#include "TParameter.h"
#include "TObjString.h"
#include "TUUID.h"
#include <toml++/toml.hpp>

namespace Record::Meta {

    struct Dataset {
        std::string name;
        std::string experiment;
        std::string data_type;
        std::string run_period;
        std::string campaign;
        std::string file_uuid;
        std::vector<std::string> parent_files;
    };

    struct Processing {
        std::string analysis_name;
        std::string build_type;
        std::string compiler;
        std::string root_version;
        std::string os_arch;
        std::string config_snapshot;
    };

    struct EventSummary {
        std::size_t n_events_total      = 0;
        std::size_t n_events_processed  = 0;
        Double_t    sum_weights         = 0.0;
        Double_t    sum_weights_squared = 0.0;
    };

    struct Physics {
        Double_t    center_of_mass_energy_gev = 0.0;
        std::string generator  = "Pythia8";
        std::string tune;
        std::string pdf_set;
        Double_t    cross_section_pb  = 0.0;
        Double_t    filter_efficiency = 1.0;
    };

    struct Objects {
        std::string selection_toml;
    };

    struct Integrity {
        std::string creation_timestamp;
        std::string processed_by;
        std::string git_sha;        // short SHA at build time (from -DGIT_SHA)
        bool        git_dirty = false; // uncommitted changes present at build time
        std::string host_uname;     // kernel + hostname at run time
        std::vector<std::string> file_shas; // "path:sha256" pairs, one per loaded file
    };

    struct Notes {
        std::string description;
        std::string known_issues;
        std::string contact;
    };

    struct Record {
        Dataset      dataset;
        Processing   processing;
        EventSummary events;
        Physics      physics;
        Objects      objects;
        Integrity    integrity;
        Notes        notes;
    };

    inline std::string nowISO8601() {
        const auto now = std::chrono::system_clock::now();
        const std::time_t t = std::chrono::system_clock::to_time_t(now);
        char buf[32];
        std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));
        return buf;
    }

    inline std::string processedBy() {
        std::string user, host;
        const passwd* pw = getpwuid(getuid());
        user = pw ? pw->pw_name : "unknown";
        char hbuf[256];
        host = (gethostname(hbuf, sizeof(hbuf)) == 0) ? hbuf : "unknown";
        return user + "@" + host;
    }

    inline std::string osArch() {
        utsname u{};
        uname(&u);
        return std::string(u.sysname) + " " + u.machine;
    }

    inline std::string readFile(const std::string& path) {
        std::ifstream f(path);
        if (!f) return "";
        return std::string(std::istreambuf_iterator<char>(f),
                           std::istreambuf_iterator<char>());
    }

    // Compute the SHA-256 of a file by shelling out to shasum/sha256sum.
    // Returns "path:sha256hex" on success, "path:unavailable" if the tool
    // is absent or the file cannot be read.
    inline std::string sha256File(const std::string& path) {
        if (path.empty()) return {};
        // Try shasum -a 256 (macOS/BSD) then sha256sum (Linux)
        for (const char* cmd : {"shasum -a 256 ", "sha256sum "}) {
            const std::string full = std::string(cmd) + "\"" + path + "\" 2>/dev/null";
#ifdef _WIN32
            FILE* pipe = _popen(full.c_str(), "r");
#else
            FILE* pipe = popen(full.c_str(), "r");  // NOLINT(cert-env33-c)
#endif
            if (!pipe) continue;
            char buf[128] = {};
            const bool ok = (fgets(buf, sizeof(buf), pipe) != nullptr);
#ifdef _WIN32
            _pclose(pipe);
#else
            pclose(pipe);
#endif
            if (!ok) continue;
            // Output is "sha256hex  filename\n" — take first token.
            std::string sha = buf;
            const auto sp = sha.find(' ');
            if (sp != std::string::npos) sha = sha.substr(0, sp);
            return path + ":" + sha;
        }
        return path + ":unavailable";
    }

    // Append a "path:sha256" entry to record.integrity.file_shas.
    // Call once per significant input file (cmnd, limits, config).
    inline void integrityAddFileSha(Record& r, const std::string& path) {
        if (path.empty()) return;
        r.integrity.file_shas.push_back(sha256File(path));
    }

    // ── Pass 2 helper: apply one [record.metadata]-shaped table to the Record
    // Per-field; only overwrites when the key is present in `meta`.
    namespace detail {
        inline void applyMetadataTable(Record& r, const toml::table& meta) {
            // Only overwrite when the key is present; dflt handles per-field defaults.
            auto setStr = [&](const char* key, std::string& field,
                              const std::string& dflt = {}) {
                if (meta.get(key)) field = meta[key].value_or(dflt);
            };
            setStr("dataset_name", r.dataset.name);
            setStr("data_type",    r.dataset.data_type);
            setStr("run_period",   r.dataset.run_period);
            setStr("campaign",     r.dataset.campaign);
            setStr("experiment",   r.dataset.experiment);
            setStr("notes",        r.notes.description);
            setStr("known_issues", r.notes.known_issues);
            setStr("contact",      r.notes.contact);
            setStr("generator",    r.physics.generator, "Pythia8");
            setStr("tune",         r.physics.tune);
            setStr("pdf_set",      r.physics.pdf_set);
        }

        inline std::string readObjString(TDirectory* dir, const char* name) {
            if (!dir) return "";
            auto* o = dynamic_cast<TObjString*>(dir->Get(name));
            return o ? std::string(o->GetString().Data()) : std::string{};
        }
        template <typename T>
        inline bool readPar(TDirectory* dir, const char* name, T& out) {
            if (!dir) return false;
            if (auto* p = dynamic_cast<TParameter<T>*>(dir->Get(name))) {
                out = p->GetVal();
                return true;
            }
            return false;
        }
    } // namespace detail

    // ── Pass 2: TOML ────────────────────────────────────────────────────────
    // Reads only cfg["record"]["metadata"]. The former top-level [metadata]
    // alias is rejected by Config::rejectSectionAliases before Writer setup.
    inline void mergeFromToml(Record& r, const std::string& configPath) {
        try {
            const auto cfg = Config::parseConfig(configPath);
            if (const auto* meta = cfg["record"]["metadata"].as_table())
                detail::applyMetadataTable(r, *meta);
            if (const auto* lam = cfg["lambda"].as_table()) {
                std::ostringstream ss;
                ss << *lam;
                r.objects.selection_toml = ss.str();
            }
        } catch (...) {}
    }

    // ── Pass 3: Probe (extract from input ROOT file's About/ block) ─────────
    // Reads About/dataset/* and About/physics/* from a previously-written
    // ROOT file (typically the input to the reconstruction driver). Per-field
    // unconditional overwrite when the source value is non-empty / non-zero
    // — Probe wins over TOML per W7 priority decision (Probe > TOML > defaults).
    inline void mergeFromProbe(Record& r, const std::string& probeInputFile) {
        if (probeInputFile.empty()) return;
        std::unique_ptr<TFile> f(TFile::Open(probeInputFile.c_str(), "READ"));
        if (!f || f->IsZombie()) return;

        auto setS = [&](TDirectory* dir, const char* key, std::string& field) {
            auto s = detail::readObjString(dir, key);
            if (!s.empty()) field = s;
        };
        auto setD = [&](TDirectory* dir, const char* key, Double_t& field) {
            Double_t d = 0;
            if (detail::readPar<Double_t>(dir, key, d) && d > 0) field = d;
        };

        if (auto* ds = f->GetDirectory("About/dataset")) {
            setS(ds, "name",        r.dataset.name);
            setS(ds, "experiment",  r.dataset.experiment);
            setS(ds, "data_type",   r.dataset.data_type);
            setS(ds, "run_period",  r.dataset.run_period);
            setS(ds, "campaign",    r.dataset.campaign);
        }
        if (auto* ph = f->GetDirectory("About/physics")) {
            setS(ph, "generator",   r.physics.generator);
            setS(ph, "tune",        r.physics.tune);
            setS(ph, "pdf_set",     r.physics.pdf_set);
            setD(ph, "center_of_mass_energy_gev", r.physics.center_of_mass_energy_gev);
            setD(ph, "cross_section_pb",          r.physics.cross_section_pb);
            setD(ph, "filter_efficiency",         r.physics.filter_efficiency);
        }
    }

    // ── Pass 4: derived ─────────────────────────────────────────────────────
    // Fields that have no source choice — always computed locally. Safe to
    // re-run (e.g. from Writer::shutdown to refresh event counts after the
    // run loop completes).
    inline void fillDerived(Record& r,
                            const std::string& analysisName,
                            const std::string& configPath,
                            const Config::Watch& log,
                            const Config::Register& root)
    {
        if (r.dataset.file_uuid.empty()) r.dataset.file_uuid = TUUID().AsString();
        if (r.dataset.experiment.empty()) r.dataset.experiment = "Pythia8_standalone";

        r.processing.analysis_name = analysisName;
#ifdef NDEBUG
        r.processing.build_type = "Release";
#else
        r.processing.build_type = "Debug";
#endif
        r.processing.compiler        = __VERSION__;
        r.processing.root_version    = gROOT->GetVersion();
        r.processing.os_arch         = osArch();
        r.processing.config_snapshot = readFile(configPath);

        r.events.n_events_total      = log.nEvents;
        r.events.n_events_processed  = log.n_real_events.load(std::memory_order_relaxed);
        r.events.sum_weights         = static_cast<Double_t>(log.n_real_events.load(std::memory_order_relaxed));
        r.events.sum_weights_squared = static_cast<Double_t>(log.n_real_events.load(std::memory_order_relaxed));

        if (r.physics.center_of_mass_energy_gev == 0.0) {
            try {
                r.physics.center_of_mass_energy_gev = std::stod(root.beamEnergy);
            } catch (...) {}
        }

        r.integrity.creation_timestamp = nowISO8601();
        r.integrity.processed_by       = processedBy();

        // Build-time git provenance (injected as -DGIT_SHA / -DGIT_DIRTY).
#ifdef GIT_SHA
        r.integrity.git_sha   = GIT_SHA;
#else
        r.integrity.git_sha   = "unknown";
#endif
#ifdef GIT_DIRTY
        r.integrity.git_dirty = (GIT_DIRTY != 0);
#else
        r.integrity.git_dirty = false;
#endif

        // Runtime host info: extend osArch() with hostname.
        utsname u{};
        uname(&u);
        char hbuf[256] = {};
        gethostname(hbuf, sizeof(hbuf));
        r.integrity.host_uname = std::string(u.sysname) + " " + u.release
                                  + " " + u.machine + " @ " + hbuf;
    }

    namespace detail {
        inline void writeStr(TDirectory* dir, const char* name, const std::string& val) {
            if (!dir) return;
            dir->cd();
            TObjString obj(val.c_str());
            obj.Write(name, TObject::kOverwrite);
        }
        template <typename T>
        inline void writePar(TDirectory* dir, const char* name, T val) {
            if (!dir) return;
            dir->cd();
            TParameter<T> par(name, val);
            par.Write(name, TObject::kOverwrite);
        }
    }

    inline void writeAbout(TFile* file, const Record& rec) {
        if (!file || file->IsZombie()) return;

        TDirectory* about = file->mkdir("About");
        if (!about) about = file->GetDirectory("About");
        if (!about) return;

        TDirectory* ds = about->mkdir("dataset");
        detail::writeStr(ds, "name",       rec.dataset.name);
        detail::writeStr(ds, "experiment", rec.dataset.experiment);
        detail::writeStr(ds, "data_type",  rec.dataset.data_type);
        detail::writeStr(ds, "run_period", rec.dataset.run_period);
        detail::writeStr(ds, "campaign",   rec.dataset.campaign);
        detail::writeStr(ds, "file_uuid",  rec.dataset.file_uuid);
        {
            std::string pf;
            for (const auto& p : rec.dataset.parent_files) pf += p + "\n";
            detail::writeStr(ds, "parent_files", pf);
        }

        TDirectory* pr = about->mkdir("processing");
        detail::writeStr(pr, "analysis_name",   rec.processing.analysis_name);
        detail::writeStr(pr, "build_type",      rec.processing.build_type);
        detail::writeStr(pr, "compiler",        rec.processing.compiler);
        detail::writeStr(pr, "root_version",    rec.processing.root_version);
        detail::writeStr(pr, "os_arch",         rec.processing.os_arch);
        detail::writeStr(pr, "config_snapshot", rec.processing.config_snapshot);

        TDirectory* ev = about->mkdir("events");
        detail::writePar(ev, "n_events_total",      static_cast<Long64_t>(rec.events.n_events_total));
        detail::writePar(ev, "n_events_processed",  static_cast<Long64_t>(rec.events.n_events_processed));
        detail::writePar(ev, "sum_weights",         rec.events.sum_weights);
        detail::writePar(ev, "sum_weights_squared", rec.events.sum_weights_squared);

        TDirectory* ph = about->mkdir("physics");
        detail::writePar(ph, "center_of_mass_energy_gev", rec.physics.center_of_mass_energy_gev);
        detail::writePar(ph, "cross_section_pb",          rec.physics.cross_section_pb);
        detail::writePar(ph, "filter_efficiency",         rec.physics.filter_efficiency);
        detail::writeStr(ph, "generator", rec.physics.generator);
        detail::writeStr(ph, "tune",      rec.physics.tune);
        detail::writeStr(ph, "pdf_set",   rec.physics.pdf_set);

        TDirectory* ob = about->mkdir("objects");
        detail::writeStr(ob, "selection_toml", rec.objects.selection_toml);

        TDirectory* ig = about->mkdir("integrity");
        detail::writeStr(ig, "creation_timestamp", rec.integrity.creation_timestamp);
        detail::writeStr(ig, "processed_by",       rec.integrity.processed_by);
        detail::writeStr(ig, "git_sha",            rec.integrity.git_sha);
        detail::writeStr(ig, "git_dirty",          rec.integrity.git_dirty ? "true" : "false");
        detail::writeStr(ig, "host_uname",         rec.integrity.host_uname);
        {
            std::string shas;
            for (const auto& s : rec.integrity.file_shas) shas += s + "\n";
            detail::writeStr(ig, "file_shas", shas);
        }

        TDirectory* nt = about->mkdir("notes");
        detail::writeStr(nt, "description",  rec.notes.description);
        detail::writeStr(nt, "known_issues", rec.notes.known_issues);
        detail::writeStr(nt, "contact",      rec.notes.contact);

        file->cd();
        about->Write("", TObject::kOverwrite);
    }
} // namespace Record::Meta
