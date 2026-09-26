#pragma once
#include <array>
#include <optional>
#include <stdexcept>
#include <string>
#include <type_traits>

#include <toml++/toml.hpp>

#include "Config.hh"
#include "Record/Configs.hh"
#include "Types.hh"
#include "TypeAid.hh"

namespace Lambda {

    inline constexpr std::array<Physics::ParticleProperty, 6> Recorded_ParticleProperties = {
        Physics::ParticleProperty::Mass_Invariant,
        Physics::ParticleProperty::Energy_Net,
        Physics::ParticleProperty::Momentum_Net,
        Physics::ParticleProperty::Momentum_Transverse,
        Physics::ParticleProperty::Momentum_Z,
        Physics::ParticleProperty::Pseudorapidity
    };

    inline std::optional<Config::Bounds> explicitBounds(const toml::node& node) {
        if (!node.is_array()) return std::nullopt;

        const toml::array& array = *node.as_array();
        if (array.size() != 2) {
            throw std::runtime_error( "Expected exactly 2 numeric values in explicit histogram bounds");
        }

        const auto low  = array[0].value<Double_t>();
        const auto high = array[1].value<Double_t>();
        if (!low || !high) throw std::runtime_error("Expected numeric histogram bounds");

        return Config::Bounds{*low, *high};
    }

    inline const Config::Bounds& levelBounds(const Record::HistConfig& hist, Physics::ParticleProperty property, Config::RangeSize level) {
        const auto quantityIt = hist.particleLimits.find(property);
        if (quantityIt == hist.particleLimits.end()) {
            throw std::runtime_error( "No configured limits for particle property " + Physics::particlePropertyName(property));
        }

        const auto levelIt = quantityIt->second.find(level);
        if (levelIt == quantityIt->second.end()) {
            throw std::runtime_error( "No configured " + propertyAlias(property) + " limit for level " + Config::levelToString(level));
        }
        return levelIt->second;
    }

    inline const Config::Bounds& levelBounds(const Record::HistConfig& hist, Physics::EventProperty property, Config::RangeSize level) {
        const auto quantityIt = hist.eventLimits.find(property);
        if (quantityIt == hist.eventLimits.end()) {
            throw std::runtime_error( "No configured limits for event property " + Physics::eventPropertyName(property));
        }

        const auto levelIt = quantityIt->second.find(level);
        if (levelIt == quantityIt->second.end()) {
            throw std::runtime_error( "No configured " + propertyAlias(property) + " limit for level " + Config::levelToString(level));
        }
        return levelIt->second;
    }

    template <typename Property>
    inline std::optional<Config::Bounds> boundsFromNode(const toml::node& node, const Record::HistConfig& hist, Property property) {
        if (const auto bounds = explicitBounds(node)) return bounds;
        if (!node.is_string()) return std::nullopt;
        return levelBounds( hist, property, Config::stringToLevel(node.value<string>().value_or("")));
    }

    template <typename Property>
    inline Config::Bounds resolveBounds(const toml::table& table, const Record::HistConfig& hist, Property property, Config::RangeSize defaultLevel) {
        std::optional<Config::Bounds> resolved;
        const string primaryKey = [&]() {
            if constexpr (std::is_same_v<Property, Physics::ParticleProperty>)
                return Physics::particlePropertyName(property);
            else
                return Physics::eventPropertyName(property);
        }();
        const string aliasKey   = propertyAlias(property);

        if (const toml::node* node = table.get(primaryKey)) resolved = boundsFromNode(*node, hist, property);

        if (!resolved && aliasKey != primaryKey) {
            if (const toml::node* node = table.get(aliasKey)) resolved = boundsFromNode(*node, hist, property);
        }

        if (!resolved) resolved = levelBounds(hist, property, defaultLevel);

        return *resolved;
    }

}
