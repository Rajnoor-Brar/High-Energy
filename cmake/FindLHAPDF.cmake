# LHAPDF via `lhapdf-config` (09 §1). Defines the imported target LHAPDF::LHAPDF.
include(HekitDependency)

hekit_config_tool(_LHAPDF_compile COMMAND lhapdf-config --cppflags)
hekit_config_tool(_LHAPDF_link COMMAND lhapdf-config --ldflags)

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(LHAPDF
  REQUIRED_VARS _LHAPDF_link
  FAIL_MESSAGE "lhapdf-config not found or not working - LHAPDF support is disabled")

if(LHAPDF_FOUND)
  hekit_target_from_flags(LHAPDF::LHAPDF COMPILE "${_LHAPDF_compile}" LINK "${_LHAPDF_link}")
endif()
