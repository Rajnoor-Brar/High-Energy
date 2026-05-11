#pragma once

// ── Probe/EventReaderMT.hh ───────────────────────────────────────────────────
// Per-task TTreeReader adapter for one ParticleSpec.
//
// Used inside a TTreeProcessorMT::Process callback: ROOT hands us a
// TTreeReader& positioned over our task's basket cluster, and this class
// binds the index + four momenta branches with the correct C++ types.
// readOne() consumes one entry and returns (event_index, Lorentz).
//
// Type dispatch is via a polymorphic ValueBinder so the spec can declare
// each branch's storage type (D=Double_t, F=Float_t, I=Int_t, etc.) and
// we bind a TTreeReaderValue of the matching type at runtime.
//
// Phase 2 implementation — docs/ROOTMT.md.
// ─────────────────────────────────────────────────────────────────────────────

#include <array>
#include <memory>
#include <stdexcept>
#include <string>

#include "TTreeReader.h"
#include "TTreeReaderValue.h"

#include "Probe/BranchControl.hh"
#include "Probe/Types.hh"

namespace Probe {

    // ── ValueBinder (type-erased TTreeReaderValue wrapper) ────────────────────
    // virtual call per entry per branch; overhead negligible vs basket-read.

    struct ValueBinder {
        virtual ~ValueBinder()              = default;
        virtual double  asDouble()          = 0;
        virtual Long64_t asInteger()        = 0;
    };

    template<typename T>
    class TypedBinder : public ValueBinder {
      public:
        TypedBinder(TTreeReader& r, const std::string& name)
            : rv_(r, name.c_str()) {}
        double  asDouble()  override { return static_cast<double>(*rv_); }
        Long64_t asInteger() override { return static_cast<Long64_t>(*rv_); }
      private:
        TTreeReaderValue<T> rv_;
    };

    inline std::unique_ptr<ValueBinder>
    makeBinder(TTreeReader& r, const std::string& name, BranchType t)
    {
        switch (t) {
            case BranchType::Double: return std::make_unique<TypedBinder<Double_t>>(r, name);
            case BranchType::Float:  return std::make_unique<TypedBinder<Float_t >>(r, name);
            case BranchType::Int32:  return std::make_unique<TypedBinder<Int_t   >>(r, name);
            case BranchType::Int64:  return std::make_unique<TypedBinder<Long64_t>>(r, name);
            case BranchType::UInt32: return std::make_unique<TypedBinder<UInt_t  >>(r, name);
            default:
                throw std::runtime_error(
                    "[Probe::IMT] makeBinder: unsupported type for branch '" + name + "'");
        }
    }

    // ── EventReaderMT ────────────────────────────────────────────────────────
    // One adapter per ParticleSpec, constructed inside a TTreeProcessorMT
    // callback.  Lifetime is the duration of the callback.

    class EventReaderMT {
      public:
        EventReaderMT(TTreeReader& reader, const ParticleSpec& spec)
            : coords_(spec.coords)
        {
            if (spec.indexBranches.empty())
                throw std::runtime_error(
                    "[Probe::IMT] EventReaderMT: spec '" + spec.label +
                    "' has no index branch");

            // Index binder
            const BranchSpec& idx = spec.indexBranches[0];
            idxBinder_ = makeBinder(reader, idx.name, idx.type);

            // Momenta binders
            const auto names = BranchControl::coordNames(spec.coords);
            std::array<BranchType, 4> types{};
            std::visit([&](const auto& s) {
                for (std::size_t i = 0; i < 4; ++i) types[i] = s.branches[i].type;
            }, spec.coords);

            for (std::size_t i = 0; i < 4; ++i)
                momBinders_[i] = makeBinder(reader, names[i], types[i]);
        }

        // Consume one entry.  Returns false when the task's range is exhausted.
        bool readOne(TTreeReader& reader, Long64_t& outKey, Lorentz& outP) {
            if (!reader.Next()) return false;
            outKey = idxBinder_->asInteger();
            const double a = momBinders_[0]->asDouble();
            const double b = momBinders_[1]->asDouble();
            const double c = momBinders_[2]->asDouble();
            const double d = momBinders_[3]->asDouble();
            outP = BranchControl::makeLorentz(coords_, a, b, c, d);
            return true;
        }

      private:
        std::unique_ptr<ValueBinder>                 idxBinder_;
        std::array<std::unique_ptr<ValueBinder>, 4>  momBinders_;
        CoordSpec                                    coords_;
    };

} // namespace Probe
