#pragma once

#include <algorithm>
#include <cstddef>
#include <exception>
#include <future>
#include <limits>
#include <mutex>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

#include "Analysis.hh"
#include "Config.hh"
#include "TFile.h"
#include "TROOT.h"
#include "TTree.h"

namespace Explore {
    using Lorentz = Analysis::Lorentz;

    struct Event {
        Int_t                eventIndex{-1};
        std::vector<Lorentz> protons;
        std::vector<Lorentz> pions;
    };

    class EventStream {
      public:
        static constexpr Int_t kIndexMin = std::numeric_limits<Int_t>::min();
        static constexpr Int_t kIndexMax = std::numeric_limits<Int_t>::max();

        explicit EventStream(const std::string& filepath,
                             const std::string& protonTree = "Protons",
                             const std::string& pionTree   = "Pions",
                             Int_t minEventIndex = kIndexMin,
                             Int_t maxEventIndex = kIndexMax)
            : minIdx_(minEventIndex), maxIdx_(maxEventIndex)
        {
            file_ = TFile::Open(filepath.c_str(), "READ");
            if (file_ == nullptr || file_->IsZombie())
                throw std::runtime_error("Explore: failed to open " + filepath);

            protons_ = dynamic_cast<TTree*>(file_->Get(protonTree.c_str()));
            pions_   = dynamic_cast<TTree*>(file_->Get(pionTree.c_str()));
            if (protons_ == nullptr || pions_ == nullptr)
                throw std::runtime_error("Explore: missing Protons/Pions tree in " + filepath);

            attachBranches(protons_, protonBuf_);
            attachBranches(pions_,   pionBuf_);

            protonEntries_ = protons_->GetEntries();
            pionEntries_   = pions_->GetEntries();

            primeCursor(protons_, protonBuf_, protonCursor_, protonEntries_);
            primeCursor(pions_,   pionBuf_,   pionCursor_,   pionEntries_);

            // Advance both cursors past any entries below minIdx_.
            seekToMin(protons_, protonBuf_, protonCursor_, protonEntries_, minIdx_);
            seekToMin(pions_,   pionBuf_,   pionCursor_,   pionEntries_,   minIdx_);

            nEvents_ = computeEventCount();
        }

        ~EventStream() {
            if (file_ != nullptr) {
                file_->Close();
                delete file_;
            }
        }

        EventStream(const EventStream&)            = delete;
        EventStream& operator=(const EventStream&) = delete;

        EventStream(EventStream&& other) noexcept { moveFrom(std::move(other)); }
        EventStream& operator=(EventStream&& other) noexcept {
            if (this != &other) {
                if (file_ != nullptr) { file_->Close(); delete file_; }
                moveFrom(std::move(other));
            }
            return *this;
        }

        // Advance to the next event. Returns false when both trees are exhausted.
        bool next() {
            const bool protonLeft = protonCursor_ < protonEntries_;
            const bool pionLeft   = pionCursor_   < pionEntries_;
            if (!protonLeft && !pionLeft) return false;

            const Int_t target = nextEventIndex();
            if (target > maxIdx_) return false;
            current_.eventIndex = target;
            current_.protons.clear();
            current_.pions.clear();

            drain(protons_, protonBuf_, protonCursor_, protonEntries_, target, current_.protons);
            drain(pions_,   pionBuf_,   pionCursor_,   pionEntries_,   target, current_.pions);

            ++index_;
            return true;
        }

        const Event& event()    const { return current_; }
        std::size_t  nEvents()  const { return nEvents_; }
        std::size_t  index()    const { return index_ == 0 ? 0 : index_ - 1; }

      private:
        struct ParticleBuf {
            Int_t    eventIndex{-1};
            Double_t energy{};
            Double_t px{};
            Double_t py{};
            Double_t pz{};
        };

        static void attachBranches(TTree* tree, ParticleBuf& buf) {
            tree->SetBranchStatus("*", 0);
            tree->SetBranchStatus("event_index", 1);
            tree->SetBranchStatus("Energy",      1);
            tree->SetBranchStatus("pX",          1);
            tree->SetBranchStatus("pY",          1);
            tree->SetBranchStatus("pZ",          1);
            tree->SetBranchAddress("event_index", &buf.eventIndex);
            tree->SetBranchAddress("Energy",      &buf.energy);
            tree->SetBranchAddress("pX",          &buf.px);
            tree->SetBranchAddress("pY",          &buf.py);
            tree->SetBranchAddress("pZ",          &buf.pz);
        }

        static void primeCursor(TTree* tree, ParticleBuf& buf, Long64_t& cursor, Long64_t total) {
            if (cursor < total) tree->GetEntry(cursor);
        }

        static void seekToMin(TTree* tree, ParticleBuf& buf, Long64_t& cursor,
                              Long64_t total, Int_t minIdx) {
            while (cursor < total && buf.eventIndex < minIdx) {
                ++cursor;
                if (cursor < total) tree->GetEntry(cursor);
            }
        }

        // Peek the smallest unconsumed event_index across the two trees.
        Int_t nextEventIndex() const {
            const bool protonLeft = protonCursor_ < protonEntries_;
            const bool pionLeft   = pionCursor_   < pionEntries_;
            if (protonLeft && pionLeft)
                return std::min(protonBuf_.eventIndex, pionBuf_.eventIndex);
            return protonLeft ? protonBuf_.eventIndex : pionBuf_.eventIndex;
        }

        // Consume all contiguous entries from cursor whose event_index == target.
        static void drain(TTree* tree, ParticleBuf& buf, Long64_t& cursor, Long64_t total,
                          Int_t target, std::vector<Lorentz>& out)
        {
            while (cursor < total && buf.eventIndex == target) {
                out.emplace_back(buf.px, buf.py, buf.pz, buf.energy);
                ++cursor;
                if (cursor < total) tree->GetEntry(cursor);
            }
        }

        // Count distinct event indices across both trees without consuming.
        // Uses a set to handle interleaved events correctly. O((N+M) log K).
        std::size_t computeEventCount() {
            std::set<Int_t> distinct;
            Int_t last = std::numeric_limits<Int_t>::min();
            for (Long64_t i = 0; i < protonEntries_; ++i) {
                protons_->GetEntry(i);
                const Int_t idx = protonBuf_.eventIndex;
                if (idx < minIdx_ || idx > maxIdx_) continue;
                if (idx != last) { last = idx; distinct.insert(last); }
            }
            last = std::numeric_limits<Int_t>::min();
            for (Long64_t i = 0; i < pionEntries_; ++i) {
                pions_->GetEntry(i);
                const Int_t idx = pionBuf_.eventIndex;
                if (idx < minIdx_ || idx > maxIdx_) continue;
                if (idx != last) { last = idx; distinct.insert(last); }
            }

            // Restore cursor entries for streaming.
            if (protonCursor_ < protonEntries_) protons_->GetEntry(protonCursor_);
            if (pionCursor_   < pionEntries_)   pions_->GetEntry(pionCursor_);
            return distinct.size();
        }

        void moveFrom(EventStream&& o) {
            file_          = o.file_;         o.file_    = nullptr;
            protons_       = o.protons_;      o.protons_ = nullptr;
            pions_         = o.pions_;        o.pions_   = nullptr;
            protonBuf_     = o.protonBuf_;
            pionBuf_       = o.pionBuf_;
            protonCursor_  = o.protonCursor_;
            pionCursor_    = o.pionCursor_;
            protonEntries_ = o.protonEntries_;
            pionEntries_   = o.pionEntries_;
            current_       = std::move(o.current_);
            index_         = o.index_;
            nEvents_       = o.nEvents_;
            minIdx_        = o.minIdx_;
            maxIdx_        = o.maxIdx_;
        }

        TFile* file_{};
        TTree* protons_{};
        TTree* pions_{};
        ParticleBuf protonBuf_{};
        ParticleBuf pionBuf_{};
        Long64_t protonCursor_{0};
        Long64_t pionCursor_{0};
        Long64_t protonEntries_{0};
        Long64_t pionEntries_{0};
        Event       current_{};
        std::size_t index_{0};
        std::size_t nEvents_{0};
        Int_t       minIdx_{std::numeric_limits<Int_t>::min()};
        Int_t       maxIdx_{std::numeric_limits<Int_t>::max()};
    };

    inline std::vector<Event> readAll(const std::string& filepath,
                                      const std::string& protonTree = "Protons",
                                      const std::string& pionTree   = "Pions")
    {
        EventStream stream(filepath, protonTree, pionTree);
        std::vector<Event> out;
        out.reserve(stream.nEvents());
        while (stream.next()) out.push_back(stream.event());
        return out;
    }

    namespace detail {
        struct Partition { Int_t firstEvent; Int_t lastEvent; };

        inline void enableRootThreadSafety() {
            static std::once_flag flag;
            std::call_once(flag, []{ ROOT::EnableThreadSafety(); });
        }

        inline std::vector<Int_t> collectEventIndices(const std::string& filepath,
                                                      const std::string& protonTree,
                                                      const std::string& pionTree)
        {
            TFile* file = TFile::Open(filepath.c_str(), "READ");
            if (file == nullptr || file->IsZombie())
                throw std::runtime_error("Explore: failed to open " + filepath);

            auto scan = [](TTree* tree, std::set<Int_t>& out) {
                if (tree == nullptr) return;
                Int_t eventIndex = -1;
                tree->SetBranchStatus("*", 0);
                tree->SetBranchStatus("event_index", 1);
                tree->SetBranchAddress("event_index", &eventIndex);
                const Long64_t n = tree->GetEntries();
                Int_t last = std::numeric_limits<Int_t>::min();
                for (Long64_t i = 0; i < n; ++i) {
                    tree->GetEntry(i);
                    if (eventIndex != last) { last = eventIndex; out.insert(last); }
                }
                tree->ResetBranchAddresses();
            };

            std::set<Int_t> distinct;
            scan(dynamic_cast<TTree*>(file->Get(protonTree.c_str())), distinct);
            scan(dynamic_cast<TTree*>(file->Get(pionTree.c_str())),   distinct);
            file->Close();
            delete file;

            return {distinct.begin(), distinct.end()};
        }

        inline std::vector<Partition> partitionEvents(const std::vector<Int_t>& indices,
                                                      std::size_t nThreads)
        {
            std::vector<Partition> parts;
            if (indices.empty() || nThreads == 0) return parts;
            const std::size_t n = indices.size();
            const std::size_t chunk = (n + nThreads - 1) / nThreads;
            for (std::size_t i = 0; i < n; i += chunk) {
                const std::size_t j = std::min(n, i + chunk) - 1;
                parts.push_back({indices[i], indices[j]});
            }
            return parts;
        }
    }

    template <typename Callback>
    inline void runParallel(const std::string& filepath,
                            Callback&& callback,
                            std::size_t nThreads = 0,
                            const std::string& protonTree = "Protons",
                            const std::string& pionTree   = "Pions")
    {
        detail::enableRootThreadSafety();
        const std::size_t threads = Config::resolveThreadCount(nThreads);

        auto indices = detail::collectEventIndices(filepath, protonTree, pionTree);
        if (indices.empty()) return;
        auto parts = detail::partitionEvents(indices, threads);

        std::vector<std::thread> workers;
        std::vector<std::exception_ptr> errors(parts.size());
        workers.reserve(parts.size());

        for (std::size_t t = 0; t < parts.size(); ++t) {
            workers.emplace_back([&, t]{
                try {
                    EventStream stream(filepath, protonTree, pionTree,
                                       parts[t].firstEvent, parts[t].lastEvent);
                    while (stream.next()) callback(stream.event(), static_cast<int>(t));
                } catch (...) {
                    errors[t] = std::current_exception();
                }
            });
        }
        for (auto& w : workers) w.join();
        for (auto& e : errors) if (e) std::rethrow_exception(e);
    }

    inline std::vector<Event> readAllParallel(const std::string& filepath,
                                              std::size_t nThreads = 0,
                                              const std::string& protonTree = "Protons",
                                              const std::string& pionTree   = "Pions")
    {
        detail::enableRootThreadSafety();
        const std::size_t threads = Config::resolveThreadCount(nThreads);

        auto indices = detail::collectEventIndices(filepath, protonTree, pionTree);
        if (indices.empty()) return {};
        auto parts = detail::partitionEvents(indices, threads);

        std::vector<std::vector<Event>> buckets(parts.size());
        std::vector<std::thread> workers;
        std::vector<std::exception_ptr> errors(parts.size());
        workers.reserve(parts.size());

        for (std::size_t t = 0; t < parts.size(); ++t) {
            workers.emplace_back([&, t]{
                try {
                    EventStream stream(filepath, protonTree, pionTree,
                                       parts[t].firstEvent, parts[t].lastEvent);
                    buckets[t].reserve(stream.nEvents());
                    while (stream.next()) buckets[t].push_back(stream.event());
                } catch (...) {
                    errors[t] = std::current_exception();
                }
            });
        }
        for (auto& w : workers) w.join();
        for (auto& e : errors) if (e) std::rethrow_exception(e);

        std::size_t total = 0;
        for (const auto& b : buckets) total += b.size();
        std::vector<Event> out;
        out.reserve(total);
        for (auto& b : buckets)
            out.insert(out.end(), std::make_move_iterator(b.begin()),
                                   std::make_move_iterator(b.end()));
        return out;
    }
}
