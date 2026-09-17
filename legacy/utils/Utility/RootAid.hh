#pragma once

// ── Utility/RootAid.hh ────────────────────────────────────────────────────────
// Checked access and RAII guards for ROOT's footgun APIs, shared by Record,
// Probe, and Paint:
//
//   enableThreadSafetyOnce  — single process-wide ROOT::EnableThreadSafety()
//   openRead                — TFile::Open + zombie check, throws with context
//   get<T>                  — TDirectory::Get + dynamic_cast, throws with context
//   require                 — nullptr → throw with context
//   BatchGuard              — gROOT batch-mode save/restore
//   StyleGuard              — gStyle state save/restore (per-plot isolation)
// ─────────────────────────────────────────────────────────────────────────────

#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>

#include "TDirectory.h"
#include "TFile.h"
#include "TROOT.h"
#include "TStyle.h"

namespace Utility::RootAid {

    // Required before any multi-threaded ROOT use: even read-only paths hit
    // shared state (TClass first-load, gROOT->fListOfFiles on TFile::Open,
    // basket allocators). Sporadic crashes and silent stat corruption occur
    // without it — see docs/Blueprint_Probe.md. Replaces the per-namespace
    // once-flags that previously lived in Record and Probe.
    inline void enableThreadSafetyOnce() {
        static std::once_flag flag;
        std::call_once(flag, [] { ROOT::EnableThreadSafety(); });
    }

    // nullptr → throw; context should say what was being looked up and where.
    template <typename T>
    inline T* require(T* pointer, const std::string& context) {
        if (pointer == nullptr)
            throw std::runtime_error("[RootAid] " + context);
        return pointer;
    }

    // TFile::Open + zombie check. The returned TFile is owned by the caller.
    inline std::unique_ptr<TFile> openRead(const std::string& path,
                                           const std::string& who = "RootAid") {
        std::unique_ptr<TFile> file(TFile::Open(path.c_str(), "READ"));
        if (!file || file->IsZombie())
            throw std::runtime_error("[" + who + "] Cannot open ROOT file '" + path + "'");
        return file;
    }

    // Get + dynamic_cast in one step; throws naming the object, expected type,
    // and source location instead of returning nullptr to be dereferenced.
    template <typename T>
    inline T* get(TDirectory& dir, const std::string& name,
                  const std::string& who = "RootAid") {
        TObject* object = dir.Get(name.c_str());
        if (object == nullptr)
            throw std::runtime_error("[" + who + "] Missing object '" + name +
                                     "' in '" + dir.GetName() + "'");
        T* typed = dynamic_cast<T*>(object);
        if (typed == nullptr)
            throw std::runtime_error("[" + who + "] Object '" + name + "' in '" +
                                     dir.GetName() + "' is a " +
                                     object->ClassName() + ", not a " +
                                     T::Class()->GetName());
        return typed;
    }

    // gROOT batch-mode save/restore (canvas rendering without display).
    struct BatchGuard {
        Bool_t previous;
        BatchGuard() : previous(gROOT->IsBatch()) { gROOT->SetBatch(kTRUE); }
        ~BatchGuard() { gROOT->SetBatch(previous); }
        BatchGuard(const BatchGuard&)            = delete;
        BatchGuard& operator=(const BatchGuard&) = delete;
    };

    // gStyle save/restore: isolates per-plot gStyle mutations so one result's
    // style does not leak into the next. TStyle::Copy restores the full state.
    struct StyleGuard {
        TStyle saved;
        StyleGuard() : saved(*gStyle) {}
        ~StyleGuard() {
            if (gStyle) saved.Copy(*gStyle);
        }
        StyleGuard(const StyleGuard&)            = delete;
        StyleGuard& operator=(const StyleGuard&) = delete;
    };

} // namespace Utility::RootAid
