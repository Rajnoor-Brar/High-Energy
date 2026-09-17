#pragma once

#include <string>
#include <vector>

#include "Physics/Types.hh"

namespace Physics {

    inline std::string particlePropertyName(ParticleProperty p) {
        return traitsOf(p).name;
    }

    inline std::string eventPropertyName(EventProperty p) {
        return traitsOf(p).name;
    }

    inline Double_t valueOf(const Lorentz& particle, ParticleProperty p) {
        return traitsOf(p).extract(particle);
    }

    inline Double_t valueOf(const std::vector<Lorentz>& particles, EventProperty p) {
        return traitsOf(p).extract(particles);
    }

    inline Double_t multiplicityOf(const std::vector<Lorentz>& particles) {
        return static_cast<Double_t>(particles.size());
    }
}
