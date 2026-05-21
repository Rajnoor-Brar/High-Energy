#pragma once

#include <atomic>
#include <chrono>
#include <functional>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <string>

#include "TString.h"

#include "Config/Types.hh"
#include "Record/Writer.hh"
#include "Utility/Number.hh"
#include "Utility/Time.hh"
#include "Monitor/Methods.hh"
#include "Monitor/Render.hh"

namespace Monitor {

    inline void writeTextFile(const TString& path, const std::string& text) {
        std::ofstream stream(path.Data(), std::ios::trunc);
        stream << text;
    }

    inline std::string buildLogText(const Record::Writer& writer,
                                    const Config::Watch& logging,
                                    const std::string& programLog = {},
                                    const std::function<void()>& printStats = {},
                                    const std::function<void()>& listChangedSettings = {},
                                    const PacingInfo* pacing = nullptr)
    {
        std::ostringstream logStream;
        const time_t localStart = std::chrono::system_clock::to_time_t(logging.start);
        const Record::Paths&       paths = writer.paths();
        const Record::HistConfig&  hist  = writer.histConfig();

        logStream << "Serial                        : " << std::setw(2) << std::setfill('0') << paths.serial << '\n';
        logStream << "Beam Energy                   : " << paths.beamEnergy.Data() << '\n';
        logStream << "Event Count                   : " << Utility::numberFormat(logging.nEvents, 0) << '\n';
        logStream << "Real Event Count              : " << Utility::numberFormat(logging.n_real_events.load(std::memory_order_relaxed), 0) << '\n';
        logStream << "Last Run                      : " << Utility::timeString(localStart, false) << '\n';
        logStream << "Time Taken                    : " << Utility::durationString(logging.elapsed.load(std::memory_order_relaxed)) << '\n';
        logStream << "Time Taken / 1000 Events      : " << Utility::durationString((1000 * logging.elapsed.load(std::memory_order_relaxed)) / logging.nEvents, true) << '\n';
        logStream << "Histogram Scale               : " << hist.histScale << '\n';
        if (pacing) {
            logStream << "Status Snapshot Interval (ms) : " << Utility::numberFormat(pacing->heartbeatMs.count(), 0) << '\n';
            logStream << "Progress Bar Update Interval  : " << Utility::numberFormat(pacing->barInterval, 0) << '\n';
        }

        if (!programLog.empty()) {
            logStream << programLog;
            if (programLog.back() != '\n') logStream << '\n';
        }

        std::ostringstream capturedOutput;
        {
            std::lock_guard<std::mutex> terminalLock(terminalMutex());
            std::streambuf* oldStream = std::cout.rdbuf(capturedOutput.rdbuf());
            std::cout << "\n\n\n";
            if (listChangedSettings) listChangedSettings();
            std::cout << "\n\n\n";
            if (printStats) printStats();
            std::cout.rdbuf(oldStream);
        }

        logStream << capturedOutput.str();
        return logStream.str();
    }

    inline void outputLog(const Record::Writer& writer,
                          const Config::Watch& logging,
                          const std::string& programLog = {},
                          const TString& logPath = "",
                          const std::function<void()>& printStats = {},
                          const std::function<void()>& listChangedSettings = {},
                          const PacingInfo* pacing = nullptr)
    {
        const TString targetLogPath = logPath.Length() > 0 ? logPath : writer.paths().logName;
        writeTextFile(targetLogPath,
                      buildLogText(writer, logging, programLog, printStats, listChangedSettings, pacing));
    }

    inline std::string buildEmergencyLogText(const Record::Writer& writer,
                                             const Config::Watch& logging,
                                             const RunSnapshot& snapshot,
                                             const std::string& programLog = {},
                                             const std::string& reason = {})
    {
        std::ostringstream stream;
        const Record::Paths& paths = writer.paths();
        stream << "Emergency Shutdown            : fatal stall\n";
        if (!reason.empty()) stream << "Emergency Detail              : " << reason << '\n';
        stream << "Serial                        : " << std::setw(2) << std::setfill('0') << writer.paths().serial << '\n';
        stream << "Beam Energy                   : " << paths.beamEnergy.Data() << '\n';
        stream << "File Title                    : " << paths.fileTitle.Data() << '\n';
        stream << "Root Output                   : " << paths.outName.Data() << '\n';
        stream << "Main Log                      : " << paths.logName.Data() << '\n';
        stream << "RunStat Log                   : " << paths.runStatName.Data() << '\n';
        stream << "Last Event                    : " << Utility::numberFormat(snapshot.eventIndex, 0)
               << " / " << Utility::numberFormat(snapshot.nEvents, 0) << '\n';
        stream << "Real Event Count              : " << Utility::numberFormat(snapshot.nRealEvents, 0) << '\n';
        stream << "Phase                         : " << phaseString(snapshot.phase) << '\n';
        stream << "Elapsed                       : " << Utility::durationString(logging.elapsed.load(std::memory_order_relaxed), true) << '\n';
        stream << "Last Update                   : " << Utility::timeString(snapshot.lastUpdateTime, false) << '\n';
        writeStallFields(stream, snapshot);
        if (!programLog.empty()) {
            stream << programLog;
            if (programLog.back() != '\n') stream << '\n';
        }
        return stream.str();
    }

    inline void writeEmergencyLog(const Record::Writer& writer,
                                  const Config::Watch& logging,
                                  const RunSnapshot& snapshot,
                                  const std::string& programLog = {},
                                  const std::string& reason = {})
    {
        writeTextFile(writer.paths().logName,
                      buildEmergencyLogText(writer, logging, snapshot, programLog, reason));
    }

    inline void terminalReport(const Record::Writer& writer,
                               Config::Watch& logging,
                               const std::function<void()>& printStats = {},
                               bool stats = false) {
        std::lock_guard<std::mutex> terminalLock(terminalMutex());
        std::cout << "\n\n\n";
        if (stats && printStats) {
            printStats();
            std::cout << "\n\n";
        }
        const Config::TimePoint now = std::chrono::system_clock::now();
        logging.elapsed.store(std::chrono::duration_cast<Config::uSeconds>(now - logging.start),
                              std::memory_order_relaxed);
        std::cout << "Finished :\n" << std::string(10, ' ')
                  << Utility::timeString(now)
                  << "\n" << std::string(10, ' ')
                  << Utility::durationString(logging.elapsed.load(std::memory_order_relaxed)) << std::endl;
        std::cout << "\nFile : " << writer.paths().outName.Data() << std::endl << std::endl;
    }

}
