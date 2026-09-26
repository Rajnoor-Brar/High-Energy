// utils/App_yd2rt.cc — YODA → ROOT (docs/rework_v2/05_Tools.md §6).
// requires: yoda root
//
//     App_yd2rt.exe IN.yoda OUT.root [GLOB …] [--keep-raw]      (GLOB: YODA paths to convert)
//
// One TDirectory per analysis, one ROOT object per YODA object:
//     Histo1D, Estimate1D   → TH1D   (Estimate errors: the average of the down/up total errors)
//     Histo2D, Estimate2D   → TH2D
//     Scatter2D             → TGraphAsymmErrors
//     Counter, Estimate0D   → a one-bin TH1D
// Rivet 4 writes its finalised histograms as Estimate1D and the unscaled fills under /RAW. /RAW and
// /TMP are skipped unless --keep-raw, which also writes <name>__entries (per-bin raw entry counts)
// beside each /RAW histogram. A variant path (/photo_eic:R=0.4/d01-x01-y01) becomes the
// directory photo_eic__R-0.4 (directories nest as the path does). Every object's title is its original YODA path, and the `paths` TTree
// maps each ROOT path back to it.
//
// The output is the non-temporary ROOT file of the brief (§Plotting): a product in results/.
// Exit codes (02 §9): 0 ok, 2 usage, 4 input, 5 output.

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
#include "TTree.h"

#include <array>
#include <cmath>
#include <cstdio>
#include <fnmatch.h>
#include <map>
#include <string>
#include <vector>

namespace {

    enum Exit { Ok = 0, Usage = 2, Input = 4, Output = 5 };

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
    TH2D* from2D(const T& y, const std::string& name, bool isEstimate) {
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
        (void)isEstimate;
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

}  // namespace

int main(int argc, char** argv) {
    std::vector<std::string> positional, select;
    bool keepRaw = false, bad = false;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--keep-raw") keepRaw = true;
        else if (arg == "--select" && i + 1 < argc) select.push_back(argv[++i]);
        else if (positional.size() >= 2 && arg.rfind("-", 0) != 0) select.push_back(arg);
        else if (arg.rfind("-", 0) == 0) bad = true;
        else positional.push_back(arg);
    }
    if (bad || positional.size() != 2) {
        std::fputs("usage: App_yd2rt.exe IN.yoda OUT.root [GLOB …] [--keep-raw]\n", stderr);
        return Usage;
    }
    const std::string in = positional[0], out = positional[1];
    Status::Reporter status;

    std::vector<YODA::AnalysisObject*> objects;
    try {
        objects = YODA::read(in);
    } catch (const std::exception& error) {
        status.log("error", "cannot read " + in + ": " + error.what());
        return Input;
    }
    if (objects.empty()) {
        status.log("error", in + " holds no objects");
        return Input;
    }

    TFile file(out.c_str(), "RECREATE");
    if (file.IsZombie()) {
        status.log("error", "cannot write " + out);
        return Output;
    }
    std::string rootPath, yodaPath;
    TTree paths("paths", "ROOT path -> YODA path");
    paths.Branch("root_path", &rootPath);
    paths.Branch("yoda_path", &yodaPath);

    long written = 0, skipped = 0;
    std::map<std::string, long> kinds;
    for (auto* ao : objects) {
        const std::string path = ao->path();
        if (!keepRaw && (path.rfind("/RAW/", 0) == 0 || path.rfind("/TMP/", 0) == 0)) { ++skipped; continue; }
        if (!select.empty()) {
            bool wanted = false;
            for (const auto& glob : select) wanted |= fnmatch(glob.c_str(), path.c_str(), 0) == 0;
            if (!wanted) { ++skipped; continue; }
        }
        const auto [dir, name] = split(path);
        TObject* made = nullptr;
        if (auto* e = dynamic_cast<YODA::Estimate1D*>(ao)) made = fromEstimate1D(*e, name);
        else if (auto* h = dynamic_cast<YODA::Histo1D*>(ao)) made = fromHisto1D(*h, name);
        else if (auto* e2 = dynamic_cast<YODA::Estimate2D*>(ao)) made = from2D(*e2, name, true);
        else if (auto* h2 = dynamic_cast<YODA::Histo2D*>(ao)) made = from2D(*h2, name, false);
        else if (auto* s = dynamic_cast<YODA::Scatter2D*>(ao)) made = fromScatter2D(*s, name);
        else if (auto* c = dynamic_cast<YODA::Counter*>(ao)) made = oneBin(name, path, c->sumW(), std::sqrt(std::fabs(c->sumW2())), c->numEntries());
        else if (auto* e0 = dynamic_cast<YODA::Estimate0D*>(ao)) made = oneBin(name, path, e0->val(), estimateError(*e0), 1);
        else {
            status.log("warn", "skipped " + path + ": no ROOT form for a " + ao->type());
            ++skipped;
            continue;
        }
        TDirectory* target = directory(file, dir);
        target->cd();
        if (auto* h = dynamic_cast<TH1*>(made)) h->SetDirectory(target);
        made->Write(nullptr, TObject::kOverwrite);
        // A raw fill histogram also gets its per-bin entry counts, which a TH1D cannot carry: Paint's
        // min_entries voiding reads them (docs/rework_v2/05_Tools.md §7).
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
        file.cd();
        paths.Fill();
        ++written;
        ++kinds[ao->type()];
        delete made;
    }
    file.cd();
    paths.Write();
    file.Close();
    for (auto* ao : objects) delete ao;

    std::string summary = "\"written\": " + std::to_string(written) + ", \"skipped\": " + std::to_string(skipped) +
                          ", \"output\": " + Status::quote(out);
    status.summary(summary);
    return written ? Ok : Input;
}
