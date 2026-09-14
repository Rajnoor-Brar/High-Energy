The folder contains the files for ZEUS 2012 Inclusive jet photoproduction and the subsequent predictions for EIC energies
The folder contain two directories
1. zeus_2012
	1.1 zeus_pdf: Variation with proton PDFs (LHC21, MSTW2008, NNPDF, NNPDF NLO)
	1.2 zeus_ptref: Variation with pTref (3.0, 3.2, 3.2 (no mpi), 3.4 GeV)
	(These two folders contain the cmnd files which could be run on PYTHIA with main42.cc or main132)

#Commands to run these files
(in the singularity environment)
make main42 #main132 based on the PYTHIA version
./main42 <cmnd-file.cmnd> <hepmc-output.hepmc> > <log-file>
# To run the rivet analysis add the following paths
export PYTHONPATH=/usr/local/lib/python3.10/site-packages 
export LD_LIBRARY_PATH=/usr/local/lib/
rivet -a <analysis-name> <hepmc-output.hepmc> #This will produce a yoda file
#For ZEUS 2012 inclusive-jet photoproduction analysis ZEUS_2012_l1116258
rivet-mkhtml Rivet.yoda #Make graph from the analysis
yodamerge -o <merged-yoda.yoda> file1.yoda file2.yoda 

2. eic
	2.1 eic_energies: Comparison with energies 18x275, 10x100 5x41 (140.7, 63.2, 28.6 GeV)
	2.2 eic_pdf: Comparison between LHC21 and NNPDF_NLO
	2.3 eic_ptref: Comparison of pTref 3.2 and 3.4
#Since there is no analysis for EIC, we use same as that ZEUS_2012 by making our own analysis
rivet-mkanalysis <name of analysis> (This will create 3 files <filename>.cc, <filename>.plot, <filename>.info)
rivet-build Rivet<filename>.so <filename>.cc

#Installing LHAPDF (to be done after exporting pythonpath and ldlibrary path)

wget https://lhapdf.hepforge.org/downloads/?f=LHAPDF-6.X.Y.tar.gz -O LHAPDF-6.X.Y.tar.gz 
# Change X Y to current version
tar xf LHAPDF-6.X.Y.tar.gz
cd LHAPDF-6.X.Y
./configure --prefix=/path/for/installation # No need to add prefix, it will install in the usr/local of singularity 
make
make install

The downloadable PDF sets are packaged as tarballs, which
must be expanded to be used. The simplest way to do this is with
the 'lhapdf' script, e.g. to install the CT10nlo PDF set:
  lhapdf install CT10nlo
The same effect can be achieved manually with, e.g.:
  wget http://lhapdfsets.web.cern.ch/lhapdfsets/current/CT10nlo.tar.gz -O- | tar xz -C /usr/local/share/LHAPDF

In order to make comparison of EIC energies one has to modify the yoda files such that the analysis file is the same for all only then the overlap can happen, for e.g

BEGIN YODA_BINNEDESTIMATE<I>_V3 /H1_2015_I1343110 (this has to be same for all the file you wish to compare)/d01-x01-y01
Path: /H1_2015_I1343110 (this has to be same for all the file you wish to compare)/d01-x01-y01
ScaledBy: 1.42445895190470950e+00
Title: 
Type: BinnedEstimate<i>
---
Edges(A1): [319]
ErrorLabels: ["stats"]
# value      	errDn(1)     	errUp(1)     	
nan          	---          	---          	
2.108199e+02 	-1.732929e+01	1.732929e+01 	
END YODA_BINNEDESTIMATE<I>_V3

