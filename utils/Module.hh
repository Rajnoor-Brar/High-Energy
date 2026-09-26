#pragma once
// utils/Module.hh — the module kit (docs/rework_v2/05_Tools.md §5).
//
// A module is a plain program. This header removes the boilerplate and nothing else:
//
//     <Name>.exe CONFIG.toml [--input=FILE] [--output=FILE] [--events=N] [--sidecar=FILE]
//
//   * CONFIG.toml: the extracted [tools.<tag>.config], with the consumed quantities set in it (or
//     under [quantities]) and any requested standard configurations under [standard.<key>];
//   * --input: HepMC3 from a file or a FIFO, plain, gz or zst (HepMC3::deduce_reader); none for an
//     integrated program that makes its own events;
//   * --output: written as given (the runner passes the .partial name and renames it after its
//     checks), with a report beside it, <output>.json: events, ΣW and the σ used;
//   * --events: the number expected, for progress only;
//   * --sidecar: the producer's sidecar, when it was written before this program started (a file
//     chain). σ then comes from it, else from the last event, which is Rivet's rule (L2).
//
// **The rule the types do not enforce** (v1's scaling contract): fill with raw weights and scale
// once, after the loop. RootOut::scale refuses a second call. A histogram drawn beside Rivet's is
// a density: scale with "width" as well (L21).
//
// Exit codes (02 §9): 0 ok, 1 config, 2 usage, 3 init, 4 input, 5 output, 6 stopped, 70 internal.
// A module runs single-threaded.

#include "Status.hh"

#include "HepMC3/GenCrossSection.h"
#include "HepMC3/GenEvent.h"
#include "HepMC3/ReaderFactory.h"

#include <toml++/toml.hpp>

#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <memory>
#include <sstream>
#include <string>
#include <type_traits>
#include <vector>

#if __has_include(<TFile.h>)
#include "TDirectory.h"
#include "TFile.h"
#include "TH1.h"
#endif

namespace Module {

    enum Exit : int { Ok = 0, Config = 1, Usage = 2, Init = 3, Input = 4, Output = 5, Stopped = 6, Internal = 70 };

    namespace detail {
        inline std::atomic<bool> stop{false};
        inline void onSignal(int) { stop = true; }
        inline std::vector<std::function<bool()>>& writers() {   // RootOut registers itself here
            static std::vector<std::function<bool()>> list;
            return list;
        }
        inline Status::Reporter& status() {
            static Status::Reporter reporter;
            return reporter;
        }
        [[noreturn]] inline void die(int code, const std::string& message) {
            status().log("error", message);
            std::exit(code);
        }
    }  // namespace detail

    // A read-only view of a TOML table, with defaults. A missing table is an empty view.
    class Values {
      public:
        Values() = default;
        Values(const toml::table* table, std::string where) : table_(table), where_(std::move(where)) {}

        bool has(const std::string& key) const { return table_ && table_->contains(key); }
        const toml::table* raw() const { return table_; }

        // The type follows the default: get("bins", 100) is an int, get("tolerance", 0.15) a double.
        template <class T>
        T get(const std::string& key, T fallback) const {
            if (!has(key)) return fallback;
            const toml::node& node = *table_->get(key);
            if constexpr (std::is_same_v<T, bool>) {
                if (auto v = node.value<bool>()) return *v;
            } else if constexpr (std::is_integral_v<T>) {
                if (auto v = node.value<int64_t>()) return static_cast<T>(*v);
                if (auto v = node.value<double>(); v && std::floor(*v) == *v) return static_cast<T>(*v);
            } else if constexpr (std::is_floating_point_v<T>) {
                if (auto v = node.value<double>()) return static_cast<T>(*v);   // an integer converts
            } else {
                if (auto v = node.value<std::string>()) return T(*v);
            }
            detail::die(Config, where_ + "." + key + " has the wrong type");
        }
        std::string get(const std::string& key, const char* fallback) const { return get<std::string>(key, fallback); }

        std::vector<std::string> list(const std::string& key) const {
            std::vector<std::string> out;
            if (!has(key)) return out;
            const toml::array* array = table_->get(key)->as_array();
            if (!array) detail::die(Config, where_ + "." + key + " must be a list");
            for (const auto& item : *array) {
                auto v = item.value<std::string>();
                if (!v) detail::die(Config, where_ + "." + key + " must be a list of strings");
                out.push_back(*v);
            }
            return out;
        }

        Values table(const std::string& key) const {
            if (!has(key)) return Values(nullptr, where_ + "." + key);
            const toml::table* inner = table_->get(key)->as_table();
            if (!inner) detail::die(Config, where_ + "." + key + " must be a table");
            return Values(inner, where_ + "." + key);
        }

      private:
        const toml::table* table_ = nullptr;
        std::string where_;
    };

    class Job;

    struct Event {
        const HepMC3::GenEvent& hepmc() const { return *event; }
        double weight() const { return event->weights().empty() ? 1.0 : event->weights().front(); }
        long index = 0;                          // 0-based
        const HepMC3::GenEvent* event = nullptr;
    };

    class Job {
      public:
        Job(int argc, char** argv) {
            std::signal(SIGINT, detail::onSignal);
            std::signal(SIGTERM, detail::onSignal);
            std::vector<std::string> positional;
            for (int i = 1; i < argc; ++i) {
                std::string arg = argv[i], value;
                const auto equals = arg.find('=');
                if (arg.rfind("--", 0) == 0 && equals != std::string::npos) {
                    value = arg.substr(equals + 1), arg = arg.substr(0, equals);
                } else if (arg.rfind("--", 0) == 0 && i + 1 < argc) {
                    value = argv[++i];
                } else if (arg.rfind("--", 0) == 0) {
                    usage(argv[0], arg + " needs a value");
                }
                if (arg == "--input") input_ = value;
                else if (arg == "--output") output_ = value;
                else if (arg == "--sidecar") sidecar_ = value;
                else if (arg == "--events") expected_ = std::atol(value.c_str());
                else if (arg.rfind("--", 0) == 0) usage(argv[0], "unknown option " + arg);
                else positional.push_back(arg);
            }
            if (positional.size() != 1) usage(argv[0], "one CONFIG.toml expected");
            try {
                document_ = toml::parse_file(positional.front());
            } catch (const toml::parse_error& error) {
                detail::die(Config, "cannot parse " + positional.front() + ": " + std::string(error.description()));
            }
            config_ = Values(&document_, positional.front());
            if (!sidecar_.empty()) readSidecar();
            started_ = std::chrono::steady_clock::now();
        }

        Job(const Job&) = delete;              // config() points into the parsed document
        Job& operator=(const Job&) = delete;

        const Values& config() const { return config_; }
        Values quantities() const { return config_.table("quantities"); }
        const std::string& input() const { return input_; }
        const std::string& output() const { return output_; }
        bool hasInput() const { return !input_.empty(); }
        bool stopping() const { return detail::stop; }
        Status::Reporter& status() { return detail::status(); }

        // ── standard configurations (V21, 04 §7.3) ──────────────────────────────────────────
        std::string standard(const std::string& key) const { return requested(key).get("path", ""); }
        std::vector<std::string> standardParts(const std::string& key) const { return requested(key).list("parts"); }
        Values standardValues(const std::string& key) const { return requested(key); }

        // ── events ───────────────────────────────────────────────────────────────────────────
        class Events {
          public:
            class iterator {
              public:
                iterator(Job* job, bool end) : job_(job), end_(end) {
                    if (!end_) ++*this;
                }
                const Event& operator*() const { return job_->current_; }
                const Event* operator->() const { return &job_->current_; }
                iterator& operator++() { end_ = !job_->next(); return *this; }
                bool operator!=(const iterator& other) const { return end_ != other.end_; }

              private:
                Job* job_;
                bool end_;
            };
            explicit Events(Job* job) : job_(job) {}
            iterator begin() { return iterator(job_, false); }
            iterator end() { return iterator(job_, true); }

          private:
            Job* job_;
        };

        Events events() {
            if (!hasInput()) detail::die(Usage, "this module was given no --input");
            if (reader_) detail::die(Internal, "events() can be iterated once");
            reader_ = HepMC3::deduce_reader(input_);
            if (!reader_ || reader_->failed()) detail::die(Input, "cannot read HepMC3 from " + input_);
            status().phase("analysing", input_);
            return Events(this);
        }

        long count() const { return count_; }
        double sumW() const { return sumW_; }
        // σ in pb: the sidecar's when it was given, else the last event's (L2).
        double crossSectionPb() const { return haveSidecar_ ? sidecarPb_ : lastPb_; }
        double crossSectionErrPb() const { return haveSidecar_ ? sidecarErrPb_ : lastErrPb_; }

        // For integrated programs that loop themselves.
        void progress(long done, long total) {
            const double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - started_).count();
            status().progress(done, total, s > 0 ? done / s : 0.0, done == 0 || done == total);
        }
        void setCrossSection(double pb, double errPb) { lastPb_ = pb, lastErrPb_ = errPb; }
        void countEvent(double weight) { ++count_, sumW_ += weight; }

        [[noreturn]] void fail(int code, const std::string& message = "") {
            detail::die(code, message.empty() ? "failed" : message);
        }

        // Write every output, then the report. Stopped (6) when interrupted: the outputs are still
        // written, under the .partial name the runner gave them.
        int finish() {
            if (reader_) reader_->close();
            progress(count_, expected_ ? expected_ : count_);
            bool ok = true;
            for (auto& write : detail::writers()) ok = write() && ok;
            if (!output_.empty()) {
                std::ofstream report(output_ + ".json");
                report.precision(12);
                report << "{\n  \"events\": " << count_ << ",\n  \"sum_w\": " << sumW_ << ",\n  \"sigma_pb\": "
                       << crossSectionPb() << ",\n  \"sigma_err_pb\": " << crossSectionErrPb()
                       << ",\n  \"sigma_from\": \"" << (haveSidecar_ ? "sidecar" : "events") << "\",\n  \"input\": "
                       << Status::quote(input_) << ",\n  \"stopped\": " << (stopping() ? "true" : "false") << "\n}\n";
                ok = ok && report.good();
            }
            status().summary("\"events\": " + std::to_string(count_) + ", \"sum_w\": " + Status::number(sumW_) +
                             ", \"sigma_pb\": " + Status::number(crossSectionPb()));
            if (!ok) {
                status().log("error", "an output could not be written");
                return Output;
            }
            return stopping() ? Stopped : Ok;
        }

      private:
        [[noreturn]] static void usage(const char* self, const std::string& why) {
            std::fprintf(stderr, "%s: %s\nusage: %s CONFIG.toml [--input=FILE] [--output=FILE] [--events=N] [--sidecar=FILE]\n",
                         self, why.c_str(), self);
            std::exit(Usage);
        }

        Values requested(const std::string& key) const {
            Values table = config_.table("standard").table(key);
            if (!table.raw())
                detail::die(Config, "no standard configuration '" + key + "': add " + key + " = true to this tool's table");
            return table;
        }

        void readSidecar() {                       // App_Pythia's flat JSON object: two numbers are enough
            std::ifstream in(sidecar_);
            std::stringstream buffer;
            buffer << in.rdbuf();
            const std::string text = buffer.str();
            auto number = [&](const std::string& key, double& out) {
                const auto at = text.find("\"" + key + "\"");
                if (at == std::string::npos) return false;
                out = std::atof(text.c_str() + text.find(':', at) + 1);
                return true;
            };
            haveSidecar_ = number("sigma_pb", sidecarPb_) && number("sigma_err_pb", sidecarErrPb_);
            if (!haveSidecar_) status().log("warn", "sidecar " + sidecar_ + " unreadable; σ from the events");
        }

        bool next() {
            if (detail::stop) return false;
            if (!reader_->read_event(event_) || reader_->failed()) return false;
            current_.event = &event_;
            current_.index = count_;
            countEvent(current_.weight());
            if (auto xs = event_.cross_section()) setCrossSection(xs->xsec(), xs->xsec_err());
            if (count_ % 100 == 0) progress(count_, expected_);
            return true;
        }

        toml::table document_;
        Values config_;
        std::string input_, output_, sidecar_;
        long expected_ = 0, count_ = 0;
        double sumW_ = 0, lastPb_ = 0, lastErrPb_ = 0, sidecarPb_ = 0, sidecarErrPb_ = 0;
        bool haveSidecar_ = false;
        std::shared_ptr<HepMC3::Reader> reader_;
        HepMC3::GenEvent event_;
        Event current_;
        std::chrono::steady_clock::time_point started_;
    };

#if __has_include(<TFile.h>)
    // ROOT histograms, written to one file when the job finishes. "Dir/name" books into a directory.
    class RootOut {
      public:
        explicit RootOut(std::string path) : path_(std::move(path)), slot_(detail::writers().size()) {
            detail::writers().push_back([this] { return write(); });
        }
        ~RootOut() { detail::writers()[slot_] = [] { return true; }; }
        RootOut(const RootOut&) = delete;
        RootOut& operator=(const RootOut&) = delete;

        template <class H, class... Args>
        H* book(const std::string& path, Args&&... args) {
            const auto slash = path.rfind('/');
            const std::string name = slash == std::string::npos ? path : path.substr(slash + 1);
            auto* h = new H(name.c_str(), std::forward<Args>(args)...);
            h->SetDirectory(nullptr);
            h->Sumw2();
            items_.push_back({slash == std::string::npos ? "" : path.substr(0, slash), std::unique_ptr<TH1>(h)});
            return h;
        }

        // Once, after the loop. `option` goes to TH1::Scale: "width" also divides by the bin width.
        void scale(double factor, const char* option = "") {
            if (scaled_) detail::die(Internal, "RootOut::scale called twice: fill raw, scale once");
            scaled_ = true;
            for (auto& item : items_) item.histogram->Scale(factor, option);
        }

        bool write() {
            if (path_.empty()) return true;
            std::unique_ptr<TFile> file(TFile::Open(path_.c_str(), "RECREATE"));
            if (!file || file->IsZombie()) return false;
            for (auto& item : items_) {
                TDirectory* where = file.get();
                if (!item.dir.empty()) {
                    where = file->GetDirectory(item.dir.c_str());
                    if (!where) where = file->mkdir(item.dir.c_str(), "", true);
                }
                where->WriteTObject(item.histogram.get());
            }
            file->Close();
            return true;
        }

      private:
        struct Item {
            std::string dir;
            std::unique_ptr<TH1> histogram;
        };
        std::string path_;
        size_t slot_;
        std::vector<Item> items_;
        bool scaled_ = false;
    };
#endif

}  // namespace Module
