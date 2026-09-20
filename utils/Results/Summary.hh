#pragma once

// ── Results/Summary.hh ───────────────────────────────────────────────────────
// `run.summary.json`: what `hep-run` alone knows about the run it just did (07 §2).
//
// This is deliberately **not** `provenance.json`. Provenance is assembled by `hekit.prov` (P3-S03),
// which knows the git state, the configuration and the resources; `hep-run` knows the counts, the
// seeds the instances really used, σ with its error, the warnings and what it wrote. Keeping the two
// apart means a run never fails because provenance could not be gathered, and `hep` never has to parse
// a log to find a number the binary already had.
//
// The escaping comes from `Status`, so the codebase has exactly one JSON escaper.

#include <string>
#include <vector>

#include "Core/Provenance.hh"
#include "Sink/Types.hh"
#include "Status/Writer.hh"

namespace Results {

    inline std::string summaryJson(
        const Core::RunRecord& record, const std::vector<Sink::Output>& outputs,
        const std::string& finished_at,
        const std::vector<std::pair<std::string, std::string>>& inputs = {}) {
        const Core::Build build = Core::build();
        std::string json = "{\n";
        json += "  \"schema\": 2,\n";
        json += "  \"point\": \"" + Status::escape(record.point) + "\",\n";
        json += "  \"hash\": \"" + Status::escape(record.hash) + "\",\n";
        json += "  \"origin\": \"" + Status::escape(record.origin) + "\",\n";
        json += "  \"host\": \"" + Status::escape(Core::hostname()) + "\",\n";
        json += "  \"started\": \"" + Status::escape(record.started) + "\",\n";
        json += "  \"finished\": \"" + Status::escape(finished_at) + "\",\n";
        json += "  \"build\": {\"version\": \"" + Status::escape(build.version) + "\", \"type\": \"" +
                Status::escape(build.type) + "\", \"compiler\": \"" + Status::escape(build.compiler) +
                "\"},\n";
        json += "  \"run\": {\n";
        json += "    \"events_requested\": " + std::to_string(record.events_requested) + ",\n";
        json += "    \"events\": " + std::to_string(record.accepted) + ",\n";
        // Attempts are not successes (00/B21): both numbers are kept, and their difference is the
        // generator's failure rate, which is a physics observation rather than an error.
        json += "    \"attempted\": " + std::to_string(record.attempted) + ",\n";
        json += "    \"threads\": " + std::to_string(record.threads) + ",\n";
        json += "    \"chunk\": " + std::to_string(record.chunk) + ",\n";
        json += "    \"mode\": \"" + Status::escape(record.mode) + "\",\n";
        json += "    \"source\": \"" + Status::escape(record.source) + "\",\n";
        json += "    \"stopped\": " + std::string(record.stopped ? "true" : "false") + ",\n";
        json += "    \"wall_s\": " + Status::number(record.wall_seconds) + ",\n";
        json += "    \"xsec_pb\": " + Status::number(record.xsec_pb) + ",\n";
        json += "    \"xsec_err_pb\": " + Status::number(record.xsec_error_pb) + ",\n";
        json += "    \"seeds\": {\"point\": " + std::to_string(record.seed) + ", \"instances\": " +
                Status::jsonList(record.seeds) + "},\n";
        json += "    \"warnings\": {";
        for (std::size_t index = 0; index < record.warnings.size(); ++index)
            json += (index ? ", " : "") + std::string("\"") +
                    Status::escape(record.warnings[index].first) + "\": " +
                    std::to_string(record.warnings[index].second);
        json += "}\n  },\n";
        json += "  \"outputs\": [";
        for (std::size_t index = 0; index < outputs.size(); ++index) {
            const Sink::Output& output = outputs[index];
            json += (index ? ",\n" : "\n") + std::string("    {\"kind\": \"") +
                    Status::escape(output.kind) + "\", \"path\": \"" + Status::escape(output.path) +
                    "\", \"partial\": " + (output.partial ? "true" : "false") + "}";
        }
        json += outputs.empty() ? "]" : "\n  ]";
        // What the sinks read, as opposed to what they wrote: a model file and its hash, so two runs
        // that disagree can be asked whether they really used the same weights (05 §6).
        json += ",\n  \"inputs\": {";
        for (std::size_t index = 0; index < inputs.size(); ++index)
            json += (index ? ",\n" : "\n") + std::string("    \"") +
                    Status::escape(inputs[index].first) + "\": \"" +
                    Status::escape(inputs[index].second) + "\"";
        json += inputs.empty() ? "}\n" : "\n  }\n";
        json += "}\n";
        return json;
    }

}  // namespace Results
