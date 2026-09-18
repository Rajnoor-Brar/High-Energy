# FastJet via `fastjet-config` (09 §1), plugins included because photo_eic uses SISCone.
include(HekitDependency)

hekit_config_tool(_FastJet_compile COMMAND fastjet-config --cxxflags)
hekit_config_tool(_FastJet_link COMMAND fastjet-config --libs --plugins=yes)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(FastJet
  REQUIRED_VARS _FastJet_link
  FAIL_MESSAGE "fastjet-config not found - FastJet support is disabled")

if(FastJet_FOUND)
  hekit_target_from_flags(FastJet::FastJet COMPILE "${_FastJet_compile}" LINK "${_FastJet_link}")
endif()
