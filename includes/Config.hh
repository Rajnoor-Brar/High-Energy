#pragma once

#include <atomic>
#include <chrono>
#include <filesystem>
#include <string>

#include "TFile.h"
#include "TString.h"

#include <toml++/toml.hpp>

namespace Config {
    using TimePoint = std::chrono::system_clock::time_point;
    using uSeconds  = std::chrono::microseconds;

    struct Log {
        std::atomic<std::size_t> iEvent{0};
        Int_t                    serial = 0;
        std::size_t              srPadding = 2;
        std::size_t              nEvents = 100;
        std::size_t              nRealEvents = 0;
        std::size_t              nDigits = 0;
        std::size_t              printInterval = 10;
        std::size_t              statusIntervalMs = 1000;
        std::size_t              barInterval = 50;
        std::size_t              checkInterval = 10000;

        TimePoint          start = TimePoint{};
        uSeconds           elapsed = uSeconds(0);
    };

    struct Root {
        TFile*  outFile       = nullptr;
        TString rootDirectory = "output/Lambda_Reconstruction/";
        TString logDirectory  = "output/Lambda_Reconstruction/params/";
        TString checkpointDirectory = "output/Lambda_Reconstruction/checkpoints/";
        TString beamEnergy    = "";
        TString outName       = "";
        TString logName       = "";
        TString runStatName   = "";
        TString checkpointOutName = "";
        TString checkpointLogName = "";
        TString fileTitle     = "";
        Int_t   binCount      = 100;
        Double_t histScale    = 100;
    };

    inline void extractParameters(
        const std::string& configPath,
        const std::string& project,
        Log& logging,
        Root& root
    ) {
        toml::table config = toml::parse_file(configPath);

        logging.serial        = config["run"]["serial"].value_or(0);
        logging.srPadding     = static_cast<std::size_t>(config["run"]["sr_Padding"].value_or(2));
        logging.nEvents       = static_cast<std::size_t>(config["run"]["event_count"].value_or(1000));

        logging.printInterval = static_cast<std::size_t>(config["logging"]["print_interval"].value_or(100));
        logging.statusIntervalMs = static_cast<std::size_t>(
            config["logging"]["status_interval"].value_or(1000)
        );
        logging.checkInterval = static_cast<std::size_t>(config["logging"]["check_interval"].value_or(10000));
        root.binCount         =                          config["logging"]["bin_count"].value_or(100);
        root.histScale        =                          config["logging"]["hist_scaling"].value_or(1.0);

        std::size_t temp = logging.nEvents, nDigits = 0;
        while (temp > 0) { ++nDigits; temp /= 10; }; logging.nDigits = nDigits;

        root.rootDirectory =
            config["paths"]["directory"].value_or(std::string("output/" + project + "/")).c_str();
        root.logDirectory =
            config["paths"]["output_log_directory"].value_or(std::string("output/" + project + "/params/")).c_str();
        root.checkpointDirectory =
            config["paths"]["checkpoint_directory"].value_or(std::string("output/" + project + "/checkpoints/")).c_str();


        const std::string filePrefix = config["file"]["prefix"].value_or(std::string("Unspecified"));
        const bool        fileSerial = config["file"]["serial"].value_or(true);
        const bool        fileEnergy = config["file"]["energy"].value_or(true);
        const bool        fileEvents = config["file"]["events"].value_or(true);

        std::string fileTitle = filePrefix;

        std::string serial = std::string(Form(("_%0" + std::to_string(static_cast<int>(logging.srPadding)) + "d").c_str(), logging.serial));

        if (fileSerial) {
            fileTitle += serial;
        }
        if (fileEnergy) {
            fileTitle += "_" + std::string(root.beamEnergy.Data()) + "GeV";
        }
        if (fileEvents) {
            fileTitle += "_" + std::to_string(logging.nEvents);
        }

        root.fileTitle = fileTitle.c_str();
        root.outName   = Form("%s%s/%s.root", root.rootDirectory.Data(), serial.c_str(), fileTitle.c_str());
        root.logName   = Form("%s%s.log", root.logDirectory.Data(), fileTitle.c_str());
        root.runStatName = Form("%s%s_runstat.log", root.logDirectory.Data(), fileTitle.c_str());
        root.checkpointOutName = Form("%s%s_checkpoint.root", root.checkpointDirectory.Data(), fileTitle.c_str());
        root.checkpointLogName = Form("%s%s_checkpoint.log", root.checkpointDirectory.Data(), fileTitle.c_str());

        std::filesystem::create_directories(std::filesystem::path(root.outName.Data()).parent_path());
        std::filesystem::create_directories(std::filesystem::path(root.logName.Data()).parent_path());
        std::filesystem::create_directories(std::filesystem::path(root.runStatName.Data()).parent_path());
        std::filesystem::create_directories(std::filesystem::path(root.checkpointOutName.Data()).parent_path());
        std::filesystem::create_directories(std::filesystem::path(root.checkpointLogName.Data()).parent_path());

        root.outFile = new TFile(root.outName, "RECREATE");
    }
}
