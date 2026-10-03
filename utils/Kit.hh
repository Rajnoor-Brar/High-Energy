#pragma once
// utils/Kit.hh — what every program of the framework does the same way (audit 1 L8, L9, C13; V73):
//
//   Kit::Exit         one table of exit codes for every app and module program (02 §11)
//   Kit::Args         --key value, --key=value, flags and positionals; an unknown option is an error
//   Kit::Json::Object a JSON object written key by key: sidecars, reports, status summaries
//   Kit::Json::Flat   a flat JSON object read back: its strings, numbers and booleans by key
//
// Header only, standard library only, so a program that needs nothing else can include it alone.

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <vector>

namespace Kit {

    // 0 ok, 1 its config (a card, a page), 2 usage, 3 init, 4 input, 5 output, 6 stopped, 70 internal.
    enum Exit : int { Ok = 0, Config = 1, Usage = 2, Init = 3, Input = 4, Output = 5, Stopped = 6, Internal = 70 };

    // The command line: `valued` options take a value (`--name V` or `--name=V`, repeatable), `flags`
    // take none; `-h`/`--help` asks for the usage (an error with no message). Anything else that starts
    // with `-` is an error; the rest are positionals, in order.
    class Args {
      public:
        Args(int argc, char** argv, std::set<std::string> valued, std::set<std::string> flags = {}) {
            for (int i = 1; i < argc && error_.empty(); ++i) {
                std::string arg = argv[i];
                if (arg == "-h" || arg == "--help") {
                    help_ = true;
                    return;
                }
                if (arg.rfind("-", 0) != 0 || arg == "-") {
                    positional_.push_back(arg);
                    continue;
                }
                std::string name = arg.substr(arg.rfind("--", 0) == 0 ? 2 : 1), value;
                const auto equals = name.find('=');
                const bool inline_value = equals != std::string::npos;
                if (inline_value) value = name.substr(equals + 1), name = name.substr(0, equals);
                if (flags.count(name) && !inline_value) {
                    values_[name].push_back("");
                } else if (valued.count(name)) {
                    if (!inline_value) {
                        if (i + 1 >= argc) {
                            error_ = arg + " needs a value";
                            break;
                        }
                        value = argv[++i];
                    }
                    values_[name].push_back(value);
                } else {
                    error_ = "unknown option " + arg;
                }
            }
        }

        bool ok() const { return error_.empty() && !help_; }
        const std::string& error() const { return error_; }      // "" with ok() false: --help
        bool has(const std::string& name) const { return values_.count(name) > 0; }
        std::string get(const std::string& name, const std::string& fallback = "") const {
            const auto found = values_.find(name);
            return found == values_.end() ? fallback : found->second.back();     // the last one given wins
        }
        std::vector<std::string> all(const std::string& name) const {
            const auto found = values_.find(name);
            return found == values_.end() ? std::vector<std::string>{} : found->second;
        }
        const std::vector<std::string>& positional() const { return positional_; }

      private:
        std::map<std::string, std::vector<std::string>> values_;
        std::vector<std::string> positional_;
        std::string error_;
        bool help_ = false;
    };

    namespace Json {

        // A JSON string literal, escaped.
        inline std::string quote(const std::string& text) {
            std::string out = "\"";
            for (char c : text) {
                switch (c) {
                    case '"':  out += "\\\""; break;
                    case '\\': out += "\\\\"; break;
                    case '\n': out += "\\n";  break;
                    case '\t': out += "\\t";  break;
                    case '\r': out += "\\r";  break;
                    default:
                        if (static_cast<unsigned char>(c) < 0x20) {
                            char buffer[8];
                            std::snprintf(buffer, sizeof buffer, "\\u%04x", c);
                            out += buffer;
                        } else {
                            out += c;
                        }
                }
            }
            return out + "\"";
        }

        // A number as JSON writes it: `digits` significant digits, no trailing noise.
        inline std::string number(double value, int digits = 10) {
            char buffer[40];
            std::snprintf(buffer, sizeof buffer, "%.*g", digits, value);
            return buffer;
        }

        // Key by key, in order: `Object().add("written", n).add("outputs", paths).str()`.
        class Object {
          public:
            Object& add(const std::string& key, const std::string& value) { return raw(key, quote(value)); }
            Object& add(const std::string& key, const char* value) { return raw(key, quote(value)); }
            Object& add(const std::string& key, bool value) { return raw(key, value ? "true" : "false"); }
            Object& add(const std::string& key, int value) { return raw(key, std::to_string(value)); }
            Object& add(const std::string& key, long value) { return raw(key, std::to_string(value)); }
            Object& add(const std::string& key, long long value) { return raw(key, std::to_string(value)); }
            Object& add(const std::string& key, double value) { return raw(key, number(value, 12)); }
            Object& add(const std::string& key, const std::vector<std::string>& values) {
                std::string out = "[";
                for (size_t i = 0; i < values.size(); ++i) out += (i ? ", " : "") + quote(values[i]);
                return raw(key, out + "]");
            }
            template <class N>
            Object& numbers(const std::string& key, const std::vector<N>& values) {
                std::string out = "[";
                for (size_t i = 0; i < values.size(); ++i) out += (i ? ", " : "") + std::to_string(values[i]);
                return raw(key, out + "]");
            }
            Object& add(const std::string& key, const Object& value) { return raw(key, value.str(false)); }
            // A value already written as JSON.
            Object& raw(const std::string& key, const std::string& json) {
                fields_.emplace_back(key, json);
                return *this;
            }

            // `{"a": 1, "b": 2}`, or (pretty) one key per line, as the sidecars have always been written.
            std::string str(bool pretty = true) const {
                std::string out = "{";
                for (size_t i = 0; i < fields_.size(); ++i)
                    out += (i ? "," : "") + std::string(pretty ? "\n  " : (i ? " " : "")) + quote(fields_[i].first) +
                           ": " + fields_[i].second;
                return out + (pretty ? (fields_.empty() ? "}\n" : "\n}\n") : "}");
            }
            // The inside of the object, for Status::Reporter::summary.
            std::string fields() const {
                const std::string whole = str(false);
                return whole.substr(1, whole.size() - 2);
            }

            // Written whole or not at all: to PATH.part, then renamed.
            bool write(const std::string& path) const {
                const std::string partial = path + ".part";
                {
                    std::ofstream out(partial);
                    out << str();
                    if (!out) return false;
                }
                return std::rename(partial.c_str(), path.c_str()) == 0;
            }

          private:
            std::vector<std::pair<std::string, std::string>> fields_;
        };

        // A flat JSON object read back (L9): the top level's strings, numbers and booleans by key;
        // a nested array or object is skipped. Enough for a sidecar or a report.
        class Flat {
          public:
            static std::optional<Flat> read(const std::string& path) {
                std::ifstream in(path);
                if (!in) return std::nullopt;
                std::stringstream buffer;
                buffer << in.rdbuf();
                return parse(buffer.str());
            }

            static std::optional<Flat> parse(const std::string& text) {
                Flat flat;
                size_t i = text.find('{');
                if (i == std::string::npos) return std::nullopt;
                ++i;
                auto space = [&] { while (i < text.size() && std::isspace(static_cast<unsigned char>(text[i]))) ++i; };
                auto string = [&](std::string& out) {
                    if (i >= text.size() || text[i] != '"') return false;
                    for (++i; i < text.size() && text[i] != '"'; ++i) {
                        if (text[i] == '\\' && i + 1 < text.size()) {
                            const char e = text[++i];
                            out += e == 'n' ? '\n' : e == 't' ? '\t' : e == 'r' ? '\r' : e;
                        } else {
                            out += text[i];
                        }
                    }
                    if (i >= text.size()) return false;
                    ++i;
                    return true;
                };
                while (true) {
                    space();
                    if (i < text.size() && text[i] == '}') return flat;
                    std::string key;
                    if (!string(key)) return std::nullopt;
                    space();
                    if (i >= text.size() || text[i] != ':') return std::nullopt;
                    ++i;
                    space();
                    if (i >= text.size()) return std::nullopt;
                    if (text[i] == '"') {
                        std::string value;
                        if (!string(value)) return std::nullopt;
                        flat.text_[key] = value;
                    } else if (text[i] == '[' || text[i] == '{') {   // skipped, brackets matched
                        int depth = 0;
                        bool quoted = false;
                        for (; i < text.size(); ++i) {
                            const char c = text[i];
                            if (quoted) { if (c == '\\') ++i; else if (c == '"') quoted = false; continue; }
                            if (c == '"') quoted = true;
                            else if (c == '[' || c == '{') ++depth;
                            else if ((c == ']' || c == '}') && --depth == 0) { ++i; break; }
                        }
                    } else {
                        const size_t end = text.find_first_of(",}", i);
                        std::string word = text.substr(i, end - i);
                        while (!word.empty() && std::isspace(static_cast<unsigned char>(word.back()))) word.pop_back();
                        if (word == "true" || word == "false") flat.bool_[key] = word == "true";
                        else if (word != "null") {
                            char* stop = nullptr;
                            const double value = std::strtod(word.c_str(), &stop);
                            if (stop == word.c_str()) return std::nullopt;
                            flat.number_[key] = value;
                        }
                        i = end;
                    }
                    space();
                    if (i < text.size() && text[i] == ',') { ++i; continue; }
                    if (i < text.size() && text[i] == '}') return flat;
                    return std::nullopt;
                }
            }

            std::optional<double> number(const std::string& key) const { return find(number_, key); }
            std::optional<std::string> text(const std::string& key) const { return find(text_, key); }
            std::optional<bool> flag(const std::string& key) const { return find(bool_, key); }

          private:
            template <class T>
            static std::optional<T> find(const std::map<std::string, T>& map, const std::string& key) {
                const auto found = map.find(key);
                return found == map.end() ? std::nullopt : std::optional<T>(found->second);
            }
            std::map<std::string, double> number_;
            std::map<std::string, std::string> text_;
            std::map<std::string, bool> bool_;
        };

    }  // namespace Json

}  // namespace Kit
