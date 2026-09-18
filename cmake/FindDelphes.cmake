# Delphes, only needed for the deferred in-process sink (09 §1; external Delphes needs no build option).
# Note the global `class Event` in DelphesClasses.h, which is why the C++ namespace is `Events` (13 §3).
include(HekitDependency)

set(_DELPHES_HINTS "$ENV{DELPHES_DIR}" "$ENV{HEP_INSTALL}/delphes")

find_path(Delphes_INCLUDE_DIR classes/DelphesClasses.h HINTS ${_DELPHES_HINTS}
          PATH_SUFFIXES include include/Delphes)
find_library(Delphes_LIBRARY NAMES Delphes HINTS ${_DELPHES_HINTS} PATH_SUFFIXES lib lib64)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Delphes
  REQUIRED_VARS Delphes_INCLUDE_DIR Delphes_LIBRARY
  FAIL_MESSAGE "Delphes not found - the in-process sink is unavailable (external Delphes still works)")

if(Delphes_FOUND AND NOT TARGET Delphes::Delphes)
  add_library(Delphes::Delphes INTERFACE IMPORTED GLOBAL)
  target_include_directories(Delphes::Delphes SYSTEM INTERFACE ${Delphes_INCLUDE_DIR})
  target_link_libraries(Delphes::Delphes INTERFACE ${Delphes_LIBRARY})
endif()
