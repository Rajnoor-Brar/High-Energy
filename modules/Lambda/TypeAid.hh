#pragma once

#include "Types.hh"
#include "Physics.hh"
namespace Lambda{

    inline constexpr std::array<HistogramSetAttributes, kHistogramSetCount> kHistogramSetMap{{
        {HistogramSet::Unvalidated, "Unvalidated", "Unvalidated"},
        {HistogramSet::Validated, "Validated", "Validated"},
        {HistogramSet::Selected, "Selected", "Selected"}
    }};

    inline string propertyAlias(Physics::ParticleProperty property) {
        switch (property) {
            case Physics::ParticleProperty::Mass_Invariant: return "Mass";
            case Physics::ParticleProperty::Energy_Net:     return "Energy";
            default:                                       return Physics::particlePropertyName(property);
        }
    }

    inline string propertyAlias(Physics::EventProperty property) { return Physics::eventPropertyName(property); }

}
