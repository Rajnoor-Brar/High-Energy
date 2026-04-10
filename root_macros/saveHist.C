// SaveHistStyled.C
#include <iostream>

#include "TCanvas.h"
#include "TError.h"
#include "TFile.h"
#include "TImage.h"
#include "TPaveText.h"
#include "TPaveStats.h"
#include "TROOT.h"
#include "TStyle.h"
#include "TSystem.h"
#include "TLegend.h"
#include "TH1.h"
#include "TDirectory.h"
#include "TString.h"

void saveHist(const char* histName, const char* outBaseName)
{
    int scale = 4;
    gROOT->SetBatch(kTRUE);

    // -------------------------
    // Global Style
    // -------------------------
    gStyle->SetOptStat("emr");
    gStyle->SetOptTitle(1);
    gStyle->SetPadTickX(1);
    gStyle->SetPadTickY(1);

    gStyle->SetTitleFont(43, "XYZ");
    gStyle->SetLabelFont(43, "XYZ");
    gStyle->SetTitleSize(scale*17, "XYZ");
    gStyle->SetLabelSize(scale*10, "XYZ");

    gStyle->SetTitleBorderSize(0);
    gStyle->SetTitleAlign(23);

    gStyle->SetFrameLineWidth(scale*1);   // axis frame line width

    gROOT->ForceStyle();

    // -------------------------
    // Fetch Histogram
    // -------------------------
    TObject* obj = gROOT->FindObject(histName);
    if (!obj && gDirectory) obj = gDirectory->Get(histName);

    if (!obj) {
        Error("saveHist", "Histogram '%s' not found.", histName);
        return;
    }

    TH1* hIn = dynamic_cast<TH1*>(obj);
    if (!hIn) {
        Error("saveHist", "'%s' is not TH1.", histName);
        return;
    }

    TH1* h = dynamic_cast<TH1*>(hIn->Clone(Form("%s__styled", histName)));
    if (!h) {
        Error("saveHist", "Clone failed.");
        return;
    }
    h->SetDirectory(nullptr);
    h->UseCurrentStyle();

    // -------------------------
    // Histogram Styling
    // -------------------------
    h->SetStats(1);   // keep stats on — we'll reposition after Draw()

    h->SetLineColor(kBlue - 6);
    h->SetLineWidth(2);
    h->SetFillColor(kBlue - 7);
    h->SetFillStyle(3003);

    h->GetXaxis()->SetTitleFont(43);
    h->GetYaxis()->SetTitleFont(43);
    h->GetXaxis()->SetLabelFont(43);
    h->GetYaxis()->SetLabelFont(43);

    h->GetXaxis()->SetTitleSize(scale*27);
    h->GetYaxis()->SetTitleSize(scale*27);
    h->GetXaxis()->SetLabelSize(scale*20);
    h->GetYaxis()->SetLabelSize(scale*20);

    h->GetXaxis()->CenterTitle();
    h->GetYaxis()->CenterTitle();

    h->GetXaxis()->SetTitleOffset(1.1);
    h->GetYaxis()->SetTitleOffset(1.35);

    h->GetYaxis()->SetMaxDigits(3);
    h->SetMinimum(0);

    // -------------------------
    // Canvas Setup
    // -------------------------
    gSystem->mkdir("results", kTRUE);

    TString outName = outBaseName;
    if (!outName.EndsWith(".png")) outName += ".png";
    TString outPath = "results/" + outName;

    TCanvas c("c", "c", scale*900, scale*600);

    c.SetLeftMargin(0.12);
    c.SetRightMargin(0.05);
    c.SetBottomMargin(0.12);
    c.SetTopMargin(0.08);
    c.SetTicks(1, 1);
    c.SetFillColor(0);
    c.SetBorderMode(0);
    c.SetFrameBorderMode(0);

    // -------------------------
    // Draw
    // -------------------------
    h->Draw("HIST");
    c.Update();

    // -------------------------
    // Reposition stats box — inside frame, top-right corner
    // Coords are in NDC (0–1) relative to the canvas
    // Right edge of frame  = 1 - RightMargin  = 0.95
    // Top edge of frame    = 1 - TopMargin     = 0.92
    // -------------------------
    if (TPaveStats* st = dynamic_cast<TPaveStats*>(h->FindObject("stats"))) {
        const double statsW  = 0.18;   // width  in NDC — adjust to taste
        const double statsH  = 0.10;   // height in NDC — adjust to taste
        const double right   = 1.0 - c.GetRightMargin()  - 0.03;  // small inset
        const double top     = 1.0 - c.GetTopMargin()    - 0.03;

        st->SetX2NDC(right);
        st->SetY2NDC(top);
        st->SetX1NDC(right - statsW);
        st->SetY1NDC(top   - statsH);

        st->SetTextFont(43);
        st->SetTextSize(scale*12);
        st->SetBorderSize(2);
        st->SetFillColor(0);
        st->SetFillStyle(1001);   // solid white — readable over bars
        c.Modified();
        c.Update();
    }

    // Style title box
    if (TPaveText* title = dynamic_cast<TPaveText*>(c.GetPrimitive("title"))) {
        title->SetTextFont(43);
        title->SetTextSize(scale*24);
        title->SetBorderSize(0);
        title->SetFillColor(0);
        title->SetFillStyle(0);
        c.Modified();
        c.Update();
    }

    // -------------------------
    // Save via TImage (explicit resolution, bypasses Retina scaling)
    // -------------------------
    const int outW = 3600;
    const int outH = 2400;

    TImage* img = TImage::Create();
    if (!img) {
        Error("saveHist", "TImage::Create() failed.");
        delete h;
        return;
    }

    img->FromPad(&c, 0, 0, outW, outH);
    img->WriteImage(outPath);
    delete img;

    Info("saveHist", "Saved %dx%d px -> %s", outW, outH, outPath.Data());

    delete h;
}