#pragma once

#include <chrono>
#include <cstddef>
#include <pwd.h>
#include <string>
#include <sys/utsname.h>
#include <unistd.h>
#include <vector>
#include <sstream>
#include <fstream>

#include "TDirectory.h"
#include "TFile.h"
#include "TParameter.h"
#include "TObjString.h"
#include "TUUID.h"

// Forward-declare so Meta.hh doesn't have to include Config.hh if you
// want to avoid circular deps — but since Config.hh includes no Meta.hh,
// just include it directly.
#include "Config.hh"
#include <toml++/toml.hpp>

namespace Meta {

    // ── Struct ─────────────────────────────────────────────────────────────

    struct Dataset {
        std::string name;         // from [metadata].dataset_name
        std::string experiment;   // optional; default "Pythia8_standalone"
        std::string data_type;    // "MC" | "data" | "derived"
        std::string run_period;
        std::string campaign;
        std::string file_uuid;    // auto: TUUID
        std::vector<std::string> parent_files; // input ROOT files (if any)
    };

    struct Processing {
        std::string analysis_name;   // e.g. "Lambda_Reconstruction"
        std::string build_type;      // auto: Release / Debug
        std::string compiler;        // auto: __VERSION__
        std::string root_version;    // auto: gROOT->GetVersion()
        std::string os_arch;         // auto: uname
        std::string config_snapshot; // auto: verbatim TOML text of config file
    };

    struct EventSummary {
        std::size_t n_events_total     = 0;
        std::size_t n_events_processed = 0;
        Double_t    sum_weights        = 0.0;  // equals n_events_processed for unweighted MC
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
        // Verbatim text of the [lambda] (or equivalent) TOML section
        std::string selection_toml;
    };

    struct Integrity {
        std::string creation_timestamp; // ISO 8601
        std::string processed_by;       // user@host
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

    // ── Auto-capture helpers ────────────────────────────────────────────────

    inline std::string nowISO8601() {
        const auto now = std::chrono::system_clock::now();
        const std::time_t t = std::chrono::system_clock::to_time_t(now);
        char buf[32];
        std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", std::gmtime(&t));
        return buf;
    }

    inline std::string processedBy() {
        // user@host
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

    // ── capture() — builds a Record from available sources ─────────────────
    // analysisName: e.g. "Lambda_Reconstruction"
    // configPath:   path to the main TOML config file
    // log, root:    current run params (call AFTER run, so nRealEvents is final)

    inline Record capture(const std::string& analysisName,
                          const std::string& configPath,
                          const Config::Log&  log,
                          const Config::Root& root)
    {
        Record r;

        // ── dataset ──────────────────────────────────────────────────────
        // [metadata] section is optional; if absent, fields stay empty
        try {
            const auto cfg = toml::parse_file(configPath);
            if (const auto* meta = cfg["metadata"].as_table()) {
                r.dataset.name       = meta->get("dataset_name") ?
                                       (*meta)["dataset_name"].value_or(std::string{}) : "";
                r.dataset.data_type  = meta->get("data_type") ?
                                       (*meta)["data_type"].value_or(std::string{"MC"}) : "MC";
                r.dataset.run_period = meta->get("run_period") ?
                                       (*meta)["run_period"].value_or(std::string{}) : "";
                r.dataset.campaign   = meta->get("campaign") ?
                                       (*meta)["campaign"].value_or(std::string{}) : "";
                r.notes.description  = meta->get("notes") ?
                                       (*meta)["notes"].value_or(std::string{}) : "";

                // optional physics overrides
                if (meta->get("generator"))
                    r.physics.generator = (*meta)["generator"].value_or(std::string{"Pythia8"});
                if (meta->get("tune"))
                    r.physics.tune = (*meta)["tune"].value_or(std::string{});
                if (meta->get("pdf_set"))
                    r.physics.pdf_set = (*meta)["pdf_set"].value_or(std::string{});
            }

            // [lambda] section → selection_toml (verbatim)
            // Reconstruct by serialising only the [lambda] table back to string
            if (const auto* lam = cfg["lambda"].as_table()) {
                std::ostringstream ss;
                ss << *lam;
                r.objects.selection_toml = ss.str();
            }
        } catch (...) {}

        r.dataset.file_uuid = TUUID().AsString();
        r.dataset.experiment = "Pythia8_standalone";

        // ── processing ───────────────────────────────────────────────────
        r.processing.analysis_name   = analysisName;
#ifdef NDEBUG
        r.processing.build_type = "Release";
#else
        r.processing.build_type = "Debug";
#endif
        r.processing.compiler    = __VERSION__;
        r.processing.root_version = gROOT->GetVersion();
        r.processing.os_arch      = osArch();
        r.processing.config_snapshot = readFile(configPath);

        // ── events ───────────────────────────────────────────────────────
        r.events.n_events_total     = log.nEvents;
        r.events.n_events_processed = log.nRealEvents;
        r.events.sum_weights        = static_cast<Double_t>(log.nRealEvents);
        r.events.sum_weights_squared = static_cast<Double_t>(log.nRealEvents);

        // ── physics ──────────────────────────────────────────────────────
        // beamEnergy is stored as TString e.g. "7000"
        try {
            r.physics.center_of_mass_energy_gev =
                std::stod(std::string(root.beamEnergy.Data()));
        } catch (...) {}

        // ── integrity ────────────────────────────────────────────────────
        r.integrity.creation_timestamp = nowISO8601();
        r.integrity.processed_by       = processedBy();

        return r;
    }

    // ── writeAbout() — writes all metadata into About/ TDirectory ──────────

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

        // ── dataset/ ─────────────────────────────────────────────────────
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

        // ── processing/ ──────────────────────────────────────────────────
        TDirectory* pr = about->mkdir("processing");
        detail::writeStr(pr, "analysis_name",   rec.processing.analysis_name);
        detail::writeStr(pr, "build_type",      rec.processing.build_type);
        detail::writeStr(pr, "compiler",        rec.processing.compiler);
        detail::writeStr(pr, "root_version",    rec.processing.root_version);
        detail::writeStr(pr, "os_arch",         rec.processing.os_arch);
        detail::writeStr(pr, "config_snapshot", rec.processing.config_snapshot);

        // ── events/ ──────────────────────────────────────────────────────
        TDirectory* ev = about->mkdir("events");
        detail::writePar(ev, "n_events_total",      static_cast<Long64_t>(rec.events.n_events_total));
        detail::writePar(ev, "n_events_processed",  static_cast<Long64_t>(rec.events.n_events_processed));
        detail::writePar(ev, "sum_weights",         rec.events.sum_weights);
        detail::writePar(ev, "sum_weights_squared", rec.events.sum_weights_squared);

        // ── physics/ ─────────────────────────────────────────────────────
        TDirectory* ph = about->mkdir("physics");
        detail::writePar(ph, "center_of_mass_energy_gev", rec.physics.center_of_mass_energy_gev);
        detail::writePar(ph, "cross_section_pb",          rec.physics.cross_section_pb);
        detail::writePar(ph, "filter_efficiency",         rec.physics.filter_efficiency);
        detail::writeStr(ph, "generator", rec.physics.generator);
        detail::writeStr(ph, "tune",      rec.physics.tune);
        detail::writeStr(ph, "pdf_set",   rec.physics.pdf_set);

        // ── objects/ ─────────────────────────────────────────────────────
        TDirectory* ob = about->mkdir("objects");
        detail::writeStr(ob, "selection_toml", rec.objects.selection_toml);

        // ── integrity/ ───────────────────────────────────────────────────
        TDirectory* ig = about->mkdir("integrity");
        detail::writeStr(ig, "creation_timestamp", rec.integrity.creation_timestamp);
        detail::writeStr(ig, "processed_by",       rec.integrity.processed_by);

        // ── notes/ ───────────────────────────────────────────────────────
        TDirectory* nt = about->mkdir("notes");
        detail::writeStr(nt, "description",  rec.notes.description);
        detail::writeStr(nt, "known_issues", rec.notes.known_issues);
        detail::writeStr(nt, "contact",      rec.notes.contact);

        // Write About/ and all contents into the file
        file->cd();
        about->Write("", TObject::kOverwrite);
    }
}
