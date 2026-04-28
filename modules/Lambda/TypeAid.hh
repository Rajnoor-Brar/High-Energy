#pragma once

#include "Types.hh"
#include "Physics.hh"
namespace Lambda{

    inline constexpr std::array<HistogramSetAttributes, kHistogramSetCount> kHistogramSetMap{{
        {HistogramSet::Unvalidated, "Unvalidated", "Unvalidated"},
        {HistogramSet::Validated, "Validated", "Validated"},
        {HistogramSet::Selected, "Selected", "Selected"}
    }};

    inline string propertyName(Physics::ParticleProperty property) { return Physics::particlePropertyName(property); }

    inline string propertyName(Physics::EventProperty property) { return Physics::eventPropertyName(property); }

    inline string propertyAlias(Physics::ParticleProperty property) {
        switch (property) {
            case Physics::ParticleProperty::Mass_Invariant: return "Mass";
            case Physics::ParticleProperty::Energy_Net:     return "Energy";
            default:                                       return propertyName(property);
        }
    }

    inline string propertyAlias(Physics::EventProperty property) { return propertyName(property); }

    inline const char* levelName(Config::RangeSize level) {
        switch (level) {
            case Config::RangeSize::Minute:   return "Minute";
            case Config::RangeSize::Small:    return "Small";
            case Config::RangeSize::Moderate: return "Moderate";
            case Config::RangeSize::Large:    return "Large";
            case Config::RangeSize::Extreme:  return "Extreme";
        }
        return "Unknown";
    }

}