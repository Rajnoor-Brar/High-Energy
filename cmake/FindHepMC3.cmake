# HepMC3 via `HepMC3-config` (09 §1). Defines the imported target HepMC3::HepMC3.
include(HekitDependency)

hekit_config_tool(_HepMC3_compile COMMAND HepMC3-config --cflags)
hekit_config_tool(_HepMC3_link COMMAND HepMC3-config --libs)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(HepMC3
  REQUIRED_VARS _HepMC3_link
  FAIL_MESSAGE "HepMC3-config not found or not working - HepMC3 support is disabled")

if(HepMC3_FOUND)
  hekit_target_from_flags(HepMC3::HepMC3 COMPILE "${_HepMC3_compile}" LINK "${_HepMC3_link}")
endif()
