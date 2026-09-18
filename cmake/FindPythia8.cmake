# Pythia8 via `pythia8-config` (09 §1). Defines the imported target Pythia8::Pythia8.
include(HekitDependency)

hekit_config_tool(_Pythia8_compile COMMAND pythia8-config --cxxflags)
hekit_config_tool(_Pythia8_link COMMAND pythia8-config --ldflags)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(Pythia8
  REQUIRED_VARS _Pythia8_link
  FAIL_MESSAGE "pythia8-config not found or not working - Pythia8 support is disabled")

if(Pythia8_FOUND)
  hekit_target_from_flags(Pythia8::Pythia8 COMPILE "${_Pythia8_compile}" LINK "${_Pythia8_link}")
endif()
