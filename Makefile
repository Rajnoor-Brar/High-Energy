SHELL = /bin/sh

# Load user-provided CXXFLAGS from Pythia, then override strict options
-include $(MYPYTHIA)/Makefile.inc

# Remove -pedantic and -Werror (automatically)
CXXFLAGS := $(filter-out -Werror -pedantic,$(CXXFLAGS)) -mcpu=native -O3

# Pythia paths
PYTHIA_INCDIR = $(shell pythia8-config --includedir)
PYTHIA_LIBDIR = $(shell pythia8-config --libdir)

# ROOT paths
ROOTCFLAGS = $(shell root-config --cflags)
ROOTLIBS   = $(shell root-config --glibs)

# Default reminder
all:
	@echo "Usage: make <program> or make <program>.exe (source file must be <program>.cc)"

# Rule: source.cc → executable.exe
%.exe: %.cc $(PYTHIA_LIBDIR)/libpythia8.dylib
	$(CXX) $(CXXFLAGS) $(ROOTCFLAGS) -I$(PYTHIA_INCDIR) \
	$< -o $@ \
	$(ROOTLIBS) -lEG \
	-L$(PYTHIA_LIBDIR) -lpythia8 \
	-Wl,-rpath,$(PYTHIA_LIBDIR)
	@echo "$< --> $@"
# Allow `make myfile` as alias for `make myfile.exe`
%: %.exe
	@true

# Clean rule
.PHONY: clean
clean:
	rm -f *.exe *~ \#* core*
