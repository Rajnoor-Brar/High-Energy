#pragma once

#include <stdexcept>
#include <string>

#include "TFile.h"
#include <toml++/toml.hpp>

#include "Config/Types.hh"
#include "Config/TypeAid.hh"
#include "Config/LimitAid.hh"
#include "Config/Defaults.hh"
#include "Config/Reader.hh"

namespace Config {

    inline void configuration(const std::string& configPath,
                              const std::string& project,
                              Events&   events,
                              Watch&    watch,
                              Register& reg)
    {
        loadMonitorDefaults(watch, reg);
        limitExtractor(configPath, reg);

        toml::table config = toml::parse_file(configPath);

        readEventsSection(config, events, watch);
        readInputSection (config, reg);
        readRecordSection(config, watch, reg);
        readLogSection   (config, watch, reg);

        watch.nDigits = std::to_string(watch.nEvents).size();
        sanitiseLoggingConfig(watch);

        readPathsAndFile(config, project, watch, reg);
    }

    inline void configuration(const std::string& configPath,
                              const std::string& project,
                              Watch&    watch,
                              Register& reg)
    {
        Events events;
        configuration(configPath, project, events, watch, reg);
    }

    // PythiaT accepts both Pythia8::Pythia and Pythia8::PythiaParallel.
    template<typename PythiaT>
    inline void configurePythia(const std::string& configPath,
                                const std::string& project,
                                Events&   events,
                                Watch&    watch,
                                Register& reg,
                                PythiaT&  pythia)
    {
        configuration(configPath, project, events, watch, reg);

        toml::table config = toml::parse_file(configPath);
        PythiaConfig py;
        readPythiaSection(config, py);

        if (!py.cmndFile.empty()) pythia.readFile(py.cmndFile);
        if (py.seed != 0) pythia.readString("Random:seed = " + std::to_string(py.seed));
        
        if (py.beamEnergy > 0) {
            pythia.readString("Beams:eCM = " + std::to_string(py.beamEnergy));
            reg.beamEnergy = Form("%.0f", py.beamEnergy);
        }
    }

    inline void configureProbe(const std::string& configPath,
                               const std::string& project,
                               Events&      events,
                               Watch&       watch,
                               Register&    reg,
                               ProbeConfig& probe)
    {
        configuration(configPath, project, events, watch, reg);

        toml::table config = toml::parse_file(configPath);
        readProbeSection(config, probe);
    }

    inline void openOutputFile(Register& reg) {
        if (reg.outFile != nullptr) {
            reg.outFile->Close();
            delete reg.outFile;
            reg.outFile = nullptr;
        }
        reg.outFile = new TFile(reg.outName, "RECREATE");
        if (reg.outFile == nullptr || reg.outFile->IsZombie())
            throw std::runtime_error("Failed to create ROOT output file: " + std::string(reg.outName.Data()));
    }

    inline void extractConfiguration(const std::string& configPath,
                                     const std::string& project,
                                     Watch&    watch,
                                     Register& reg)
    {
        configuration(configPath, project, watch, reg);
    }
}
