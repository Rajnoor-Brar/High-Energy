#pragma once

#include <algorithm>
#include <cctype>
#include <cmath>
#include <memory>
#include <optional>
#include <ostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "TClass.h"
#include "TDirectory.h"
#include "TGraph.h"
#include "TH1.h"
#include "TH2.h"
#include "TKey.h"
#include "TROOT.h"

#include "Paint/Apply.hh"
#include "Paint/Book.hh"
#include "Paint/Style.hh"
#include "Paint/Types.hh"

namespace Paint {

    // Named constants for key TOML keys and internal identifiers.
    inline constexpr const char* kPaintTableKey    = "paint";
    inline constexpr const char* kResultsKey       = "results";
    inline constexpr const char* kResultDirDefault = "results";
    inline constexpr const char* kCloneSuffix      = "__paint";

    namespace detail {

        inline const toml::table& paintTable(const PaintBook& book) {
            const toml::table* paint = getTable(book.config, kPaintTableKey);
            if (paint == nullptr) {
                throw std::runtime_error("Paint config must contain a [paint] table");
            }
            return *paint;
        }

        inline std::string resultContext(const std::string& resultName) {
            return "Paint result '" + resultName + "'";
        }

        inline std::string sourceContext(const std::string& resultName, const std::string& sourcePath) {
            return resultContext(resultName) + ": source '" + sourcePath + "'";
        }

        inline std::vector<std::string> readRequiredResults(const toml::table& paint) {
            std::vector<std::string> results = readStringArray(paint[kResultsKey]);
            if (results.empty()) {
                throw std::runtime_error("Paint config [paint].results must list at least one result");
            }
            return results;
        }

        inline const toml::table* resultTable(const toml::table& paint,
                                              const std::string& name,
                                              const std::string& context) {
            const toml::table* table = getTable(paint, name);
            if (table == nullptr) {
                throw std::runtime_error(context + ": missing [paint." + name + "] table");
            }
            return table;
        }

        inline void mergeSubsectionUse(const toml::table& paint,
                                       const toml::table& table,
                                       const std::string& useKey,
                                       const std::string& subtableKey,
                                       Style& style,
                                       const std::string& context) {
            const auto presetName = table[useKey].value<std::string>();
            if (!presetName) return;
            const toml::table* preset = resultTable(paint, *presetName, context + ": unknown preset '" + *presetName + "'");
            const toml::table* sub = getTable(*preset, subtableKey);
            if (sub == nullptr) return;

            if (subtableKey == "axis") {
                mergeAxis(*sub, style.axis);
            } else if (subtableKey == "canvas") {
                mergeCanvas(*sub, style.canvas);
            } else if (subtableKey == "stats") {
                mergeStats(*sub, style.stats);
            } else if (subtableKey == "legend") {
                mergeLegend(*sub, style.legend);
            } else if (subtableKey == "title_box") {
                mergeTitleBox(*sub, style.titleBox);
            }
        }

        inline void mergeDirectRenderSettings(const toml::table& table,
                                              RenderResult& result,
                                              const std::string& context,
                                              bool inheritOutputName,
                                              bool trackMode = true) {
            if (const auto mode = table["mode"].value<std::string>()) {
                result.mode = parseMode(*mode, context);
                if (trackMode) result.modeExplicit = true;
            }
            readValue(table, "rows", result.rows);
            readValue(table, "cols", result.cols);
            readString(table, "title", result.title);

            const std::vector<std::string> formats = readStringArray(table["formats"]);
            if (!formats.empty()) result.formats = formats;

            if (inheritOutputName) {
                readString(table, "output_name", result.outputName);
            }
        }

        template <typename T, typename MergeFn>
        inline void resolvePresetChain(const toml::table& paint,
                                       const std::string& presetName,
                                       T& out,
                                       std::vector<std::string>& stack,
                                       const std::string& context,
                                       const std::string& kindWord,
                                       MergeFn&& merge) {
            if (std::find(stack.begin(), stack.end(), presetName) != stack.end())
                throw std::runtime_error(context + ": " + kindWord + " cycle involving '" + presetName + "'");
            const toml::table* preset = resultTable(paint, presetName,
                context + ": unknown " + kindWord + " '" + presetName + "'");
            stack.push_back(presetName);
            if (const auto parent = (*preset)["use"].value<std::string>())
                resolvePresetChain(paint, *parent, out, stack, context, kindWord, merge);
            merge(*preset, out);
            stack.pop_back();
        }

        inline void applyVisualPreset(const toml::table& paint,
                                      const std::string& presetName,
                                      RenderResult& result,
                                      std::vector<std::string>& stack,
                                      const std::string& context) {
            resolvePresetChain(paint, presetName, result, stack, context, "preset",
                [&](const toml::table& preset, RenderResult& r) {
                    mergeSubsectionUse(paint, preset, "axis_use",   "axis",      r.style, context);
                    mergeSubsectionUse(paint, preset, "canvas_use", "canvas",    r.style, context);
                    mergeSubsectionUse(paint, preset, "stats_use",  "stats",     r.style, context);
                    mergeSubsectionUse(paint, preset, "legend_use", "legend",    r.style, context);
                    mergeSubsectionUse(paint, preset, "title_use",  "title_box", r.style, context);
                    mergeDirectRenderSettings(preset, r, context, true);
                    mergeStyle(preset, r.style);
                });
        }

        inline void mergeResultVisual(const toml::table& paint,
                                      const std::string& name,
                                      const toml::table& table,
                                      RenderResult& result) {
            const std::string context = resultContext(name);

            if (const auto preset = table["use"].value<std::string>()) {
                std::vector<std::string> stack;
                applyVisualPreset(paint, *preset, result, stack, context);
            }

            mergeSubsectionUse(paint, table, "axis_use",   "axis",      result.style, context);
            mergeSubsectionUse(paint, table, "canvas_use", "canvas",    result.style, context);
            mergeSubsectionUse(paint, table, "stats_use",  "stats",     result.style, context);
            mergeSubsectionUse(paint, table, "legend_use", "legend",    result.style, context);
            mergeSubsectionUse(paint, table, "title_use",  "title_box", result.style, context);
            mergeDirectRenderSettings(table, result, context, true);
            mergeStyle(table, result.style);
        }

        inline void applySourcePreset(const toml::table& paint,
                                      const std::string& presetName,
                                      Style& style,
                                      std::vector<std::string>& stack,
                                      const std::string& context) {
            resolvePresetChain(paint, presetName, style, stack, context, "source preset",
                [](const toml::table& preset, Style& s) { mergeStyle(preset, s); });
        }

        inline std::string expectedKind(const toml::table& resultTable,
                                        const toml::table* sourceTable) {
            if (sourceTable != nullptr) {
                if (const auto local = (*sourceTable)["source_type"].value<std::string>()) return *local;
            }
            return resultTable["source_type"].value_or(std::string{});
        }

        inline ObjectKind inferKind(const TObject* object, const std::string& context) {
            for (const auto& [kind, entry] : kindRegistry()) {
                if (entry.detect(object)) return kind;
            }
            throw std::runtime_error(context + ": unsupported ROOT object type " + object->ClassName());
        }

        inline std::string toLower(std::string s) {
            std::transform(s.begin(), s.end(), s.begin(),
                [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            return s;
        }

        inline void assertExpectedKind(ObjectKind actual,
                                       const std::string& expected,
                                       const std::string& context) {
            if (expected.empty()) return;
            const std::string expectedLower = toLower(expected);
            for (const auto& [kind, entry] : kindRegistry()) {
                if (kind != actual) continue;
                const std::string cnLower    = toLower(entry.rootClassName);
                const std::string shortLower = cnLower.size() > 1 ? cnLower.substr(1) : cnLower;
                if (expectedLower == cnLower || expectedLower == shortLower) return;
                break;
            }
            throw std::runtime_error(context + ": expected " + expected + ", got " + objectKindName(actual));
        }

        inline void detachHistFromDirectory(TObject* object) {
            if (TH1* hist = dynamic_cast<TH1*>(object)) {
                hist->SetDirectory(nullptr);
            }
        }

        // Glob matcher: '*' matches any sequence, '?' matches any single character.
        inline bool globMatch(const std::string& pattern, const std::string& text) {
            std::size_t pi = 0, ti = 0;
            std::size_t starPi = std::string::npos, starTi = 0;
            while (ti < text.size()) {
                if (pi < pattern.size() && (pattern[pi] == text[ti] || pattern[pi] == '?')) {
                    ++pi; ++ti;
                } else if (pi < pattern.size() && pattern[pi] == '*') {
                    starPi = pi++;
                    starTi = ti;
                } else if (starPi != std::string::npos) {
                    pi = starPi + 1;
                    ti = ++starTi;
                } else {
                    return false;
                }
            }
            while (pi < pattern.size() && pattern[pi] == '*') ++pi;
            return pi == pattern.size();
        }

        static constexpr int kMaxSearchDepth = 32;

        inline void searchDirectory(TDirectory* dir,
                                    const std::string& needle,
                                    const std::string& prefix,
                                    std::vector<std::string>& matches,
                                    int depth = 0) {
            if (dir == nullptr || dir->GetListOfKeys() == nullptr) return;
            if (depth >= kMaxSearchDepth) {
                throw std::runtime_error(
                    "Paint source_search: directory depth exceeded " +
                    std::to_string(kMaxSearchDepth) + " levels at '" + prefix + "'");
            }

            TIter next(dir->GetListOfKeys());
            while (TObject* raw = next()) {
                TKey* key = dynamic_cast<TKey*>(raw);
                if (key == nullptr) continue;

                const std::string name = key->GetName();
                const std::string path = prefix.empty() ? name : prefix + "/" + name;

                TClass* cls = gROOT->GetClass(key->GetClassName());
                if (cls != nullptr && cls->InheritsFrom(TDirectory::Class())) {
                    if (TDirectory* subdir = dir->GetDirectory(name.c_str())) {
                        searchDirectory(subdir, needle, path, matches, depth + 1);
                    }
                    continue;
                }

                if (globMatch(needle, name)) matches.push_back(path);
            }
        }

        inline std::vector<std::string> searchObjects(TFile& file, const std::string& needle) {
            std::vector<std::string> matches;
            searchDirectory(&file, needle, "", matches);
            std::sort(matches.begin(), matches.end());
            return matches;
        }

        inline std::unique_ptr<TObject> cloneObject(TObject* object, const std::string& cloneName) {
            TObject* clone = object->Clone(cloneName.c_str());
            if (clone == nullptr) {
                throw std::runtime_error("Paint: failed to clone ROOT object " + std::string(object->GetName()));
            }
            detachHistFromDirectory(clone);
            return std::unique_ptr<TObject>(clone);
        }

        inline ResolvedSource resolveSource(const toml::table& paint,
                                            TFile& file,
                                            const toml::table& resultConfig,
                                            const RenderResult& result,
                                            const std::string& path,
                                            const toml::table* sourceConfig,
                                            std::size_t index,
                                            std::optional<Color_t> paletteColor = std::nullopt) {
            const std::string context = sourceContext(result.name, path);
            TObject* raw = file.Get(path.c_str());
            if (raw == nullptr) {
                throw std::runtime_error(context + " not found");
            }

            ResolvedSource source;
            source.path = path;
            source.title = raw->GetTitle();
            source.rootClass = raw->ClassName();
            source.style = result.style;

            // Apply palette colour before source-level overrides so that
            // per-source use/inline settings can still override it.
            if (paletteColor) {
                source.style.line.color   = *paletteColor;
                source.style.marker.color = *paletteColor;
            }

            if (sourceConfig != nullptr) {
                readString(*sourceConfig, "label", source.label);
                readString(*sourceConfig, "title", source.title);
                readString(*sourceConfig, "draw_option", source.drawOption);
                if (const auto preset = (*sourceConfig)["use"].value<std::string>()) {
                    std::vector<std::string> stack;
                    applySourcePreset(paint, *preset, source.style, stack, context);
                }
                mergeStyle(*sourceConfig, source.style);
            }

            if (source.drawOption.empty()) source.drawOption = source.style.drawOption;

            source.kind = inferKind(raw, context);
            assertExpectedKind(source.kind, expectedKind(resultConfig, sourceConfig), context);

            const std::string cloneName = result.name + "_" + std::to_string(index) + kCloneSuffix;
            source.owned = cloneObject(raw, cloneName);
            source.object = source.owned.get();
            return source;
        }

        inline std::vector<const toml::table*> readSourceTables(const toml::table& resultConfig,
                                                               const std::string& resultName) {
            const toml::array* sources = resultConfig["sources"].as_array();
            std::vector<const toml::table*> tables;
            if (sources == nullptr) return tables;
            tables.reserve(sources->size());
            for (const toml::node& node : *sources) {
                const toml::table* source = node.as_table();
                if (source == nullptr) {
                    throw std::runtime_error(resultContext(resultName) + ": every sources[] entry must be a table");
                }
                tables.push_back(source);
            }
            return tables;
        }

        inline void resolveSources(const toml::table& paint,
                                   TFile& file,
                                   const toml::table& resultConfig,
                                   RenderResult& result) {
            const bool hasSources = resultConfig["sources"].as_array() != nullptr;
            const auto search = resultConfig["source_search"].value<std::string>();

            if (hasSources && search) {
                throw std::runtime_error(resultContext(result.name) + ": cannot use both sources and source_search");
            }
            if (!hasSources && !search) {
                throw std::runtime_error(resultContext(result.name) + ": must define sources or source_search");
            }

            std::vector<std::string> paths;
            std::vector<const toml::table*> sourceTables;
            if (search) {
                paths = searchObjects(file, *search);
                if (paths.empty()) {
                    throw std::runtime_error(resultContext(result.name) + ": source_search '" + *search + "' found no objects");
                }
                if (paths.size() > 1 && !result.modeExplicit && result.mode != Mode::Overlay) {
                    result.mode = Mode::Grid;
                }
            } else {
                sourceTables = readSourceTables(resultConfig, result.name);
                for (const toml::table* source : sourceTables) {
                    const auto path = (*source)["path"].value<std::string>();
                    if (!path || path->empty()) {
                        throw std::runtime_error(resultContext(result.name) + ": every sources[] entry must define path");
                    }
                    paths.push_back(*path);
                }
            }

            std::vector<Color_t> palette;
            if (const toml::array* arr = resultConfig["palette"].as_array()) {
                for (const toml::node& item : *arr) {
                    if (const auto s = item.value<std::string>()) {
                        palette.push_back(parseColor(*s));
                    } else if (const auto n = item.value<int64_t>()) {
                        palette.push_back(static_cast<Color_t>(*n));
                    }
                }
            }

            for (std::size_t i = 0; i < paths.size(); ++i) {
                const toml::table* sourceConfig = i < sourceTables.size() ? sourceTables[i] : nullptr;
                std::optional<Color_t> palColor;
                if (!palette.empty()) palColor = palette[i % palette.size()];
                result.sources.push_back(
                    resolveSource(paint, file, resultConfig, result, paths[i], sourceConfig, i, palColor));
            }
        }

        inline void finaliseLayout(RenderResult& result) {
            const std::size_t n = result.sources.size();
            if (n == 0) {
                throw std::runtime_error(resultContext(result.name) + ": resolved no sources");
            }
            if (result.mode == Mode::Single && n != 1) {
                throw std::runtime_error(resultContext(result.name) + ": single mode requires exactly one source");
            }
            if (result.mode != Mode::Grid) {
                result.rows = 1;
                result.cols = 1;
                return;
            }

            if (result.rows <= 0 && result.cols <= 0) {
                result.cols = static_cast<int>(std::ceil(std::sqrt(static_cast<double>(n))));
                result.rows = static_cast<int>(std::ceil(static_cast<double>(n) / result.cols));
            } else if (result.rows <= 0) {
                result.rows = static_cast<int>(std::ceil(static_cast<double>(n) / result.cols));
            } else if (result.cols <= 0) {
                result.cols = static_cast<int>(std::ceil(static_cast<double>(n) / result.rows));
            }

            if (result.rows * result.cols < static_cast<int>(n)) {
                throw std::runtime_error(resultContext(result.name) + ": grid layout has fewer pads than sources");
            }
        }

    } // namespace detail

    inline RenderPlan resolveBook(const PaintBook& book) {
        const toml::table& paint = detail::paintTable(book);
        RenderPlan plan;

        plan.rootFile = paint["root_file"].value_or(std::string{});
        if (plan.rootFile.empty()) {
            throw std::runtime_error("Paint config [paint].root_file is required");
        }

        plan.file.reset(TFile::Open(plan.rootFile.c_str(), "READ"));
        if (!plan.file || plan.file->IsZombie()) {
            throw std::runtime_error("Paint root_file cannot be opened: " + plan.rootFile);
        }

        std::string resultDir = paint["result_dir"].value_or(std::string{kResultDirDefault});
        std::vector<std::string> formats = detail::readStringArray(paint["formats"], {"png"});
        bool overwrite = paint["overwrite"].value_or(true);
        int imageScale = paint["image_scale"].value_or(1);

        const toml::table* defaultTable = detail::getTable(paint, "default");
        const std::vector<std::string> resultNames = detail::readRequiredResults(paint);
        plan.results.reserve(resultNames.size());

        for (const std::string& name : resultNames) {
            const toml::table* resultConfig = detail::resultTable(paint, name, detail::resultContext(name));

            RenderResult result;
            result.name = name;
            result.outputName = name;
            result.resultDir = resultDir;
            result.formats = formats;
            result.overwrite = overwrite;
            result.imageScale = imageScale < 1 ? 1 : imageScale;

            if (defaultTable != nullptr) {
                detail::mergeDirectRenderSettings(*defaultTable, result, "Paint default", false, false);
                mergeStyle(*defaultTable, result.style);
            }

            detail::mergeResultVisual(paint, name, *resultConfig, result);
            detail::resolveSources(paint, *plan.file, *resultConfig, result);
            detail::finaliseLayout(result);

            plan.results.push_back(std::move(result));
        }

        return plan;
    }

    inline void printPlan(const RenderPlan& plan, std::ostream& os) {
        os << "Paint render plan\n";
        os << "  root_file: " << plan.rootFile << '\n';
        os << "  results: " << plan.results.size() << '\n';

        for (const RenderResult& result : plan.results) {
            os << "\n[" << result.name << "]\n";
            os << "  mode: " << modeName(result.mode) << '\n';
            os << "  output: " << result.resultDir << "/" << result.outputName << '\n';
            os << "  formats:";
            for (const std::string& format : result.formats) os << ' ' << format;
            os << '\n';
            os << "  layout: " << result.rows << "x" << result.cols << '\n';
            os << "  style: line_color=" << result.style.line.color
               << " log_y=" << (result.style.logY ? "true" : "false")
               << " draw_option=" << result.style.drawOption << '\n';
            for (const ResolvedSource& source : result.sources) {
                os << "  - " << source.path
                   << " [" << objectKindName(source.kind)
                   << ", " << source.rootClass << "]";
                if (!source.label.empty()) os << " label=\"" << source.label << "\"";
                os << " line_color=" << source.style.line.color;
                os << '\n';
            }
        }
    }

} // namespace Paint
