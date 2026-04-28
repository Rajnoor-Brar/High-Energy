#pragma once

#include <exception>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "Config.hh"
#include "Probe/Event.hh"

namespace Probe {

    template<typename Callback>
    inline void runParallel(const std::string& filepath,
                             const std::vector<CollectionSpec>& collections,
                             const std::vector<ScalarSpec>&     scalars,
                             Callback&& callback,
                             std::size_t nThreads = 0,
                             std::size_t nEventsHint = 0)
    {
        detail::enableRootThreadSafety();

        bool anyFlat = false, anyVec = false;
        for (const auto& cs : collections) {
            if (cs.indexBranches.empty()) anyVec = true; else anyFlat = true;
        }
        if (anyFlat && anyVec)
            throw std::runtime_error("[Probe] runParallel: cannot mix Flat and Vec collections");

        if (anyVec) {
            const std::size_t threads = nThreads > 0 ? nThreads : Config::resolveThreadCount(0);

            TFile* sf = TFile::Open(filepath.c_str(), "READ");
            if (!sf || sf->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + filepath + "'");
            TTree* t0 = dynamic_cast<TTree*>(sf->Get(collections[0].tree.c_str()));
            const Long64_t total = t0 ? t0->GetEntries() : 0;
            sf->Close(); delete sf;

            if (total == 0) return;

            const Long64_t chunk = (total + static_cast<Long64_t>(threads) - 1) / static_cast<Long64_t>(threads);
            std::vector<detail::Partition> parts;
            for (Long64_t start = 0; start < total; start += chunk)
                parts.push_back({start, std::min(total - 1, start + chunk - 1)});

            std::vector<std::thread>        workers;
            std::vector<std::exception_ptr> errors(parts.size());
            workers.reserve(parts.size());
            for (std::size_t t = 0; t < parts.size(); ++t) {
                workers.emplace_back([&, t]{
                    try {
                        EventStream stream(filepath, collections, scalars,
                                           parts[t].firstEvent, parts[t].lastEvent);
                        while (stream.next()) callback(stream.event(), static_cast<int>(t));
                    } catch (...) { errors[t] = std::current_exception(); }
                });
            }
            for (auto& w : workers) w.join();
            for (auto& e : errors)  if (e) std::rethrow_exception(e);
            return;
        }

        const std::size_t threads = nThreads > 0 ? nThreads : Config::resolveThreadCount(0);
        std::vector<detail::Partition> parts;

        if (nEventsHint > 0) {
            const Long64_t total    = static_cast<Long64_t>(nEventsHint);
            if (total <= 0) return;
            const Long64_t firstKey = detail::probeFirstKey(filepath, collections);
            const Long64_t lastKey  = firstKey + total - 1;
            const Long64_t chunk    = (total + static_cast<Long64_t>(threads) - 1)
                                    / static_cast<Long64_t>(threads);
            for (Long64_t start = firstKey; start <= lastKey; start += chunk)
                parts.push_back({start, std::min(lastKey, start + chunk - 1)});
        } else {
            TFile* sf = TFile::Open(filepath.c_str(), "READ");
            if (!sf || sf->IsZombie())
                throw std::runtime_error("[Probe] Failed to open file '" + filepath + "'");

            std::set<Long64_t> keySet;
            for (const auto& cs : collections)
                if (!cs.indexBranches.empty())
                    detail::scanIndexBranch(sf, cs.tree, cs.indexBranches[0], keySet, filepath);
            sf->Close(); delete sf;

            const std::vector<Long64_t> keys(keySet.begin(), keySet.end());
            if (keys.empty()) return;
            parts = detail::partitionEvents(keys, threads);
        }

        std::vector<std::thread>        workers;
        std::vector<std::exception_ptr> errors(parts.size());
        workers.reserve(parts.size());
        for (std::size_t t = 0; t < parts.size(); ++t) {
            workers.emplace_back([&, t]{
                try {
                    EventStream stream(filepath, collections, scalars,
                                       parts[t].firstEvent, parts[t].lastEvent,
                                       nEventsHint);
                    while (stream.next()) callback(stream.event(), static_cast<int>(t));
                } catch (...) { errors[t] = std::current_exception(); }
            });
        }
        for (auto& w : workers) w.join();
        for (auto& e : errors)  if (e) std::rethrow_exception(e);
    }

    // Convenience overload — no scalars
    template<typename Callback>
    inline void runParallel(const std::string& filepath,
                             const std::vector<CollectionSpec>& collections,
                             Callback&& callback,
                             std::size_t nThreads = 0,
                             std::size_t nEventsHint = 0)
    {
        runParallel(filepath, collections, {}, std::forward<Callback>(callback), nThreads, nEventsHint);
    }

    // [MEMORY WARNING] Loads all events into RAM — unsafe for large files
    inline std::vector<Event> readAllParallel(const std::string& filepath,
                                               const std::vector<CollectionSpec>& collections,
                                               const std::vector<ScalarSpec>&     scalars = {},
                                               std::size_t nThreads = 0)
    {
        detail::enableRootThreadSafety();
        std::vector<Event> out;
        std::mutex mtx;
        runParallel(filepath, collections, scalars,
            [&](const Event& ev, int) {
                std::lock_guard<std::mutex> lk(mtx);
                out.push_back(ev);
            }, nThreads);
        return out;
    }

} // namespace Probe
