#pragma once

// ── Probe/ConfigAid.hh ───────────────────────────────────────────────────────
// Parses the [probe] section of a TOML config file directly into
// Probe::CollectionSpec objects — without an intermediate Config type.
//
// Dependency direction: Probe → Physics, toml++   (no Config dependency here)
// Config/Reader.hh includes this header and calls parseCollectionsFromToml
// from readProbeSection.

#include <stdexcept>
#include <string>
#include <vector>

#include <toml++/toml.hpp>

#include "Probe/Types.hh"
#include "Probe/BranchControl.hh"

namespace Probe {

    // ── parseCollectionsFromToml ─────────────────────────────────────────────
    // Reads the [probe] event_particles array from a parsed TOML table and
    // returns one CollectionSpec per entry.
    //
    // Each entry in event_particles is a 5-element array:
    //   [ label, spec_id, tree_name, [[branch, type], ...], [[idx_branch, type], ...] ]
    //
    // spec_id: 0 = Cartesian (Px,Py,Pz,E), 1 = PtEtaPhiE, 2 = PtEtaPhiM
    // type codes: D=Double, F=Float, I=Int32, i=UInt32, L=Int64, l=UInt64, O=Bool

    inline std::vector<CollectionSpec>
    parseCollectionsFromToml(const toml::table& cfg)
    {
        std::vector<CollectionSpec> out;

        const auto* arr = cfg["probe"]["event_particles"].as_array();
        if (!arr) return out;

        for (const auto& entry : *arr) {
            const auto* row = entry.as_array();
            if (!row || row->size() < 5) continue;

            const std::string label    = (*row)[0].value_or(std::string{});
            const int         specId   = (*row)[1].value_or(0);
            const std::string treeName = (*row)[2].value_or(std::string{});

            // ── momenta branches ─────────────────────────────────────────────
            std::vector<BranchSpec> momentaBranches;
            if (const auto* momentaArr = (*row)[3].as_array()) {
                for (const auto& b : *momentaArr) {
                    if (const auto* pair = b.as_array(); pair && pair->size() == 2) {
                        momentaBranches.push_back({
                            pair->at(0).value_or(std::string{}),
                            BranchControl::detectType(pair->at(1).value_or(std::string{}))
                        });
                    }
                }
            }
            if (momentaBranches.size() != 4)
                throw std::runtime_error(
                    "[Probe] parseCollectionsFromToml: '" + label +
                    "' must have exactly 4 momenta branches, got " +
                    std::to_string(momentaBranches.size()));

            // ── coordinate spec ──────────────────────────────────────────────
            CoordSpec coords;
            switch (specId) {
                case 0: coords = CartesianSpec{ momentaBranches}; break;
                case 1: coords = PtEtaPhiESpec{momentaBranches}; break;
                case 2: coords = PtEtaPhiMSpec{momentaBranches}; break;
                default:
                    throw std::runtime_error(
                        "[Probe] parseCollectionsFromToml: invalid spec ID " +
                        std::to_string(specId) + " for '" + label + "'");
            }

            // ── index branches ───────────────────────────────────────────────
            std::vector<BranchSpec> indexBranches;
            if (const auto* indexArr = (*row)[4].as_array()) {
                for (const auto& b : *indexArr) {
                    if (const auto* pair = b.as_array(); pair && pair->size() == 2) {
                        indexBranches.push_back({
                            pair->at(0).value_or(std::string{}),
                            BranchControl::detectType(pair->at(1).value_or(std::string{}))
                        });
                    }
                }
            }

            CollectionSpec spec;
            spec.label         = label;
            spec.tree          = treeName;
            spec.coords        = std::move(coords);
            spec.indexBranches = std::move(indexBranches);
            out.push_back(std::move(spec));
        }
        return out;
    }

} // namespace Probe
