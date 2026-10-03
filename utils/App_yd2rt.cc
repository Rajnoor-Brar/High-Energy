// utils/App_yd2rt.cc — YODA → ROOT, and a sweep's YODAs into one file (docs/05_Tools_Reference.md §16).
// requires: yoda root
//
//     App_yd2rt.exe IN.yoda OUT.root [GLOB …] [--keep-raw]                    (GLOB: YODA paths to convert)
//     App_yd2rt.exe --merge OUT.root|OUT.yoda NAME=IN.yoda … [--keep-raw] [--select GLOB] [--points FILE]
//
// One TDirectory per analysis, one ROOT object per YODA object:
//     Histo1D, Estimate1D   → TH1D   (Estimate errors: the average of the down/up total errors)
//     Histo2D, Estimate2D   → TH2D
//     Scatter2D             → TGraphAsymmErrors
//     Counter, Estimate0D   → a one-bin TH1D
// Rivet 4 writes its finalised histograms as Estimate1D and the unscaled fills under /RAW. /RAW and
// /TMP are skipped unless --keep-raw, which also writes <name>__entries (per-bin raw entry counts)
// beside each /RAW histogram. A variant path (/photo_eic:R=0.4/d01-x01-y01) becomes the
// directory photo_eic__R-0.4 (directories nest as the path does). Every object's title is its
// original YODA path, and the `paths` TTree maps each ROOT path back to it.
//
// --merge (plotmerge, `hep plot`): each input's objects go under a directory named for it, its point
// (27x920_MSTW08lo/photo_eic/d01-x01-y01); the `paths` tree says which point, and --points stores
// the sweep's points.json in the file as the TNamed "points.json". Into a .yoda file the name becomes
// a path prefix instead (/27x920_MSTW08lo/photo_eic/d01-x01-y01): one YODA file for the sweep.
//
// The output is the non-temporary ROOT file of the brief (§Plotting): a product in results/.
// Exit codes: utils/Kit.hh's one table (V73): 0 ok, 2 usage, 4 input, 5 output.

#include "Kit.hh"
#include "Status.hh"

#include "YODA/BinnedEstimate.h"
#include "YODA/Counter.h"
#include "YODA/Estimate0D.h"
#include "YODA/Histo.h"
#include "YODA/IO.h"
#include "YODA/Scatter.h"

#include "TDirectory.h"
#include "TFile.h"
#include "TGraphAsymmErrors.h"
#include "TH1D.h"
#include "TH2D.h"
#include "TNamed.h"
#include "TTree.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <fnmatch.h>
#include <fstream>
#include <sstream>
#include <map>
#include <string>
#include <vector>

namespace {

    using Kit::Ok, Kit::Usage, Kit::Input, Kit::Output;   // V73

    double finite(double value) { return std::isfinite(value) ? value : 0.0; }

    // Estimate errors: the average of the (absolute) total down and up errors.
    template <class B>
    double estimateError(const B& bin) {
        const auto [down, up] = bin.totalErr();
        return finite(0.5 * (std::fabs(down) + std::fabs(up)));
    }

    std::string safe(std::string text) {
        std::string out;
        for (char c : text) {
            if (c == ':') out += "__";
            else if (c == '=') out += "-";
            else if (c == ' ') out += "_";
            else out += c;
        }
        return out;
    }

    // "/photo_eic:R=0.4/d01-x01-y01" → {"photo_eic__R-0.4", "d01-x01-y01"}; "/_XSEC" → {"", "_XSEC"}
    std::pair<std::string, std::string> split(const std::string& path) {
        const std::string body = path.empty() || path[0] != '/' ? path : path.substr(1);
        const auto slash = body.rfind('/');
        if (slash == std::string::npos) return {"", safe(body)};
        return {safe(body.substr(0, slash)), safe(body.substr(slash + 1))};
    }

    // Nested, as in the YODA path: /RAW/photo_eic/d01 → RAW/photo_eic/d01.
    TDirectory* directory(TFile& file, const std::string& name) {
        TDirectory* here = &file;
        size_t start = 0;
        while (start < name.size()) {
            const size_t end = name.find('/', start);
            const std::string part = name.substr(start, end == std::string::npos ? std::string::npos : end - start);
            TDirectory* next = here->GetDirectory(part.c_str());
            here = next ? next : here->mkdir(part.c_str());
            if (end == std::string::npos) break;
            start = end + 1;
        }
        return here;
    }

    TH1D* fromEstimate1D(const YODA::Estimate1D& e, const std::string& name) {
        const auto edges = e.edges<0>();
        auto* h = new TH1D(name.c_str(), e.path().c_str(), static_cast<int>(edges.size()) - 1, edges.data());
        for (size_t i = 0; i < edges.size() + 1; ++i) {  // 0 = underflow … n+1 = overflow
            const auto& bin = e.bin(i);
            h->SetBinContent(static_cast<int>(i), finite(bin.val()));
            h->SetBinError(static_cast<int>(i), estimateError(bin));
        }
        h->SetEntries(e.numBins());
        return h;
    }

    TH1D* fromHisto1D(const YODA::Histo1D& y, const std::string& name) {
        const auto edges = y.edges<0>();
        auto* h = new TH1D(name.c_str(), y.path().c_str(), static_cast<int>(edges.size()) - 1, edges.data());
        for (size_t i = 0; i < edges.size() + 1; ++i) {
            const auto& bin = y.bin(i);
            h->SetBinContent(static_cast<int>(i), bin.sumW());
            h->SetBinError(static_cast<int>(i), std::sqrt(std::fabs(bin.sumW2())));
        }
        h->SetEntries(y.numEntries());
        return h;
    }

    template <class T>
    TH2D* from2D(const T& y, const std::string& name) {
        const auto xs = y.template edges<0>();
        const auto ys = y.template edges<1>();
        auto* h = new TH2D(name.c_str(), y.path().c_str(), static_cast<int>(xs.size()) - 1, xs.data(),
                           static_cast<int>(ys.size()) - 1, ys.data());
        for (size_t ix = 0; ix < xs.size() + 1; ++ix) {
            for (size_t iy = 0; iy < ys.size() + 1; ++iy) {
                const auto& bin = y.bin(y.binning().localToGlobalIndex(std::array<size_t, 2>{ix, iy}));
                if constexpr (std::is_same_v<T, YODA::Estimate2D>) {
                    h->SetBinContent(static_cast<int>(ix), static_cast<int>(iy), finite(bin.val()));
                    h->SetBinError(static_cast<int>(ix), static_cast<int>(iy), estimateError(bin));
                } else {
                    h->SetBinContent(static_cast<int>(ix), static_cast<int>(iy), bin.sumW());
                    h->SetBinError(static_cast<int>(ix), static_cast<int>(iy), std::sqrt(std::fabs(bin.sumW2())));
                }
            }
        }
        return h;
    }

    TGraphAsymmErrors* fromScatter2D(const YODA::Scatter2D& s, const std::string& name) {
        auto* g = new TGraphAsymmErrors(static_cast<int>(s.numPoints()));
        g->SetName(name.c_str());
        g->SetTitle(s.path().c_str());
        int i = 0;
        for (const auto& p : s.points()) {
            g->SetPoint(i, p.x(), p.y());
            g->SetPointError(i, std::fabs(p.xErrMinus()), p.xErrPlus(), std::fabs(p.yErrMinus()), p.yErrPlus());
            ++i;
        }
        return g;
    }

    TH1D* oneBin(const std::string& name, const std::string& title, double value, double error, double entries) {
        auto* h = new TH1D(name.c_str(), title.c_str(), 1, 0.0, 1.0);
        h->SetBinContent(1, finite(value));
        h->SetBinError(1, finite(error));
        h->SetEntries(entries);
        return h;
    }

    bool selected(const std::string& path, bool keepRaw, const std::vector<std::string>& select) {
        if (!keepRaw && (path.rfind("/RAW/", 0) == 0 || path.rfind("/TMP/", 0) == 0)) return false;
        if (select.empty()) return true;
        for (const auto& glob : select)
            if (fnmatch(glob.c_str(), path.c_str(), 0) == 0) return true;
        return false;
    }

    // Every selected object of one YODA file into `file`, under `prefix/` (empty: at the top).
    struct Counts { long written = 0, skipped = 0; };
    Counts convert(const std::vector<YODA::AnalysisObject*>& objects, TFile& file, const std::string& prefix,
                   bool keepRaw, const std::vector<std::string>& select, TTree& paths, std::string& point,
                   std::string& rootPath, std::string& yodaPath, Status::Reporter& status) {
        Counts n;
        for (auto* ao : objects) {
            const std::string path = ao->path();
            if (!selected(path, keepRaw, select)) { ++n.skipped; continue; }
            auto [dir, name] = split(path);
            if (!prefix.empty()) dir = dir.empty() ? prefix : prefix + "/" + dir;
            TObject* made = nullptr;
            if (auto* e = dynamic_cast<YODA::Estimate1D*>(ao)) made = fromEstimate1D(*e, name);
            else if (auto* h = dynamic_cast<YODA::Histo1D*>(ao)) made = fromHisto1D(*h, name);
            else if (auto* e2 = dynamic_cast<YODA::Estimate2D*>(ao)) made = from2D(*e2, name);
            else if (auto* h2 = dynamic_cast<YODA::Histo2D*>(ao)) made = from2D(*h2, name);
            else if (auto* sc = dynamic_cast<YODA::Scatter2D*>(ao)) made = fromScatter2D(*sc, name);
            else if (auto* c = dynamic_cast<YODA::Counter*>(ao)) made = oneBin(name, path, c->sumW(), std::sqrt(std::fabs(c->sumW2())), c->numEntries());
            else if (auto* e0 = dynamic_cast<YODA::Estimate0D*>(ao)) made = oneBin(name, path, e0->val(), estimateError(*e0), 1);
            else {
                status.log("warn", "skipped " + path + ": no ROOT form for a " + ao->type());
                ++n.skipped;
                continue;
            }
            TDirectory* target = directory(file, dir);
            target->cd();
            if (auto* h = dynamic_cast<TH1*>(made)) h->SetDirectory(target);
            made->Write(nullptr, TObject::kOverwrite);
            // A raw fill histogram also gets its per-bin entry counts, which a TH1D cannot carry: Paint's
            // min_entries voiding reads them (docs/05_Tools_Reference.md §17).
            if (auto* raw = dynamic_cast<YODA::Histo1D*>(ao); raw && path.rfind("/RAW/", 0) == 0) {
                TH1D* entries = fromHisto1D(*raw, name + "__entries");
                for (size_t i = 0; i < raw->edges<0>().size() + 1; ++i) {
                    entries->SetBinContent(static_cast<int>(i), raw->bin(i).numEntries());
                    entries->SetBinError(static_cast<int>(i), 0.0);
                }
                entries->SetDirectory(target);
                entries->Write(nullptr, TObject::kOverwrite);
                delete entries;
            }
            rootPath = dir.empty() ? name : dir + "/" + name;
            yodaPath = path;
            point = prefix;
            file.cd();
            paths.Fill();
            ++n.written;
            delete made;
        }
        return n;
    }

    int usage() {
        std::fputs("usage: App_yd2rt.exe IN.yoda OUT.root [GLOB …] [--keep-raw]\n"
                   "       App_yd2rt.exe --merge OUT.root|OUT.yoda NAME=IN.yoda … [--keep-raw] [--select GLOB] [--points FILE]\n",
                   stderr);
        return Usage;
    }

}  // namespace

int main(int argc, char** argv) {
    const Kit::Args args(argc, argv, {"select", "points"}, {"keep-raw", "merge"});
    if (!args.ok()) {
        if (!args.error().empty()) std::fprintf(stderr, "App_yd2rt: %s\n", args.error().c_str());
        return usage();
    }
    const bool keepRaw = args.has("keep-raw"), merge = args.has("merge");
    std::vector<std::string> positional = args.positional(), select = args.all("select");
    const std::string pointsFile = args.get("points");
    if (!merge && positional.size() > 2) {            // a plain conversion's GLOBs follow IN and OUT
        select.insert(select.end(), positional.begin() + 2, positional.end());
        positional.resize(2);
    }
    if ((!merge && positional.size() != 2) || (merge && positional.size() < 2)) return usage();
    Status::Reporter status;

    // the inputs: (name, path); a plain conversion has one, with no name
    std::vector<std::pair<std::string, std::string>> inputs;
    std::string out;
    if (merge) {
        out = positional[0];
        for (size_t i = 1; i < positional.size(); ++i) {
            const auto eq = positional[i].find('=');
            if (eq == std::string::npos || eq == 0) {
                status.log("error", "--merge takes NAME=IN.yoda, not " + positional[i]);
                return Usage;
            }
            inputs.emplace_back(positional[i].substr(0, eq), positional[i].substr(eq + 1));
        }
    } else {
        inputs.emplace_back("", positional[0]);
        out = positional[1];
    }

    std::vector<std::vector<YODA::AnalysisObject*>> read(inputs.size());
    for (size_t i = 0; i < inputs.size(); ++i) {
        try {
            read[i] = YODA::read(inputs[i].second);
        } catch (const std::exception& error) {
            status.log("error", "cannot read " + inputs[i].second + ": " + error.what());
            return Input;
        }
        if (read[i].empty()) {
            status.log("error", inputs[i].second + " holds no objects");
            return Input;
        }
    }
    auto release = [&] { for (auto& list : read) for (auto* ao : list) delete ao; };

    const bool toYoda = out.size() > 5 && out.compare(out.size() - 5, 5, ".yoda") == 0;
    if (toYoda) {                                  // one YODA file, the point as a path prefix
        if (!merge) { release(); return usage(); }
        std::vector<const YODA::AnalysisObject*> kept;
        long skipped = 0;
        for (size_t i = 0; i < inputs.size(); ++i)
            for (auto* ao : read[i]) {
                if (!selected(ao->path(), keepRaw, select)) { ++skipped; continue; }
                ao->setPath("/" + inputs[i].first + ao->path());
                kept.push_back(ao);
            }
        try {
            YODA::write(out, kept.begin(), kept.end());
        } catch (const std::exception& error) {
            status.log("error", "cannot write " + out + ": " + error.what());
            release();
            return Output;
        }
        status.summary("\"written\": " + std::to_string(kept.size()) + ", \"skipped\": " + std::to_string(skipped) +
                       ", \"inputs\": " + std::to_string(inputs.size()) + ", \"output\": " + Status::quote(out));
        release();
        return kept.empty() ? Input : Ok;
    }

    TFile file(out.c_str(), "RECREATE");
    if (file.IsZombie()) {
        status.log("error", "cannot write " + out);
        release();
        return Output;
    }
    std::string point, rootPath, yodaPath;
    TTree paths("paths", "ROOT path -> YODA path");
    if (merge) paths.Branch("point", &point);
    paths.Branch("root_path", &rootPath);
    paths.Branch("yoda_path", &yodaPath);

    Counts total;
    for (size_t i = 0; i < inputs.size(); ++i) {
        const Counts n = convert(read[i], file, inputs[i].first, keepRaw, select, paths, point, rootPath, yodaPath, status);
        total.written += n.written, total.skipped += n.skipped;
    }
    file.cd();
    paths.Write();
    if (!pointsFile.empty()) {                     // the sweep's points.json, so the file describes itself
        std::ifstream in(pointsFile);
        std::stringstream text;
        text << in.rdbuf();
        TNamed("points.json", text.str().c_str()).Write();
    }
    file.Close();
    release();

    status.summary("\"written\": " + std::to_string(total.written) + ", \"skipped\": " + std::to_string(total.skipped) +
                   ", \"inputs\": " + std::to_string(inputs.size()) + ", \"output\": " + Status::quote(out));
    return total.written ? Ok : Input;
}
