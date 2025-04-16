import ROOT
import csv

# Open the ROOT file
file = ROOT.TFile("pp_500GeV-15TeV_30x2k.root", "READ")

# Get the TTree (assuming it is named "tree")
tree = file.Get("p-p_14000GeV")

# Define which branches to extract
branches = ["px", "py", "pz", "E"]  # Replace with actual branch names

# Open a CSV file to write
with open("output.csv", "w", newline='') as csvfile:
    writer = csv.writer(csvfile)
    
    # Write the header
    writer.writerow(branches)
    
    # Loop over the tree entries
    for event in tree:
        row = [getattr(event, branch) for branch in branches]
        writer.writerow(row)

print("CSV file saved successfully!")
