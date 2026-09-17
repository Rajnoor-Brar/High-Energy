#pragma once

#include <optional>
#include <stdexcept>
#include <string>

#include "Physics/Types.hh"

namespace Physics {

    inline const char* particlePropertyToString(ParticleProperty p) {
        return traitsOf(p).name;
    }

    inline const char* eventPropertyToString(EventProperty p) {
        return traitsOf(p).name;
    }

    inline ParticleProperty stringToParticleProperty(const std::string& s) {
        if (s == "Mass_Invariant" || s == "Mass")   return ParticleProperty::Mass_Invariant;
        if (s == "Mass_Transverse")                 return ParticleProperty::Mass_Transverse;
        if (s == "Energy_Net"     || s == "Energy") return ParticleProperty::Energy_Net;
        if (s == "Energy_Transverse")               return ParticleProperty::Energy_Transverse;
        if (s == "Momentum_Net")                    return ParticleProperty::Momentum_Net;
        if (s == "Momentum_Transverse")             return ParticleProperty::Momentum_Transverse;
        if (s == "Momentum_X")                      return ParticleProperty::Momentum_X;
        if (s == "Momentum_Y")                      return ParticleProperty::Momentum_Y;
        if (s == "Momentum_Z")                      return ParticleProperty::Momentum_Z;
        if (s == "Rapidity")                        return ParticleProperty::Rapidity;
        if (s == "Pseudorapidity")                  return ParticleProperty::Pseudorapidity;
        if (s == "Azimuthal_Angle")                 return ParticleProperty::Azimuthal_Angle;
        throw std::runtime_error("Unknown particle property: " + s);
    }

    inline EventProperty stringToEventProperty(const std::string& s) {
        if (s == "Multiplicity") return EventProperty::Multiplicity;
        throw std::runtime_error("Unknown event property: " + s);
    }

    inline std::optional<ParticleProperty> tryStringToParticleProperty(const std::string& s) {
        try { return stringToParticleProperty(s); } catch (...) { return std::nullopt; }
    }

    inline std::optional<EventProperty> tryStringToEventProperty(const std::string& s) {
        try { return stringToEventProperty(s); } catch (...) { return std::nullopt; }
    }
}
