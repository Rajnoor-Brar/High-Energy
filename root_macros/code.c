void save_hist_png() {

    // -----------------------------
    // 1. Create histogram
    // -----------------------------
    TH1F* h1 = new TH1F("h1", "Gaussian Distribution", 100, -5, 5);

    // -----------------------------
    // 2. Fill histogram (example)
    // -----------------------------
    TRandom3 rng(0);
    for (int i = 0; i < 100000; ++i) {
        h1->Fill(rng.Gaus(0, 1));
    }

    // -----------------------------
    // 3. Create canvas (high-res)
    // -----------------------------
    TCanvas* c1 = new TCanvas("c1", "Canvas", 2000, 1500);  // high resolution

    // -----------------------------
    // 4. Style (important for clarity)
    // -----------------------------
    gStyle->SetOptStat(1110);

    h1->SetLineWidth(3);
    h1->SetLineColor(kBlue);

    h1->SetTitle("Gaussian Distribution;X;Counts");

    h1->GetXaxis()->SetTitleSize(0.05);
    h1->GetYaxis()->SetTitleSize(0.05);

    h1->GetXaxis()->SetLabelSize(0.04);
    h1->GetYaxis()->SetLabelSize(0.04);

    // -----------------------------
    // 5. Draw
    // -----------------------------
    h1->Draw("HIST");

    // -----------------------------
    // 6. Save as high-res PNG
    // -----------------------------
    c1->SaveAs("histogram.png");
}