# Currently you have by hand to remove the pedantic options in:
# $(MYPYTHIA)/Makefile.inc
# to make charged_particle_tree compile (step 3)

SHELL = /bin/sh

-include $(MYPYTHIA)/Makefile.inc

# PYTHIA variables

PYTHIA_INCDIR=$(PYTHIA8)/include
PYTHIA_LIBDIR=$(PYTHIA8)/lib

# ROOT variables (ROOTCFLAGS also includes include path)
ROOTCFLAGS=$(shell root-config --cflags)
ROOTLIBS=$(shell root-config --glibs)

# There is no default behaviour, so remind user.
all:
	@echo "Usage: make XXX, where XXX.cc is your program"

# Create an executable for one of the normal test programs
%:	%.cc $(PYTHIA_LIBDIR)/libpythia8.so #dependencies
	$(CXX) $(CXXFLAGS) $(ROOTCFLAGS) -I$(PYTHIA_INCDIR) \
	$@.cc -o $@.exe \
	-L$(PYTHIA_LIBDIR) -lpythia8 \
	$(ROOTLIBS) -lEG


# Clean up: remove executables and outdated files.
.PHONY: clean
clean:
	rm -f *.exe
	rm -f *~; rm -f \#*; rm -f core*
