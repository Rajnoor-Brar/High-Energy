#pragma once

#include "Pythia8/Pythia.h"
#include "Pythia8/PythiaParallel.h"
#include "Math/Vector4D.h"
#include "Math/VectorUtil.h"
#include "TFile.h"
#include "TTree.h"
#include <chrono>
#include </opt/homebrew/Cellar/tomlplusplus/3.4.0/include/toml++/toml.hpp>
#include <type_traits>
#include <sys/ioctl.h>

#include "Config_Types.hh"
#include "Progress.hh"

void extract_Parameters( const std::string&   project,
                            Config::Analysis& analysis,
                            Config::Log&      logging,
                            Config::Root&     root) {
    toml::table config = toml::parse_file(std::string("configs/") + project + ".toml");

    namespace Filesystem = std::filesystem;

    // beamEnergy is handled elsewhere
    logging.serial = config["run"]["serial"].value_or(0);
    logging.nEvents = config["run"]["event_count"].value_or(1000);
    logging.printInterval = config["run"]["print_interval"].value_or(100);

    root.binCount = config["run"]["bin_count"].value_or(100);

    analysis.histScale = config["physics"]["hist_scaling"].value_or(1.0);
    analysis.EnergyTolerance = config["physics"]["delta_energy_gev"].value_or(0.1);
    analysis.MassTolerance = config["physics"]["delta_mass_gev"].value_or(0.1);
    analysis.ThetaTolerance = config["physics"]["delta_theta_rad"].value_or(0.1);

    root.rootDirectory =
        config["paths"]["directory"].value_or(std::string("output/" + project + "/")).c_str();

    root.logDirectory =
        config["paths"]["output_log_directory"].value_or(std::string("output/" + project + "/params/")).c_str();

    std::string filePrefix = config["file"]["prefix"].value_or("Unspecified");
    bool        fileSerial = config["file"]["serial"].value_or("true");
    bool        fileEnergy = config["file"]["energy"].value_or("true");
    bool        fileEvents = config["file"]["events"].value_or("true");


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

    root.outName = Form(
        "%s%s.root",
        root.rootDirectory.Data(),
        fileTitle.c_str()
    );

    root.logName = Form(
        "%s%s.log",
        root.logDirectory.Data(),
        fileTitle.c_str()
    );

    Filesystem::create_directories(root.rootDirectory.Data());
    Filesystem::create_directories(root.logDirectory.Data());

    root.outFile = new TFile(root.outName, "RECREATE");
}

template <typename PythiaT>
void terminalReport(
    PythiaT& pythia,
    const Config::Root& root,
    const Config::Analysis& analysis,
    Config::Log& logParams
) {
    std::cout<<"\n\n\n";
    pythia.stat();
    std::cout<<"\n\n";
   
    Config::TimePoint now =  std::chrono::system_clock::now();
    time_t localNow = std::chrono::system_clock::to_time_t(now);
    logParams.elapsed =  std::chrono::duration_cast<Config::uSeconds>(now - logParams.start);

    std::cout <<"Finished :\n"<<std::string(10, ' ')<< std::put_time(std::localtime(&localNow), "%F %T")
                           <<"\n"<<std::string(10, ' ')<< durationString(logParams.elapsed) << std::endl;
    std::cout <<"\nFile Title : "<< root.fileTitle.Data()<<std::endl<<std::endl;
}


template <typename PythiaT>
void outputLog(
    PythiaT& pythia,
    const Config::Root& root,
    const Config::Analysis& analysis,
    const Config::Log& logging
) {
    std::ofstream logStream(root.logName.Data(), std::ios::trunc);

    const time_t localStart = std::chrono::system_clock::to_time_t(logging.start);

    logStream << "Serial                        : " << std::setw(2) << std::setfill('0') << logging.serial << std::endl;
    logStream << "Beam Energy                   : " << root.beamEnergy.Data() << std::endl;
    logStream << "Event Count                   : " << logging.nEvents << std::endl;
    logStream << "Real Event Count              : " << logging.nRealEvents << std::endl;
    logStream << "Last Run                      : " << std::put_time(std::localtime(&localStart), "%F %T") << std::endl;
    logStream << "Time Taken                    : " << durationString(logging.elapsed) << std::endl;
    logStream << "Time Taken / 100 Events       : " << durationString((100 * logging.elapsed) / logging.nEvents) << std::endl;
    logStream << "Energy Tolerance              : " << analysis.EnergyTolerance << std::endl;
    logStream << "Mass Tolerance                : " << analysis.MassTolerance << std::endl;
    logStream << "Theta Tolerance               : " << analysis.ThetaTolerance << std::endl;
    logStream << "Progress Bar Update Interval  : " << logging.barInterval << std::endl;

    std::streambuf* oldStream = std::cout.rdbuf();
    std::cout.rdbuf(logStream.rdbuf());
    std::cout << "\n\n\n";

    if constexpr (std::is_same_v<PythiaT, Pythia8::Pythia>) {
        pythia.info.list();
        std::cout << "\n\n\n";
    }

    pythia.stat();
    std::cout.rdbuf(oldStream);
}

void pythiaAnalysis(
    Pythia8::Pythia& pythia,
    RootAnalysis::ValidatedArray& validated,
    const Config::Analysis& analysis,
    Config::Log& logging
) {
    using namespace RootAnalysis;
    namespace VectorUtil = ROOT::Math::VectorUtil;

    const Int_t eventIndex = ++logging.iEvent;
    ++logging.nRealEvents;
    
    static int wsCol = [] {
        struct winsize w{};
        ioctl(STDOUT_FILENO, TIOCGWINSZ, &w);
        return static_cast<int>(w.ws_col);
    }();


    const Int_t progGapInternal = std::max<Int_t>(1, logging.nEvents / std::max(1, wsCol - 6));

    Lorentz lambda;
    Lorentz proton, protonCM;
    Lorentz pion, pionCM;
    std::vector<Lorentz> protonList;
    std::vector<Lorentz> pionList;

    Bool_t energyCheck = false;
    Bool_t massCheck   = false;
    Bool_t thetaCheck  = false;
    Double_t theta     = 0.0;

    protonList.reserve(pythia.event.size());
    pionList.reserve(pythia.event.size());

    if (eventIndex == 1) {
        pythia.info.list();
        std::cout << std::flush;
    }

    if (eventIndex == 2) {
        std::cout << "\n\n\n";
        logging.elapsed = Chrono::duration_cast<uSeconds>(SysClock::now() - logging.start);
        printProgressStat(2, logging.nEvents, logging.nDigits, updatedETA(2, logging.nEvents, logging.elapsed));
        printProgressBar(0.01);
    }

    for (Int_t particle = 0; particle < pythia.event.size(); ++particle) {
        const auto& eventParticle = pythia.event[particle];

        if (eventParticle.id() == 2212) {
            proton = Lorentz(
                eventParticle.px(),
                eventParticle.py(),
                eventParticle.pz(),
                eventParticle.e()
            );
            protonList.push_back(proton);
        }
        else if (eventParticle.id() == -211) {
            pion = Lorentz(
                eventParticle.px(),
                eventParticle.py(),
                eventParticle.pz(),
                eventParticle.e()
            );
            pionList.push_back(pion);
        }
    }

    if (eventIndex % logging.printInterval == 0 || eventIndex == logging.nEvents) {
        logging.elapsed = Chrono::duration_cast<uSeconds>(SysClock::now() - logging.start);
        printProgressStat(
            eventIndex,
            logging.nEvents,
            logging.nDigits,
            updatedETA(eventIndex, logging.nEvents, logging.elapsed)
        );
    }

    if (eventIndex % progGapInternal == 0 || eventIndex == logging.nEvents) {
        printProgressBar(static_cast<double>(eventIndex) / logging.nEvents);
        logging.barInterval = progGapInternal;
    }

    resetAllCounts(validated);

    for (Int_t iProton = 0; iProton < static_cast<Int_t>(protonList.size()); ++iProton) {
        for (Int_t iPion = 0; iPion < static_cast<Int_t>(pionList.size()); ++iPion) {
            proton = protonList[iProton];
            pion   = pionList[iPion];
            lambda = proton + pion;

            fill(validated, ValidationBasis::Un, lambda);

            auto beta = lambda.BoostToCM();

            auto protonCM = VectorUtil::boost(proton, beta);
            auto pionCM   = VectorUtil::boost(pion, beta);

            theta =
                (protonCM.Px() * pionCM.Px() +
                 protonCM.Py() * pionCM.Py() +
                 protonCM.Pz() * pionCM.Pz()) /
                (protonCM.P() * pionCM.P());

            energyCheck =
                (lambda.E() > (analysis.lambdaMass - analysis.EnergyTolerance)) &&
                (lambda.E() < (analysis.lambdaMass + analysis.EnergyTolerance));

            massCheck =
                (lambda.M() > (analysis.lambdaMass - analysis.MassTolerance)) &&
                (lambda.M() < (analysis.lambdaMass + analysis.MassTolerance));

            thetaCheck =
                (theta > (-1 - std::cos(analysis.ThetaTolerance))) &&
                (theta < (-1 + std::cos(analysis.ThetaTolerance)));

            if (massCheck) {
                fill(validated, ValidationBasis::Mass, lambda);
            }
            if (energyCheck) {
                fill(validated, ValidationBasis::Energy, lambda);
            }
            if (thetaCheck) {
                fill(validated, ValidationBasis::Theta, lambda);
            }
            if (massCheck && energyCheck) {
                fill(validated, ValidationBasis::EnergyMass, lambda);
            }
            if (massCheck && thetaCheck) {
                fill(validated, ValidationBasis::MassTheta, lambda);
            }
            if (energyCheck && thetaCheck) {
                fill(validated, ValidationBasis::EnergyTheta, lambda);
            }
            if (energyCheck && massCheck && thetaCheck) {
                fill(validated, ValidationBasis::All, lambda);
            }
        }
    }

    countAll(validated);
}
