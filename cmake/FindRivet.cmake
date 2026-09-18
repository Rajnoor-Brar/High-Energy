# Rivet via `rivet-config` (09 §1). Defines the imported target Rivet::Rivet.
include(HekitDependency)

hekit_config_tool(_Rivet_compile COMMAND rivet-config --cppflags)
hekit_config_tool(_Rivet_link COMMAND rivet-config --libs)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Rivet
  REQUIRED_VARS _Rivet_link
  FAIL_MESSAGE "rivet-config not found or not working - Rivet support is disabled")

if(Rivet_FOUND)
  hekit_target_from_flags(Rivet::Rivet COMPILE "${_Rivet_compile}" LINK "${_Rivet_link}")
endif()
