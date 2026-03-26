#pragma once

#include <atomic>
#include <chrono>
#include <filesystem>
#include <string>

#include "TFile.h"
#include "TString.h"

#include </opt/homebrew/Cellar/tomlplusplus/3.4.0/include/toml++/toml.hpp>

namespace Config {
    using TimePoint = std::chrono::system_clock::time_point;
    using uSeconds  = std::chrono::microseconds;

    struct Log {
        std::atomic<Int_t> iEvent = 0;
        Int_t              serial = 0;
        Int_t              nEvents = 100;
        Int_t              nRealEvents = 0;
        Int_t              nDigits = 0;
        Int_t              printInterval = 10;
        Int_t              barInterval = 50;
        TimePoint          start = TimePoint{};
        uSeconds           elapsed = uSeconds(0);
    };

    struct Root {
        TFile*  outFile       = nullptr;
        TString rootDirectory = "output/Lambda_Reconstruction/";
        TString logDirectory  = "output/Lambda_Reconstruction/params/";
        TString beamEnergy    = "";
        TString outName       = "";
        TString logName       = "";
        TString fileTitle     = "";
        Int_t   binCount      = 100;
        Double_t histScale    = 100;
    };

    inline void extractParameters(
        const std::string& project,
        Log& logging,
        Root& root
    ) {
        toml::table config = toml::parse_file("configs/" + project + ".toml");

        logging.serial        = config["run"]["serial"].value_or(0);
        logging.nEvents       = config["run"]["event_count"].value_or(1000);
        logging.printInterval = config["run"]["print_interval"].value_or(100);

        root.binCount  = config["run"]["bin_count"].value_or(100);
        root.histScale = config["run"]["hist_scaling"].value_or(1.0);

        root.rootDirectory =
            config["paths"]["directory"].value_or(std::string("output/" + project + "/")).c_str();
        root.logDirectory =
            config["paths"]["output_log_directory"].value_or(std::string("output/" + project + "/params/")).c_str();

        const std::string filePrefix = config["file"]["prefix"].value_or(std::string("Unspecified"));
        const bool        fileSerial = config["file"]["serial"].value_or(true);
        const bool        fileEnergy = config["file"]["energy"].value_or(true);
        const bool        fileEvents = config["file"]["events"].value_or(true);

        std::string fileTitle = filePrefix;

        if (fileSerial) {
            fileTitle += Form("_%02d", logging.serial);
        }
        if (fileEnergy) {
            fileTitle += "_" + std::string(root.beamEnergy.Data()) + "GeV";
        }
        if (fileEvents) {
            fileTitle += "_" + std::to_string(logging.nEvents);
        }

        root.fileTitle = fileTitle.c_str();
        root.outName   = Form("%s%s.root", root.rootDirectory.Data(), fileTitle.c_str());
        root.logName   = Form("%s%s.log", root.logDirectory.Data(), fileTitle.c_str());

        std::filesystem::create_directories(root.rootDirectory.Data());
        std::filesystem::create_directories(root.logDirectory.Data());

        root.outFile = new TFile(root.outName, "RECREATE");
    }
}
