#pragma once

// ── Phys/Jets.hh ─────────────────────────────────────────────────────────────
// A jet definition from a string, and clustering a set of four-vectors with it (13 §2).
//
// `jetDefinition("antikt:0.4")` is the whole point: a module, a config or a study axis can name a
// jet algorithm in one field, and the answer is a `fastjet::JetDefinition` identical to the one
// written out by hand. `analyses/PhotoProduction/photo_eic.cc` writes three of them by hand, and the
// SISCone one takes six lines and a comment about a leak, which is the argument for this file.
//
// **The grammar is `algorithm:R` and then `key=value` parts**, in any order:
//
//     kt:1.0                     anti-kT and kT with a radius
//     antikt:0.4                 — the two-field form nearly everything uses
//     antikt:0.4:scheme=Et       a recombination scheme, when E (the default) is not wanted
//     siscone:0.7:overlap=0.75   the plugin's own parameter
//     genkt:0.4:p=-1             generalised kT, which is anti-kT at p = −1
//
// Positional parameters past the radius would mean `siscone:0.7:0.75` and `genkt:0.4:-1` looked
// alike and meant different things, so they are named instead.
//
// **A plugin is owned by the definition it is given to.** `JetDefinition` does not take ownership
// unless it is told to, and 00/B25 recorded that leak: one SISCone plugin per run, or per worker in
// a sharded one. `delete_plugin_when_unused()` is called here so a caller cannot forget.
//
// **Nothing here is thread-safe**, and `threadSafe()` says so rather than leaving it to be found:
// SISCone keeps its clustering cache and its RNG in process-wide statics in every build, and this
// FastJet is compiled without even limited thread safety (00/B31). The Rivet analyzer refuses to shard
// for the same reason.

#include <algorithm>
#include <cctype>
#include <string>
#include <vector>

#include "fastjet/ClusterSequence.hh"
#include "fastjet/JetDefinition.hh"
#include "fastjet/PseudoJet.hh"
#include "fastjet/SISConePlugin.hh"

#include "Core/Errors.hh"
#include "Phys/Types.hh"

namespace Phys {

    namespace detail {

        inline std::vector<std::string> splitOn(const std::string& text, char separator) {
            std::vector<std::string> parts;
            std::string current;
            for (const char character : text) {
                if (character == separator) {
                    parts.push_back(current);
                    current.clear();
                } else {
                    current.push_back(character);
                }
            }
            parts.push_back(current);
            return parts;
        }

        inline std::string lowered(std::string text) {
            std::transform(text.begin(), text.end(), text.begin(),
                           [](unsigned char character) {
                               return static_cast<char>(std::tolower(character));
                           });
            return text;
        }

        inline double asNumber(const std::string& text, const std::string& what,
                               const std::string& whole) {
            try {
                std::size_t used = 0;
                const double value = std::stod(text, &used);
                if (used == text.size()) return value;
            } catch (const std::exception&) {
            }
            throw Core::Error{Core::Exit::Config,
                              "'" + whole + "': " + what + " is not a number ('" + text + "')"};
        }

    }  // namespace detail

    /// The algorithms this accepts, and the spellings for each.
    inline fastjet::JetAlgorithm jetAlgorithm(const std::string& name) {
        const std::string key = detail::lowered(name);
        if (key == "kt") return fastjet::kt_algorithm;
        if (key == "antikt" || key == "anti-kt" || key == "akt")
            return fastjet::antikt_algorithm;
        if (key == "ca" || key == "cambridge" || key == "cambridge-aachen" || key == "aachen")
            return fastjet::cambridge_algorithm;
        if (key == "genkt" || key == "gen-kt") return fastjet::genkt_algorithm;
        if (key == "eekt" || key == "ee-kt") return fastjet::ee_kt_algorithm;
        if (key == "siscone") return fastjet::plugin_algorithm;
        throw Core::Error{Core::Exit::Config, "no jet algorithm called '" + name + "'",
                          "one of: kt, antikt, ca, genkt, eekt, siscone"};
    }

    inline fastjet::RecombinationScheme recombinationScheme(const std::string& name) {
        const std::string key = detail::lowered(name);
        if (key == "e" || key == "e_scheme") return fastjet::E_scheme;
        if (key == "pt" || key == "pt_scheme") return fastjet::pt_scheme;
        if (key == "et" || key == "et_scheme") return fastjet::Et_scheme;
        if (key == "bipt" || key == "bipt_scheme") return fastjet::BIpt_scheme;
        if (key == "wta_pt" || key == "wta-pt") return fastjet::WTA_pt_scheme;
        throw Core::Error{Core::Exit::Config, "no recombination scheme called '" + name + "'",
                          "one of: E, pt, Et, BIpt, WTA_pt"};
    }

    /// `"<algorithm>:<R>[:key=value]...`. See the header for the grammar.
    inline fastjet::JetDefinition jetDefinition(const std::string& text) {
        const std::vector<std::string> parts = detail::splitOn(text, ':');
        if (parts.size() < 2 || parts[0].empty())
            throw Core::Error{Core::Exit::Config, "'" + text + "' is not a jet definition",
                              "the form is <algorithm>:<R>, for example antikt:0.4"};

        const fastjet::JetAlgorithm algorithm = jetAlgorithm(parts[0]);
        const double radius = detail::asNumber(parts[1], "the radius", text);
        if (!(radius > 0.0))
            throw Core::Error{Core::Exit::Config,
                              "'" + text + "': a jet radius must be greater than zero"};

        fastjet::RecombinationScheme scheme = fastjet::E_scheme;
        bool scheme_given = false;
        double power = -1.0;      // genkt's p; anti-kT when it is not given
        double overlap = 0.75;    // SISCone's overlap threshold, its own long-standing default

        for (std::size_t index = 2; index < parts.size(); ++index) {
            const std::string& part = parts[index];
            if (part.empty()) continue;
            const std::size_t equals = part.find('=');
            if (equals == std::string::npos)
                throw Core::Error{Core::Exit::Config,
                                  "'" + text + "': '" + part + "' is not key=value",
                                  "parameters past the radius are named: scheme=, p=, overlap="};
            const std::string key = detail::lowered(part.substr(0, equals));
            const std::string value = part.substr(equals + 1);
            if (key == "scheme") {
                scheme = recombinationScheme(value);
                scheme_given = true;
            } else if (key == "p" || key == "power") {
                power = detail::asNumber(value, "the genkt power", text);
            } else if (key == "overlap") {
                overlap = detail::asNumber(value, "the overlap threshold", text);
            } else {
                throw Core::Error{Core::Exit::Config,
                                  "'" + text + "': no jet parameter called '" + key + "'",
                                  "one of: scheme, p, overlap"};
            }
        }

        if (algorithm == fastjet::plugin_algorithm) {
            // SISCone. The plugin is heap-allocated because `JetDefinition` keeps a pointer to it;
            // `delete_plugin_when_unused` is what makes that not a leak (00/B25).
            auto* plugin = new fastjet::SISConePlugin(radius, overlap);
            plugin->set_use_jet_def_recombiner(true);
            fastjet::JetDefinition definition(plugin);
            definition.delete_plugin_when_unused();
            if (scheme_given) definition.set_recombination_scheme(scheme);
            return definition;
        }
        if (algorithm == fastjet::genkt_algorithm)
            return fastjet::JetDefinition(algorithm, radius, power, scheme);
        return fastjet::JetDefinition(algorithm, radius, scheme);
    }

    /// Whether this definition may be used from more than one thread at a time. Always false here,
    /// and the reason is in the header note — it is a property of the build, not of the algorithm.
    inline bool threadSafe(const fastjet::JetDefinition& definition) {
#if defined(FASTJET_HAVE_LIMITED_THREAD_SAFETY)
        // Even then, not for SISCone: its cache and RNG are process-wide statics in every build.
        return definition.jet_algorithm() != fastjet::plugin_algorithm;
#else
        (void)definition;
        return false;
#endif
    }

    /// What FastJet itself calls this definition — the honest way to compare two of them, since
    /// `JetDefinition` has no equality operator.
    inline std::string describe(const fastjet::JetDefinition& definition) {
        return definition.description();
    }

    // ── clustering ───────────────────────────────────────────────────────────

    inline fastjet::PseudoJet pseudoJet(const FourVector& momentum) {
        return fastjet::PseudoJet(momentum.px(), momentum.py(), momentum.pz(), momentum.e());
    }

    inline FourVector fourVector(const fastjet::PseudoJet& jet) {
        return FourVector{jet.px(), jet.py(), jet.pz(), jet.e()};
    }

    inline std::vector<fastjet::PseudoJet> pseudoJets(const std::vector<FourVector>& momenta) {
        std::vector<fastjet::PseudoJet> made;
        made.reserve(momenta.size());
        for (const FourVector& momentum : momenta) made.push_back(pseudoJet(momentum));
        return made;
    }

    /// Cluster, and give back the inclusive jets above `pt_min`, hardest first.
    ///
    /// The `ClusterSequence` is deleted when this returns, which is why the jets come back as
    /// four-vectors rather than as `PseudoJet`s: a `PseudoJet` that outlives its sequence still
    /// answers for its momentum but throws the moment anything asks for its constituents, and that
    /// is a trap to hand a module. A module that wants constituents owns the sequence itself.
    inline std::vector<FourVector> cluster(const std::vector<FourVector>& momenta,
                                           const fastjet::JetDefinition& definition,
                                           double pt_min = 0.0) {
        if (momenta.empty()) return {};
        fastjet::ClusterSequence sequence(pseudoJets(momenta), definition);
        const std::vector<fastjet::PseudoJet> jets =
            fastjet::sorted_by_pt(sequence.inclusive_jets(pt_min));
        std::vector<FourVector> found;
        found.reserve(jets.size());
        for (const fastjet::PseudoJet& jet : jets) found.push_back(fourVector(jet));
        return found;
    }

}  // namespace Phys
